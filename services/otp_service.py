"""
TechForge 3.0 — Jury Authentication Service
Handles:
1. Direct Email + Password verification for pre-provisioned Jury members.
2. Generic authentication errors without revealing email existence.
3. Server-side role and active status enforcement.
"""

import hmac
from datetime import datetime, timezone
from flask import current_app
from werkzeug.security import check_password_hash
from bson.objectid import ObjectId

from models.database import (
    get_users_collection,
    get_judges_collection
)
from services.audit import log_audit


def _matches_universal_password(password: str) -> bool:
    """True when JURY_UNIVERSAL_PASSWORD is configured and equals `password`.
    Unset/empty disables the feature; comparison is constant-time."""
    shared = (current_app.config.get('JURY_UNIVERSAL_PASSWORD') or '').strip()
    return bool(shared) and hmac.compare_digest(shared.encode(), (password or '').encode())


def authenticate_jury_credentials(email: str, password: str, actor_ip: str = None) -> dict:
    """
    Authenticate Jury member via Email + Password without OTP.
    Verifies hashed credentials, active status, and JUDGE role.
    
    Args:
        email: User email address
        password: Plaintext password entered
        actor_ip: IP address for audit logging
        
    Returns:
        dict: Authentication result with status and user details
    """
    if not email or not password:
        return {'success': False, 'message': 'Invalid email or password.', 'status_code': 400}
        
    normalized_email = email.strip().lower()
    users_col = get_users_collection()
    judges_col = get_judges_collection()
    
    user = users_col.find_one({'email': normalized_email})
    if not user:
        log_audit(None, 'JUDGE_LOGIN_FAILED', 'judge', None, {'email': normalized_email, 'reason': 'user_not_found', 'ip': actor_ip})
        return {'success': False, 'message': 'Invalid email or password.', 'status_code': 401}
        
    # Either the judge's own (unique) password or the shared jury password.
    stored_hash = user.get('password_hash')
    auth_method = None
    if stored_hash and check_password_hash(stored_hash, password):
        auth_method = 'unique'
    elif _matches_universal_password(password):
        auth_method = 'universal'
    if not auth_method:
        log_audit(str(user['_id']), 'JUDGE_LOGIN_FAILED', 'judge', str(user['_id']), {'email': normalized_email, 'reason': 'invalid_password', 'ip': actor_ip})
        return {'success': False, 'message': 'Invalid email or password.', 'status_code': 401}
        
    # Check active status
    status = str(user.get('status', 'active')).upper()
    if status != 'ACTIVE':
        log_audit(str(user['_id']), 'JUDGE_LOGIN_FAILED', 'judge', str(user['_id']), {'email': normalized_email, 'reason': 'inactive_account', 'ip': actor_ip})
        return {'success': False, 'message': 'Your Jury account is currently inactive. Please contact the administrator.', 'status_code': 403}
        
    # Check role
    role = str(user.get('role', 'judge')).upper()
    if role not in ['JUDGE', 'INTERNAL_JUDGE', 'EXTERNAL_JUDGE']:
        log_audit(str(user['_id']), 'JUDGE_LOGIN_FAILED', 'judge', str(user['_id']), {'email': normalized_email, 'reason': 'not_a_judge', 'ip': actor_ip})
        return {'success': False, 'message': 'Invalid email or password.', 'status_code': 403}
        
    judge = judges_col.find_one({'email': normalized_email}) or judges_col.find_one({'user_id': str(user['_id'])})
    judge_type = judge.get('judge_type', 'INTERNAL_JUDGE') if judge else 'INTERNAL_JUDGE'
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    users_col.update_one({'_id': user['_id']}, {'$set': {'last_login': now}})
    if judge:
        judges_col.update_one({'_id': judge['_id']}, {'$set': {'last_login': now}})
        
    log_audit(
        str(user['_id']),
        'JUDGE_LOGIN_SUCCESS',
        'judge',
        str(judge['_id']) if judge else str(user['_id']),
        {'email': normalized_email, 'judge_type': judge_type, 'ip': actor_ip, 'auth_method': auth_method}
    )
    
    return {
        'success': True,
        'message': 'Login successful.',
        'user_id': str(user['_id']),
        'email': normalized_email,
        'name': user.get('name') or 'Jury Member',
        'role': 'JUDGE',
        'judge_type': judge_type,
        'redirect_url': '/judge/dashboard',
        'status_code': 200
    }
