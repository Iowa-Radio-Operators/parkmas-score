from flask import Blueprint, render_template, request, current_app as app, redirect, url_for, send_from_directory
from hamutils.adif import ADIReader
from collections import defaultdict
from sqlalchemy.orm import joinedload
import io
import os
from app.importer import import_adif_file
from app import db
from app.models import QSO, Log
from app.scoring import score_qsos_for_operator
from .auth_utils import admin_required
bp = Blueprint("main", __name__)

ALLOWED_EXTENSIONS = {"adi", "adif"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# -----------------------------
# INDEX ROUTES
# -----------------------------
@bp.route("/")
def index():
    return render_template("index.html", title="Home")


@bp.route("/index")
def index_alias():
    return render_template("index.html", title="Home")


@bp.route("/index.html")
def index_html():
    return render_template("index.html", title="Home")


# -----------------------------
# UPLOAD ROUTE (SAVES FOR REVIEW - DOESN'T IMPORT)
# -----------------------------
@bp.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file = request.files.get("adif_file")

        if not file:
            return render_template("upload.html", title="Upload Logs", error="No file selected")

        if not allowed_file(file.filename):
            return render_template(
                "upload.html",
                title="Upload Logs",
                error="Invalid file type. Only .adi or .adif files are allowed."
            )

        try:
            upload_dir = os.path.join(app.instance_path, "uploads")
            os.makedirs(upload_dir, exist_ok=True)

            save_path = os.path.join(upload_dir, file.filename)
            file.save(save_path)

            # Count QSOs for display
            with open(save_path, "r", encoding="utf-8") as f:
                reader = ADIReader(f)
                qso_count = sum(1 for _ in reader)

            return render_template(
                "upload.html",
                title="Upload Logs",
                success=f"Uploaded {file.filename} with {qso_count} QSOs. An admin will review it shortly."
            )

        except Exception as e:
            return render_template(
                "upload.html",
                title="Upload Logs",
                error=f"Error uploading ADIF file: {e}"
            )

    return render_template("upload.html", title="Upload Logs")


# -----------------------------
# ADMIN HOME
# -----------------------------
@bp.route("/admin")
@admin_required
def admin_home():
    upload_dir = os.path.join(app.instance_path, "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    upload_count = len([
        f for f in os.listdir(upload_dir)
        if os.path.isfile(os.path.join(upload_dir, f))
    ])

    from .models import QSO, Park
    qso_count = QSO.query.count()
    park_count = Park.query.count()

    return render_template(
        "admin_home.html",
        title="Admin Dashboard",
        upload_count=upload_count,
        qso_count=qso_count,
        park_count=park_count
    )


