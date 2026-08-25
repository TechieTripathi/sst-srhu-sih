from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from werkzeug.security import check_password_hash, generate_password_hash
from bson.objectid import ObjectId
from datetime import datetime, timezone

from models.database import get_users_collection, get_audit_logs_collection
from services.audit import log_audit

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if 'user_id' in session:
        role = session.get('role')
        if role == 'super_admin':
            return redirect(url_for('super_admin.dashboard'))
        elif role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif role in ['internal_judge', 'external_judge']:
            return redirect(url_for('judge.dashboard'))
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        if not email or not password:
            flash('Please provide email and password', 'error')
            return render_template('auth/login.html')
        
        users = get_users_collection()
        user = users.find_one({'email': email})
        
        if not user:
            flash('Invalid email or password', 'error')
            log_audit(None, 'login_failed', 'user', None, {'email': email, 'reason': 'user_not_found'})
            return render_template('auth/login.html')
        
        if not check_password_hash(user['password_hash'], password):
            flash('Invalid email or password', 'error')
            log_audit(str(user['_id']), 'login_failed', 'user', str(user['_id']), {'reason': 'invalid_password'})
            return render_template('auth/login.html')
        
        if user.get('status') != 'active':
            flash('Your account is not active. Please contact the administrator.', 'error')
            log_audit(str(user['_id']), 'login_failed', 'user', str(user['_id']), {'reason': 'inactive_account'})
            return render_template('auth/login.html')
        
        # Create session
        session.permanent = True
        session['user_id'] = str(user['_id'])
        session['email'] = user['email']
        session['name'] = user['name']
        session['role'] = user['role']

        user_role = str(user.get('role', '')).lower()
        if user_role in ['judge', 'internal_judge', 'external_judge']:
            from models.database import get_judges_collection
            judges_col = get_judges_collection()
            judge = judges_col.find_one({'email': user['email']}) or judges_col.find_one({'user_id': str(user['_id'])})
            if judge:
                session['judge_type'] = judge.get('judge_type', 'INTERNAL_JUDGE')
                if judge.get('panel_id'):
                    session['panel_id'] = judge['panel_id']

        # Update last login
        now_dt = datetime.now(timezone.utc).replace(tzinfo=None)
        users.update_one(
            {'_id': user['_id']},
            {'$set': {'last_login': now_dt}}
        )

        log_audit(str(user['_id']), 'login_success', 'user', str(user['_id']))

        # Redirect based on role
        if user_role == 'super_admin':
            return redirect(url_for('super_admin.dashboard'))
        elif user_role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif user_role in ['judge', 'internal_judge', 'external_judge']:
            return redirect(url_for('judge.dashboard'))
        elif user_role == 'student_leader':
            return redirect(url_for('index'))
        else:
            return redirect(url_for('index'))
    
    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    """Logout"""
    user_id = session.get('user_id')
    if user_id:
        log_audit(user_id, 'logout', 'user', user_id)
    
    session.clear()
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('auth.login'))


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
                flash('Please log in to access this page', 'error')
                return redirect(url_for('auth.login'))
            
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
