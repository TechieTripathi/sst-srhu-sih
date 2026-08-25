from functools import wraps
from flask import session, redirect, url_for, flash, abort


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    """Server-side role check. Frontend hiding of buttons is never security."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                flash("Please sign in to continue.", "warning")
                return redirect(url_for("auth.login"))
            if session.get("role") not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def current_user_id():
    return session.get("user_id")


def current_role():
    return session.get("role")
