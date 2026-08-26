import os
from flask import current_app, Blueprint, render_template, session, request, redirect, url_for, flash, jsonify
from werkzeug.security import generate_password_hash
from bson.objectid import ObjectId
from datetime import datetime

from routes.auth import require_auth, staff_login
from models.database import (
    get_teams_collection,
    get_users_collection,
    get_judges_collection,
    get_evaluations_collection,
    get_event_settings_collection,
    get_audit_logs_collection
)
from services.audit import log_audit
from services.jury_scope import FILTER_EXCEPTION, FILTER_GROUP
from services.results_calculator import get_evaluation_coverage
from services.email_service import get_email_status

super_admin_bp = Blueprint('super_admin', __name__)


@super_admin_bp.route('', methods=['GET', 'POST'], strict_slashes=False)
def login():
    """Super Admin (developer) sign-in."""
    return staff_login('super_admin')


@super_admin_bp.route('/login')
def login_alias():
    """Old URL — the sign-in page lives at the blueprint root."""
    return redirect(url_for('super_admin.login'), code=301)


@super_admin_bp.route('/dashboard')
@require_auth(roles=['super_admin'])
def dashboard():
    """Super Admin Dashboard with global system overview"""
    teams_col = get_teams_collection()
    judges_col = get_judges_collection()
    evaluations_col = get_evaluations_collection()
    settings_col = get_event_settings_collection()
    users_col = get_users_collection()
    audit_col = get_audit_logs_collection()

    coverage = get_evaluation_coverage()
    completed_evals = evaluations_col.count_documents({'status': 'submitted'})
    
    # Global Statistics
    stats = {
        'total_teams': teams_col.count_documents({}),
        'registered_teams': teams_col.count_documents({'status': 'registered'}),
        'total_judges': judges_col.count_documents({}),
        'internal_judges': judges_col.count_documents({'judge_type': {'$in': ['internal', 'INTERNAL_JUDGE']}}),
        'external_judges': judges_col.count_documents({'judge_type': {'$in': ['external', 'EXTERNAL_JUDGE']}}),
        'exception_judges': judges_col.count_documents(FILTER_EXCEPTION),
        'group_judges': judges_col.count_documents(FILTER_GROUP),
        'total_admins': users_col.count_documents({'role': 'admin'}),
        'evaluations_completed': completed_evals,
        'teams_evaluated': coverage['teams_evaluated'],
        'teams_pending': coverage['teams_pending'],
        'completion_percentage': int(coverage['completion_percentage'])
    }
    
    # Event and System Settings
    event_settings = settings_col.find_one({}) or {}
    stats['judging_locked'] = event_settings.get('judging_locked', False)
    stats['results_published'] = event_settings.get('results_published', False)
    stats['registration_open'] = event_settings.get('registration_open', True)
    
    # System Health Information
    system_status = {
        'database': 'Connected (MongoDB Atlas)',
        'auth_engine': 'Active (Role-Based Access Control)',
        'judging_engine': 'Locked' if stats['judging_locked'] else 'Active (Open for Submissions)',
        'results_status': 'Published' if stats['results_published'] else 'Unpublished (Restricted)',
        'server_time': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
        'email': (lambda e: f"Configured — {e['host']}:{e['port']} as {e['from_address']}" if e['configured'] else
                  "NOT configured — SMTP_HOST / SMTP_USERNAME missing in this deployment's environment")(get_email_status()),
        'frontend_url': current_app.config.get('FRONTEND_URL') or 'not set (links use the request host)',
        'env': os.environ.get('VERCEL_ENV') or os.environ.get('FLASK_ENV') or 'unknown',
    }
    
    # Recent Audit Log Activity
    recent_logs = list(audit_col.find().sort('created_at', -1).limit(10))
    for log in recent_logs:
        actor = None
        if log.get('actor_id'):
            try:
                actor = users_col.find_one({'_id': ObjectId(log['actor_id'])})
            except Exception:
                actor = users_col.find_one({'email': log['actor_id']})
        log['actor_name'] = actor['name'] if actor else 'System / Guest'
        log['actor_role'] = actor.get('role', 'N/A') if actor else 'N/A'
    
    # Recent Registered Teams
    recent_teams = list(teams_col.find().sort('created_at', -1).limit(5))
    
    return render_template(
        'super_admin/dashboard.html',
        stats=stats,
        system_status=system_status,
        recent_logs=recent_logs,
        recent_teams=recent_teams,
        event_settings=event_settings
    )


@super_admin_bp.route('/admins', methods=['GET', 'POST'])
@require_auth(roles=['super_admin'])
def manage_admins():
    """Admin management - Super Admin Only"""
    users_col = get_users_collection()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        phone = request.form.get('phone', '').strip()
        role = request.form.get('role', 'admin').strip().lower()
        
        # Super Admin can create 'admin' or 'super_admin'
        if role not in ['admin', 'super_admin']:
            role = 'admin'
            
        if not name or not email or not password:
            flash('Name, email, and password are required', 'error')
            return redirect(url_for('super_admin.manage_admins'))
        
        # Check duplicate
        if users_col.find_one({'email': email}):
            flash(f'An account with email {email} already exists', 'error')
            return redirect(url_for('super_admin.manage_admins'))
        
        new_admin = {
            'name': name,
            'email': email,
            'phone': phone or None,
            'password_hash': generate_password_hash(password),
            'role': role,
            'status': 'active',
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'created_by': session.get('user_id')
        }
        
        admin_id = users_col.insert_one(new_admin).inserted_id
        
        log_audit(
            session.get('user_id'),
            'admin_created',
            'user',
            str(admin_id),
            {'email': email, 'role': role, 'name': name}
        )
        
        flash(f'Admin account created for {name} ({email}) with role {role.upper()}', 'success')
        return redirect(url_for('super_admin.manage_admins'))
    
    # List all admin and super_admin accounts
    admins = list(users_col.find({'role': {'$in': ['admin', 'super_admin']}}).sort('created_at', -1))
    
    return render_template('super_admin/admins.html', admins=admins)


