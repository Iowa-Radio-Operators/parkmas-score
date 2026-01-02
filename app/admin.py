from .auth_utils import admin_required

@bp.route("/admin")
@admin_required
def admin_home():
    return render_template("admin_home.html", title="Admin Dashboard")