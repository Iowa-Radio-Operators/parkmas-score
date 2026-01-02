from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    callsign = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f"<User {self.callsign}>"


class Log(db.Model):
    __tablename__ = "logs"

    id = db.Column(db.Integer, primary_key=True)
    operator = db.Column(db.String(20))
    station_callsign = db.Column(db.String(20))
    filename = db.Column(db.String(255))

    qsos = db.relationship("QSO", backref="log", lazy=True)


class QSO(db.Model):
    __tablename__ = "qsos"

    id = db.Column(db.Integer, primary_key=True)
    log_id = db.Column(db.Integer, db.ForeignKey("logs.id"), nullable=False)

    call = db.Column(db.String(20))
    band = db.Column(db.String(20))
    mode = db.Column(db.String(20))
    submode = db.Column(db.String(20))
    freq = db.Column(db.Float)
    rst_sent = db.Column(db.String(10))
    rst_rcvd = db.Column(db.String(10))
    state = db.Column(db.String(10))
    county = db.Column(db.String(50))
    country = db.Column(db.String(50))
    gridsquare = db.Column(db.String(20))
    distance = db.Column(db.Float)
    raw_comment = db.Column(db.String(255))

    datetime_on = db.Column(db.DateTime)
    datetime_off = db.Column(db.DateTime)

    parks = db.relationship("QsoPark", backref="qso", lazy=True)

    # ---------------------------------------------------------
    # ADIF IMPORT LOGIC
    # ---------------------------------------------------------
    @classmethod
    def from_adif(cls, record, log_id):
        """Create a QSO object from an ADIF record dict."""
        r = {k.lower(): v for k, v in record.items()}

        # Print debug info for first QSO
        if log_id == 1:
            print(f"\nDEBUG: Sample ADIF record keys: {list(r.keys())[:10]}")
            print(f"QSO_DATE value: '{r.get('qso_date')}'")
            print(f"TIME_ON value: '{r.get('time_on')}'")

        # -----------------------------
        # DATETIME PARSING (FIXED)
        # -----------------------------
        dt_on = None
        dt_off = None

        if "qso_date" in r and "time_on" in r:
            try:
                qso_date = r["qso_date"].strip()
                time_on = r["time_on"].strip()
                
                # Handle time formats: "HHMM", "HHMMSS", or with spaces
                time_on = time_on.replace(" ", "")[:4]  # Take first 4 digits only (HHMM)
                
                # Parse: YYYYMMDD + HHMM
                dt_on = datetime.strptime(qso_date + time_on, "%Y%m%d%H%M")
                print(f"Parsed datetime_on: {dt_on}")
            except Exception as e:
                print(f"ERROR parsing datetime_on: {e} (date='{r.get('qso_date')}', time='{r.get('time_on')}')")
                dt_on = None

        if "qso_date_off" in r and "time_off" in r:
            try:
                qso_date_off = r["qso_date_off"].strip()
                time_off = r["time_off"].strip()
                time_off = time_off.replace(" ", "")[:4]
                
                dt_off = datetime.strptime(qso_date_off + time_off, "%Y%m%d%H%M")
            except Exception as e:
                print(f"ERROR parsing datetime_off: {e}")
                dt_off = None

        # -----------------------------
        # CREATE QSO OBJECT
        # -----------------------------
        qso = cls(
            log_id=log_id,
            call=r.get("call"),
            band=r.get("band"),
            mode=r.get("mode"),
            submode=r.get("submode"),
            freq=float(r["freq"]) if "freq" in r else None,
            rst_sent=r.get("rst_sent"),
            rst_rcvd=r.get("rst_rcvd"),
            state=r.get("state"),
            county=r.get("county"),
            country=r.get("country"),
            gridsquare=r.get("gridsquare"),
            distance=float(r["distance"]) if "distance" in r else None,
            raw_comment=r.get("comment") or r.get("notes"),
            datetime_on=dt_on,
            datetime_off=dt_off,
        )

        db.session.add(qso)
        db.session.flush()  # ensures qso.id exists

        # -----------------------------
        # PARK HANDLING - Prioritize MY park (where YOU are activating from)
        # -----------------------------
        # Look for MY park first (activator's park)
        pota = (
            r.get("my_sig_info")
            or r.get("my_sig")
            or r.get("my_pota_ref")
            # Only fall back to their park if MY park not found
            or r.get("sig_info")
            or r.get("sig")
            or r.get("pota_ref")
        )

        if pota:
            # Normalize park ref (e.g., K-1234)
            pota = pota.strip().upper()

            # Find or create Park
            park = Park.query.filter_by(park_ref=pota).first()
            if not park:
                park = Park(park_ref=pota)
                db.session.add(park)
                db.session.flush()

            # Link QSO ↔ Park
            link = QsoPark(qso_id=qso.id, park_id=park.id)
            db.session.add(link)

        return qso


class Park(db.Model):
    __tablename__ = "parks"

    id = db.Column(db.Integer, primary_key=True)
    park_ref = db.Column(db.String(20), unique=True, nullable=False)

    qsos = db.relationship("QsoPark", backref="park", lazy=True)


class QsoPark(db.Model):
    __tablename__ = "qso_parks"

    id = db.Column(db.Integer, primary_key=True)
    qso_id = db.Column(db.Integer, db.ForeignKey("qsos.id"), nullable=False)
    park_id = db.Column(db.Integer, db.ForeignKey("parks.id"), nullable=False)