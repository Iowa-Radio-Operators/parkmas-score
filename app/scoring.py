from collections import defaultdict
from datetime import datetime
from app import db

VALID_MODES = {"SSB", "CW", "FT8", "FT4", "RTTY", "PSK31", "FM"}


def get_qso_local_date(qso):
    dt = qso.datetime_on
    if not dt:
        return None
    return dt.date()


def get_qso_park_code(qso):
    """
    Returns YOUR park code for the QSO (e.g. 'US-9317').
    Only looks at MY park (where you're activating from), not their park.
    """
    # Check the linked parks - but we need to verify it's from MY_SIG_INFO
    if qso.parks:
        # The park was linked during import from MY_SIG_INFO or similar fields
        return qso.parks[0].park.park_ref
    return None


def get_qso_power(qso):
    """
    Returns TX power as a float, or None if missing/invalid.
    """
    p = getattr(qso, "tx_pwr", None)
    if p is None:
        return None
    try:
        return float(p)
    except (TypeError, ValueError):
        return None


def score_qsos_for_operator(qsos):
    """
    Score QSOs for a single operator across all days/parks.
    
    Scoring rules (MULTIPLIERS):
    - Base: 2 points per QSO
    - New Park Multiplier: ×2 (only on FIRST activation of that park)
    - QRP Multiplier: ×2 (if 5W or less)
    
    Examples:
    - Day 1 @ US-9317 (NOT new, it's your starting park): 2 pts (4 if QRP)
    - Day 2 @ US-2281 (NEW park): 2 × 2 = 4 pts (4 × 2 = 8 if QRP)
    - Day 3 @ US-9317 (repeat): 2 pts (4 if QRP)
    - Day 4 @ US-2281 (repeat): 2 pts (4 if QRP)
    
    Maximum: 2 × 2 × 2 = 8 points per QSO
    
    Returns:
        {
          "daily": {
             (date, park_code): {
                 "qsos": [qso, ...],
                 "score": int,
                 "qso_scores": {qso.id: int},
                 "park_code": str,
                 "date": date,
                 "is_new_park": bool,
             },
             ...
          },
          "by_operator": {
             "total_score": int,
             "total_qsos": int,
             "days": int,
             "parks": set([...]),
          }
        }
    """
    print(f"\n=== SCORING DEBUG: Processing {len(qsos)} QSOs ===")
    
    # Sort all QSOs by datetime to process chronologically
    sorted_qsos = sorted([q for q in qsos if q.datetime_on], key=lambda q: q.datetime_on)
    
    print(f"QSOs with valid dates: {len(sorted_qsos)}")
    
    # Track which parks have been activated
    parks_activated = {}  # park_code -> date first activated
    is_very_first_park = True  # Track if this is the operator's very first park ever
    
    # Group by (date, park) for processing
    day_park_qsos = defaultdict(lambda: defaultdict(list))
    
    for qso in sorted_qsos:
        park_code = get_qso_park_code(qso)
        qso_date = get_qso_local_date(qso)
        
        if park_code and qso_date:
            day_park_qsos[qso_date][park_code].append(qso)
    
    # Process each day/park combination in chronological order
    daily_results = {}
    total_score = 0
    total_qsos = 0
    
    for qso_date in sorted(day_park_qsos.keys()):
        parks_dict = day_park_qsos[qso_date]
        
        print(f"\n--- Processing date: {qso_date} ---")
        
        for park_code, qsos_list in parks_dict.items():
            # Check if this is a NEW park (never activated before)
            is_new_park = park_code not in parks_activated
            
            # First park ever doesn't get the bonus
            if is_very_first_park:
                is_new_park = False
                is_very_first_park = False
                parks_activated[park_code] = qso_date
                print(f"🏁 FIRST PARK EVER: {park_code} (no bonus - this is your starting park)")
            elif is_new_park:
                parks_activated[park_code] = qso_date
                print(f"✨ NEW PARK: {park_code} (first activation - all QSOs get 2× multiplier!)")
            else:
                print(f"Repeat park: {park_code} (first was on {parks_activated[park_code]})")
            
            qso_scores = {}
            day_score = 0
            skipped_mode = 0
            
            for qso in sorted(qsos_list, key=lambda q: q.datetime_on):
                mode = (qso.mode or "").upper()
                
                # Check valid mode
                if mode not in VALID_MODES:
                    print(f"  QSO {qso.id}: INVALID MODE '{mode}' - skipped")
                    qso_scores[qso.id] = 0
                    skipped_mode += 1
                    continue
                
                # Calculate score with MULTIPLIERS
                score = 2  # Base points
                multiplier = 1
                score_breakdown = ["2 base"]
                
                # New park multiplier (×2)
                if is_new_park:
                    multiplier *= 2
                    score_breakdown.append("×2 new park")
                
                # QRP multiplier (×2)
                power = get_qso_power(qso)
                if power is not None and power <= 5:
                    multiplier *= 2
                    score_breakdown.append(f"×2 QRP ({power}W)")
                
                score = score * multiplier
                
                qso_scores[qso.id] = score
                day_score += score
                total_qsos += 1
                
                print(f"  QSO {qso.id}: {score} pts [{' '.join(score_breakdown)}] - {qso.call} on {mode}")
            
            print(f"Park {park_code} subtotal: {day_score} pts from {len(qso_scores)} QSOs")
            if skipped_mode > 0:
                print(f"  (skipped {skipped_mode} QSOs due to invalid mode)")
            
            daily_results[(qso_date, park_code)] = {
                "qsos": qsos_list,
                "score": day_score,
                "qso_scores": qso_scores,
                "park_code": park_code,
                "date": qso_date,
                "is_new_park": is_new_park,
            }
            
            total_score += day_score
    
    print(f"\n=== FINAL TOTALS ===")
    print(f"Total score: {total_score}")
    print(f"Total QSOs counted: {total_qsos}")
    print(f"Unique parks activated: {len(parks_activated)}")
    print(f"Days active: {len(day_park_qsos)}")
    
    return {
        "daily": daily_results,
        "by_operator": {
            "total_score": total_score,
            "total_qsos": total_qsos,
            "days": len(day_park_qsos),
            "parks": set(parks_activated.keys()),
        },
    }