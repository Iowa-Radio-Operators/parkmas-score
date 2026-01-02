from flask import Blueprint, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash
from .models import User

auth = Blueprint("auth", __name__)


# -------------------------------------------------
# LOGIN
# -------------------------------------------------
@auth.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        callsign = request.form.get("username", "").strip().upper()
        password = request.form.get("password", "")

        user = User.query.filter_by(callsign=callsign).first()

        # User not found
        if not user:
            error = "Invalid call sign or password"
            return render_template("login.html", title="Login", error=error)

        # Inactive user
        if not user.is_active:
            error = "Your account has been deactivated."
            return render_template("login.html", title="Login", error=error)

        # Password mismatch
        if not check_password_hash(user.password_hash, password):
            error = "Invalid call sign or password"
            return render_template("login.html", title="Login", error=error)

        # Successful login
        session["user"] = user.callsign
        session["user_id"] = user.id
        session["user_is_admin"] = bool(user.is_admin)
        session.permanent = True

        return redirect(url_for("main.index"))

    return render_template("login.html", title="Login", error=error)


# -------------------------------------------------
# LOGOUT
# -------------------------------------------------
@auth.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.index"))