@super_admin_bp.route('/admins/<admin_id>/status', methods=['POST'])
@require_auth(roles=['super_admin'])
def toggle_admin_status(admin_id):
    """Activate or deactivate an Admin account"""
    users_col = get_users_collection()
    
    # Prevent modifying own account or super_admin if not allowed
    if admin_id == session.get('user_id'):
        flash('You cannot deactivate your own Super Admin account', 'error')
        return redirect(url_for('super_admin.manage_admins'))
    
    target = users_col.find_one({'_id': ObjectId(admin_id)})
    if not target:
        flash('Admin account not found', 'error')
        return redirect(url_for('super_admin.manage_admins'))
    
    new_status = 'inactive' if target.get('status') == 'active' else 'active'
    
    users_col.update_one(
        {'_id': ObjectId(admin_id)},
        {'$set': {'status': new_status, 'updated_at': datetime.utcnow()}}
    )
    
    log_audit(
        session.get('user_id'),
        'admin_status_updated',
        'user',
        admin_id,
        {'email': target['email'], 'new_status': new_status}
    )
    
    flash(f'Admin {target["name"]} is now {new_status.upper()}', 'success')
    return redirect(url_for('super_admin.manage_admins'))


@super_admin_bp.route('/admins/<admin_id>/reset-password', methods=['POST'])
@require_auth(roles=['super_admin'])
def reset_admin_password(admin_id):
    """Reset password for an Admin account"""
    users_col = get_users_collection()
    new_password = request.form.get('new_password', '').strip()
    
    if not new_password or len(new_password) < 6:
        flash('Password must be at least 6 characters', 'error')
        return redirect(url_for('super_admin.manage_admins'))
    
    target = users_col.find_one({'_id': ObjectId(admin_id)})
    if not target:
        flash('Admin account not found', 'error')
        return redirect(url_for('super_admin.manage_admins'))
    
    users_col.update_one(
        {'_id': ObjectId(admin_id)},
        {
            '$set': {
                'password_hash': generate_password_hash(new_password),
                'updated_at': datetime.utcnow()
            }
        }
    )
    
    log_audit(
        session.get('user_id'),
        'admin_password_reset',
        'user',
        admin_id,
        {'email': target['email']}
    )
    
    flash(f'Password reset successfully for {target["name"]}', 'success')
    return redirect(url_for('super_admin.manage_admins'))


@super_admin_bp.route('/audit-logs')
@require_auth(roles=['super_admin'])
def audit_logs():
    """View complete audit logs"""
    audit_col = get_audit_logs_collection()
    users_col = get_users_collection()
    
    page = int(request.args.get('page', 1))
    per_page = 30
    skip = (page - 1) * per_page
    
    action_filter = request.args.get('action', '')
    query = {}
    if action_filter:
        query['action'] = action_filter
        
    total_logs = audit_col.count_documents(query)
    logs = list(audit_col.find(query).sort('created_at', -1).skip(skip).limit(per_page))
    
    for log in logs:
        actor = None
        if log.get('actor_id'):
            try:
                actor = users_col.find_one({'_id': ObjectId(log['actor_id'])})
            except Exception:
                actor = users_col.find_one({'email': log['actor_id']})
        log['actor_name'] = actor['name'] if actor else 'System'
        log['actor_email'] = actor['email'] if actor else 'system'
        log['actor_role'] = actor.get('role', 'N/A') if actor else 'N/A'
    
    total_pages = (total_logs + per_page - 1) // per_page
    
    return render_template(
        'super_admin/audit_logs.html',
        logs=logs,
        total=total_logs,
        page=page,
        total_pages=total_pages,
        action_filter=action_filter
    )


@super_admin_bp.route('/system-settings', methods=['GET', 'POST'])
@require_auth(roles=['super_admin'])
def system_settings():
    """Manage global system and event settings"""
    settings_col = get_event_settings_collection()
    
    if request.method == 'POST':
        judging_locked = request.form.get('judging_locked') == 'on'
        results_published = request.form.get('results_published') == 'on'
        registration_open = request.form.get('registration_open') == 'on'
        bulk_credentials_enabled = request.form.get('bulk_credentials_enabled') == 'on'
        
        settings_col.update_one(
            {},
            {
                '$set': {
                    'judging_locked': judging_locked,
                    'results_published': results_published,
                    'registration_open': registration_open,
                    'bulk_credentials_enabled': bulk_credentials_enabled,
                    'updated_at': datetime.utcnow(),
                    'updated_by': session.get('user_id')
                }
            },
            upsert=True
        )

        from routes.teams import invalidate_registration_cache
        invalidate_registration_cache()

        log_audit(
            session.get('user_id'),
            'system_settings_updated',
            'settings',
            'global',
            {
                'judging_locked': judging_locked,
                'results_published': results_published,
                'registration_open': registration_open,
                'bulk_credentials_enabled': bulk_credentials_enabled
            }
        )
        
        flash('System settings updated successfully', 'success')
        return redirect(url_for('super_admin.system_settings'))
    
    settings = settings_col.find_one({}) or {}
    return render_template('super_admin/settings.html', settings=settings)
