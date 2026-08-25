"""
TechForge 3.0 — API Blueprint
Contains endpoints for:
- Normal Jury Login with Email + Password (NO OTP)
- Session handling and system status.
"""

from flask import Blueprint, jsonify, request, session
from services.otp_service import authenticate_jury_credentials
from services.email_service import get_email_status
from routes.auth import require_auth

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/auth/judge/login', methods=['POST'])
def api_judge_login():
    """
    POST /api/auth/judge/login
    Jury Login endpoint via Email + Password.
    Input: JSON {"email": "...", "password": "..."}
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    client_ip = request.remote_addr

    result = authenticate_jury_credentials(email, password, client_ip)
    status_code = result.get('status_code', 200 if result.get('success') else 401)

    if result.get('success'):
        session.permanent = True
        session['user_id'] = result['user_id']
        session['name'] = result['name']
        session['email'] = result['email']
        session['role'] = 'JUDGE'
        session['judge_type'] = result.get('judge_type', 'INTERNAL_JUDGE')

        return jsonify({
            'success': True,
            'message': 'Login successful.',
            'redirect_url': '/judge/dashboard',
            'user': {
                'name': result['name'],
                'email': result['email'],
                'role': 'JUDGE',
                'judge_type': result['judge_type']
            }
        }), 200

    return jsonify({
        'success': False,
        'message': result.get('message', 'Invalid email or password.')
    }), status_code


@api_bp.route('/auth/logout', methods=['POST'])
def api_logout():
    """
    POST /api/auth/logout
    Invalidates current session
    """
    from services.audit import log_audit
    user_id = session.get('user_id')
    if user_id:
        log_audit(user_id, 'JUDGE_LOGOUT', 'judge', user_id)
    session.clear()
    return jsonify({
        'success': True,
        'message': 'Logged out successfully.',
        'redirect_url': '/judge/login'
    }), 200


@api_bp.route('/system/email-status', methods=['GET'])
@require_auth(roles=['super_admin'])
def api_email_status():
    """
    GET /api/system/email-status
    Health check for email service (Super Admin restricted)
    """
    status = get_email_status()
    return jsonify(status), 200
