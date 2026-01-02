from functools import wraps
from flask import session, redirect, url_for


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_is_admin"):
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return wrapper