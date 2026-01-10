from flask import Blueprint, redirect
from .client_auth import redirect_to_login, logout_everywhere

auth = Blueprint("auth", __name__)


@auth.route("/login", methods=["GET", "POST"])
def login():
    """Redirect to SSO login"""
    return redirect_to_login()


@auth.route("/logout")
def logout():
    """Logout via SSO"""
    return logout_everywhere()