# -----------------------------
# REVIEW UPLOADS
# -----------------------------
@bp.route("/admin/uploads")
@admin_required
def review_uploads():
    upload_dir = os.path.join(app.instance_path, "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    from .models import Log
    imported_files = {log.filename for log in Log.query.all()}

    files = []

    for filename in os.listdir(upload_dir):
        if filename in imported_files:
            continue  # hide imported files

        full_path = os.path.join(upload_dir, filename)
        if not os.path.isfile(full_path):
            continue

        size = os.path.getsize(full_path)
        uploaded = os.path.getmtime(full_path)

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                reader = ADIReader(f)
                qso_count = sum(1 for _ in reader)
        except Exception:
            qso_count = 0

        files.append({
            "name": filename,
            "size": size,
            "uploaded": uploaded,
            "qso_count": qso_count
        })

    return render_template(
        "admin_uploads.html",
        title="Review Uploads",
        files=files
    )


@bp.route("/admin/uploads/accept/<filename>", methods=["POST"])
@admin_required
def accept_upload(filename):
    upload_dir = os.path.join(app.instance_path, "uploads")
    full_path = os.path.join(upload_dir, filename)

    if not os.path.isfile(full_path):
        return "File not found", 404

    try:
        # Use the importer to add to database
        import_adif_file(full_path, filename)
        return redirect(url_for("main.review_uploads"))
    except Exception as e:
        return f"Error importing file: {e}", 500


@bp.route("/admin/uploads/reject/<filename>", methods=["POST"])
@admin_required
def reject_upload(filename):
    upload_dir = os.path.join(app.instance_path, "uploads")
    full_path = os.path.join(upload_dir, filename)

    # Delete the file if it exists
    if os.path.isfile(full_path):
        os.remove(full_path)

    # Return to the review page
    return redirect(url_for("main.review_uploads"))


# -----------------------------
# SCORES PLACEHOLDER
# -----------------------------
@bp.route("/admin/scores")
@admin_required
def scores():
    return "<h3>Scores Dashboard (coming soon)</h3>"


# -----------------------------
# EDIT UPLOAD (QSO EDITOR)
# -----------------------------
@bp.route("/admin/uploads/edit/<filename>", methods=["GET"])
@admin_required
def edit_upload(filename):
    upload_dir = os.path.join(app.instance_path, "uploads")
    full_path = os.path.join(upload_dir, filename)

    if not os.path.isfile(full_path):
        return "File not found", 404

    with open(full_path, "r", encoding="utf-8") as f:
        reader = ADIReader(f)
        qsos = list(reader)

    editable_qsos = []
    for q in qsos:
        editable_qsos.append({k.lower(): v for k, v in q.items()})

    seen = set()
    duplicates = set()

    for i, q in enumerate(editable_qsos):
        key = (
            q.get("call", "").upper(),
            q.get("band", "").upper(),
            q.get("mode", "").upper(),
            q.get("qso_date", ""),
            q.get("time_on", "")
        )
        if key in seen:
            duplicates.add(i)
        else:
            seen.add(key)

    return render_template(
        "admin_edit_upload.html",
        title="Edit QSO Data",
        filename=filename,
        qsos=editable_qsos,
        duplicates=duplicates
    )


@bp.route("/admin/uploads/edit/<filename>", methods=["POST"])
@admin_required
def save_edit_upload(filename):
    upload_dir = os.path.join(app.instance_path, "uploads")
    full_path = os.path.join(upload_dir, filename)

    if not os.path.isfile(full_path):
        return "File not found", 404

    qsos = []
    total = int(request.form.get("total_qsos", 0))

    for i in range(total):
        qso = {}
        prefix = f"qso_{i}_"

        for key in request.form:
            if key.startswith(prefix):
                field = key[len(prefix):]
                qso[field.upper()] = request.form[key]

        qsos.append(qso)

    with open(full_path, "w", encoding="utf-8") as f:
        for q in qsos:
            for k, v in q.items():
                f.write(f"<{k}:{len(v)}>{v}")
            f.write("<EOR>\n")

    return redirect(url_for("main.edit_upload", filename=filename))


@bp.route("/admin/uploads/delete_qso/<filename>/<int:index>", methods=["POST"])
@admin_required
def delete_qso_from_upload(filename, index):
    upload_dir = os.path.join(app.instance_path, "uploads")
    full_path = os.path.join(upload_dir, filename)

    if not os.path.isfile(full_path):
        return "File not found", 404

    # Read entire file
    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split into header + QSO blocks
    if "<EOH>" not in content:
        return "Invalid ADIF: missing <EOH>", 400

    header, body = content.split("<EOH>", 1)
    header = header.strip() + "\n<EOH>\n"

    # Split QSOs by <EOR>
    qso_blocks = [b.strip() for b in body.split("<EOR>") if b.strip()]

    # Remove selected QSO
    if 0 <= index < len(qso_blocks):
        qso_blocks.pop(index)

    # Reassemble ADIF
    new_body = ""
    for block in qso_blocks:
        new_body += block + " <EOR>\n"

    # Write back
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(new_body)

    return redirect(url_for("main.edit_upload", filename=filename))

# -----------------------------
# FILE MANAGER
# -----------------------------
@bp.route("/admin/files")
@admin_required
def file_manager():
    upload_dir = os.path.join(app.instance_path, "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    files = []
    for filename in os.listdir(upload_dir):
        full_path = os.path.join(upload_dir, filename)
        if os.path.isfile(full_path):
            size = os.path.getsize(full_path)
            uploaded = os.path.getmtime(full_path)

            files.append({
                "name": filename,
                "size": size,
                "uploaded": uploaded
            })

    return render_template(
        "admin_files.html",
        title="File Management",
        files=files
    )


@bp.route("/admin/files/delete/<filename>", methods=["POST"])
@admin_required
def delete_file(filename):
    # You may want to disable deletion entirely for audit reasons
    return redirect(url_for("main.file_manager"))


@bp.route("/admin/files/download/<filename>")
@admin_required
def download_file(filename):
    upload_dir = os.path.join(app.instance_path, "uploads")

    safe_path = os.path.join(upload_dir, filename)
    if not os.path.isfile(safe_path):
        return "File not found", 404

    return send_from_directory(upload_dir, filename, as_attachment=True)

@bp.route("/admin/scoring")
@admin_required
def scoring_overview():
    # Load all QSOs with their logs
    qsos = (
        db.session.query(QSO)
        .outerjoin(Log, QSO.log_id == Log.id)
        .options(joinedload(QSO.log))
        .all()
    )

    print("QSOs loaded:", len(qsos))

    # Group QSOs by operator
    qsos_by_operator = defaultdict(list)
    for qso in qsos:
        if not qso.log:
            continue

        operator = (
            qso.log.operator
            or qso.log.station_callsign
            or f"LOG-{qso.log.id}"
        ).upper()
        if not operator:
            continue

        qsos_by_operator[operator].append(qso)

    print("Operators found:", list(qsos_by_operator.keys()))

    operator_results = []
    for operator, op_qsos in qsos_by_operator.items():
        result = score_qsos_for_operator(op_qsos, operator_name=operator)  # Pass operator name
        summary = result["by_operator"]

        operator_results.append({
            "operator": operator,
            "total_score": summary["total_score"],
            "total_qsos": summary["total_qsos"],
            "days": summary["days"],
            "parks": sorted(summary["parks"]),
            "daily": result["daily"],
        })

    operator_results.sort(key=lambda r: r["total_score"], reverse=True)

    return render_template("scoring_overview.html", operators=operator_results)


@bp.route("/admin/scoring/multiplier/<operator>/<date_str>", methods=["GET", "POST"])
@admin_required
def set_daily_multiplier(operator, date_str):
    """Set or update a daily multiplier for an operator on a specific date"""
    from datetime import datetime
    from .models import DailyMultiplier
    
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return "Invalid date format", 400
    
    if request.method == "POST":
        # Check if this is a delete request
        if request.form.get("delete"):
            dm = DailyMultiplier.query.filter_by(
                operator=operator,
                date=date_obj
            ).first()
            
            if dm:
                db.session.delete(dm)
                db.session.commit()
            
            return redirect(url_for("main.scoring_overview"))
        
        # Otherwise, save/update the multiplier
        multiplier = float(request.form.get("multiplier", 1.0))
        reason = request.form.get("reason", "").strip()
        
        # Find or create multiplier
        dm = DailyMultiplier.query.filter_by(
            operator=operator,
            date=date_obj
        ).first()
        
        if not dm:
            dm = DailyMultiplier(operator=operator, date=date_obj)
            db.session.add(dm)
        
        dm.multiplier = multiplier
        dm.reason = reason
        db.session.commit()
        
        return redirect(url_for("main.scoring_overview"))
    
    # GET request - show form
    dm = DailyMultiplier.query.filter_by(
        operator=operator,
        date=date_obj
    ).first()
    
    return render_template(
        "set_multiplier.html",
        operator=operator,
        date=date_str,
        current_multiplier=dm.multiplier if dm else 1.0,
        current_reason=dm.reason if dm else ""
    )

@bp.route("/admin/debug_qsos")
@admin_required
def debug_qsos():
    """Temporary debug route to see what's in the QSOs"""
    qsos = QSO.query.limit(5).all()
    
    output = "<h2>Debug: First 5 QSOs</h2>"
    
    for qso in qsos:
        output += f"<h3>QSO ID: {qso.id}</h3>"
        output += f"<p>Call: {qso.call}</p>"
        output += f"<p>Band: {qso.band}</p>"
        output += f"<p>Mode: {qso.mode}</p>"
        output += f"<p>DateTime On: {qso.datetime_on}</p>"
        output += f"<p>Raw Comment: {qso.raw_comment}</p>"
        output += f"<p>Parks linked: {len(qso.parks)}</p>"
        
        if qso.parks:
            for qp in qso.parks:
                output += f"<p>&nbsp;&nbsp;- Park: {qp.park.park_ref}</p>"
        else:
            output += "<p style='color:red;'>NO PARKS LINKED!</p>"
        
        output += "<hr>"
    
    return output

# -----------------------------
# PUBLIC LEADERBOARD
# -----------------------------
@bp.route("/leaders")
def leaderboard():
    """Public leaderboard - no login required"""
    # Load all QSOs with their logs
    qsos = (
        db.session.query(QSO)
        .outerjoin(Log, QSO.log_id == Log.id)
        .options(joinedload(QSO.log))
        .all()
    )

    # Group QSOs by operator
    qsos_by_operator = defaultdict(list)
    for qso in qsos:
        if not qso.log:
            continue

        operator = (
            qso.log.operator
            or qso.log.station_callsign
            or f"LOG-{qso.log.id}"
        ).upper()
        if not operator:
            continue

        qsos_by_operator[operator].append(qso)

    # Calculate scores for each operator
    operator_results = []
    for operator, op_qsos in qsos_by_operator.items():
        result = score_qsos_for_operator(op_qsos)
        summary = result["by_operator"]

        operator_results.append({
            "operator": operator,
            "total_score": summary["total_score"],
            "parks": sorted(summary["parks"]),
        })

    # Sort by score descending
    operator_results.sort(key=lambda r: r["total_score"], reverse=True)

    return render_template("leaderboard.html", operators=operator_results)

# -----------------------------
# MASTER RESET (DANGEROUS!)
# -----------------------------
@bp.route("/admin/reset", methods=["GET", "POST"])
@admin_required
def master_reset():
    """
    Master reset - deletes ALL data and files.
    Use this to prepare for next year's competition.
    """
    if request.method == "POST":
        confirmation = request.form.get("confirmation", "").strip()
        
        if confirmation.upper() != "DELETE EVERYTHING":
            return render_template(
                "admin_reset.html",
                title="Master Reset",
                error="You must type 'DELETE EVERYTHING' to confirm."
            )
        
        try:
            # Delete all database records
            from .models import QsoPark, QSO, Park, Log
            
            print("Deleting all database records...")
            db.session.query(QsoPark).delete()
            db.session.query(QSO).delete()
            db.session.query(Park).delete()
            db.session.query(Log).delete()
            db.session.commit()
            print("✓ Database cleared")
            
            # Delete all uploaded files
            upload_dir = os.path.join(app.instance_path, "uploads")
            if os.path.exists(upload_dir):
                file_count = 0
                for filename in os.listdir(upload_dir):
                    file_path = os.path.join(upload_dir, filename)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        file_count += 1
                print(f"✓ Deleted {file_count} uploaded files")
            
            return render_template(
                "admin_reset.html",
                title="Master Reset",
                success="All data and files have been deleted. System reset complete!"
            )
            
        except Exception as e:
            return render_template(
                "admin_reset.html",
                title="Master Reset",
                error=f"Error during reset: {e}"
            )
    
    return render_template("admin_reset.html", title="Master Reset")