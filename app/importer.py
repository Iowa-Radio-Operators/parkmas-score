from app import db
from app.models import Log, QSO
import adif_io


def import_adif_file(filepath, filename):
    """
    Import an ADIF file into the database.
    """

    # Read ADIF file
    records, header = adif_io.read_from_file(filepath)

    if not records:
        raise ValueError("No ADIF records found")

    # adif_io returns records as list of dicts already - just lowercase the keys
    first = {k.lower(): v for k, v in records[0].items()}

    operator = first.get("operator") or first.get("station_callsign")
    station_callsign = first.get("station_callsign") or operator

    if not operator:
        operator = filename.split(".")[0].upper()

    # Create Log row
    log = Log(
        operator=operator.upper(),
        station_callsign=station_callsign.upper() if station_callsign else None,
        filename=filename,
    )
    db.session.add(log)
    db.session.flush()

    # Process each QSO record
    for qso_record in records:
        QSO.from_adif(qso_record, log.id)

    db.session.commit()

    print("Imported", len(records), "QSOs for operator:", operator)
    return len(records)