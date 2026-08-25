from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from werkzeug.security import check_password_hash, generate_password_hash
from bson.objectid import ObjectId
from datetime import datetime, timezone

from models.database import get_users_collection, get_audit_logs_collection
from services.audit import log_audit

auth_bp = Blueprint('auth', __name__)


PORTALS = {
    # portal key -> (roles allowed to sign in here, dashboard endpoint, human label)
    'admin':       (('admin',), 'admin.dashboard', 'Admin'),
    'super_admin': (('super_admin',), 'super_admin.dashboard', 'Super Admin'),
}


def _dashboard_for(role):
    role = str(role or '').lower()
    if role == 'super_admin':
        return url_for('super_admin.dashboard')
    if role == 'admin':
        return url_for('admin.dashboard')
    if role in ['judge', 'internal_judge', 'external_judge']:
        return url_for('judge.dashboard')
    return url_for('index')


def staff_login(portal):
    """
    Sign-in page for one staff role. Mounted as /admin/login (portal='admin')
    and /super-admin/login (portal='super_admin'). Each page accepts only its
    own role, so an Admin cannot enter through the Super Admin door and vice
    versa — the page tells them which door to use instead.
    """
    allowed, dashboard, label = PORTALS[portal]
    ctx = {'portal': portal, 'portal_label': label}

    if 'user_id' in session:
        return redirect(_dashboard_for(session.get('role')))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please provide email and password', 'error')
            return render_template('auth/login.html', **ctx)

        users = get_users_collection()
        user = users.find_one({'email': email})
        if not user or not check_password_hash(user.get('password_hash', ''), password):
            flash('Invalid email or password', 'error')
            log_audit(str(user['_id']) if user else None, 'login_failed', 'user', str(user['_id']) if user else None,
                      {'email': email, 'reason': 'invalid_password' if user else 'user_not_found', 'portal': portal})
            return render_template('auth/login.html', **ctx)

        if user.get('status') != 'active':
            flash('Your account is not active. Please contact the administrator.', 'error')
            log_audit(str(user['_id']), 'login_failed', 'user', str(user['_id']), {'reason': 'inactive_account', 'portal': portal})
            return render_template('auth/login.html', **ctx)

        user_role = str(user.get('role', '')).lower()
        if user_role not in allowed:
            other = {'admin': ('Super Admin', 'super_admin.login'), 'super_admin': ('Admin', 'admin.login')}
            if user_role in PORTALS:
                name, endpoint = other[portal]
                flash(f'This is the {label} sign-in. Your account is a {name} account — use the {name} sign-in instead.', 'error')
                log_audit(str(user['_id']), 'login_failed', 'user', str(user['_id']), {'reason': 'wrong_portal', 'portal': portal})
                return redirect(url_for(endpoint))
            if user_role in ['judge', 'internal_judge', 'external_judge']:
                flash('Jury members sign in on the Jury page.', 'error')
                return redirect(url_for('judge.login'))
            flash('This account cannot sign in here.', 'error')
            log_audit(str(user['_id']), 'login_failed', 'user', str(user['_id']), {'reason': 'role_not_allowed', 'portal': portal})
            return render_template('auth/login.html', **ctx)

        session.clear()
        session.permanent = True
        session['user_id'] = str(user['_id'])
        session['email'] = user['email']
        session['name'] = user['name']
        session['role'] = user['role']

        users.update_one({'_id': user['_id']}, {'$set': {'last_login': datetime.now(timezone.utc).replace(tzinfo=None)}})
        log_audit(str(user['_id']), 'login_success', 'user', str(user['_id']), {'portal': portal})
        return redirect(url_for(dashboard))

    return render_template('auth/login.html', **ctx)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Legacy URL. Staff now sign in at /admin/login or /super-admin/login."""
    if 'user_id' in session:
        return redirect(_dashboard_for(session.get('role')))
    if request.method == 'POST':
        # Backward compatibility for old bookmarks/tests: route by the account's role.
        email = request.form.get('email', '').strip().lower()
        user = get_users_collection().find_one({'email': email}) if email else None
        portal = 'super_admin' if user and str(user.get('role', '')).lower() == 'super_admin' else 'admin'
        return staff_login(portal)
    return redirect(url_for('admin.login'))


@auth_bp.route('/logout')
def logout():
    """Logout"""
    user_id = session.get('user_id')
    if user_id:
        log_audit(user_id, 'logout', 'user', user_id)
    
    role = str(session.get('role', '')).lower()
    session.clear()
    flash('You have been signed out', 'success')
    if role == 'super_admin':
        return redirect(url_for('super_admin.login'))
    if role in ['judge', 'internal_judge', 'external_judge']:
        return redirect(url_for('judge.login'))
    return redirect(url_for('admin.login'))


@auth_bp.route('/api/logout', methods=['POST'])
def api_logout():
    """API Logout for judge and frontend sessions"""
    user_id = session.get('user_id')
    if user_id:
        log_audit(user_id, 'JUDGE_LOGOUT', 'judge', user_id)
    session.clear()
    from flask import jsonify
    return jsonify({
        'success': True,
        'message': 'Logged out successfully',
        'redirect_url': url_for('judge.login')
    })


def require_auth(roles=None):
    """Decorator to require authentication and optionally specific roles"""
    from functools import wraps
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please sign in to continue', 'error')
                path = request.path
                if path.startswith('/super-admin'):
                    return redirect(url_for('super_admin.login'))
                if path.startswith('/judge') or path.startswith('/results') or path.startswith('/api/evaluations'):
                    return redirect(url_for('judge.login'))
                return redirect(url_for('admin.login'))
            
            user_role = str(session.get('role', '')).lower()
            if roles:
                allowed_roles = [str(r).lower() for r in roles]
                
                # Super Admin has access to all admin-level routes
                if 'admin' in allowed_roles and 'super_admin' not in allowed_roles:
                    allowed_roles.append('super_admin')
                
                # Normalize judge roles
                is_judge_allowed = any(r in ['judge', 'internal_judge', 'external_judge'] for r in allowed_roles)
                is_user_judge = user_role in ['judge', 'internal_judge', 'external_judge']
                
                if is_judge_allowed and is_user_judge:
                    return f(*args, **kwargs)
                
                if user_role not in allowed_roles:
                    return render_template('errors/error.html',
                                         code=403,
                                         title='Access Denied',
                                         message="You don't have permission to view this page."), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
