from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from bson.objectid import ObjectId
import re
import threading
import time

from models.database import get_teams_collection, get_users_collection, get_event_settings_collection
from services.audit import log_audit

teams_bp = Blueprint('teams', __name__)


# Every page render asks for this through the inject_globals context processor, so
# an uncached lookup puts a MongoDB round trip on the critical path of the landing
# page - which otherwise touches no data at all. The value only changes when an
# admin flips the switch, and those routes call invalidate_registration_cache(),
# so the short TTL is just a backstop for changes made outside the app.
_REG_CACHE_TTL_SECONDS = 15.0
_reg_cache = {'value': None, 'fetched_at': 0.0}
_reg_cache_lock = threading.Lock()


def invalidate_registration_cache():
    """Drop the cached switch so the next render re-reads it from MongoDB."""
    with _reg_cache_lock:
        _reg_cache['value'] = None
        _reg_cache['fetched_at'] = 0.0


def is_registration_open():
    """Admin/Super Admin switch 'registration_open' in event_settings (default: open)."""
    now = time.monotonic()

    with _reg_cache_lock:
        cached = _reg_cache['value']
        if cached is not None and now - _reg_cache['fetched_at'] < _REG_CACHE_TTL_SECONDS:
            return cached

    # Queried outside the lock on purpose: holding it here would serialise every
    # worker thread behind one network call. A rare duplicate fetch is cheaper.
    try:
        settings = get_event_settings_collection().find_one(
            {}, {'registration_open': 1}
        ) or {}
        value = bool(settings.get('registration_open', True))
    except Exception:
        return True

    with _reg_cache_lock:
        _reg_cache['value'] = value
        _reg_cache['fetched_at'] = now
    return value


@teams_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Team registration page (enforces the registration_open switch)"""
    if not is_registration_open():
        if request.method == 'POST':
            flash('Team registration is closed.', 'error')
        return render_template('teams/registration_closed.html'), 403

    if request.method == 'POST':
        # Get form data
        leader_name = request.form.get('leader_name', '').strip()
        team_name = request.form.get('team_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        mobile = request.form.get('mobile', '').strip()
        
        # Validate required fields
        if not all([leader_name, team_name, email, mobile]):
            flash('All fields are required', 'error')
            return render_template('teams/register.html')
        
        # Validate email format
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            flash('Invalid email format', 'error')
            return render_template('teams/register.html')
        
        # Validate mobile format (basic)
        mobile_pattern = r'^\d{10}$'
        if not re.match(mobile_pattern, mobile):
            flash('Invalid mobile number. Please enter 10 digits.', 'error')
            return render_template('teams/register.html')
        
        teams = get_teams_collection()
        users = get_users_collection()
        
        # Check for duplicate team name
        if teams.find_one({'team_name': team_name}):
            flash('Team name already exists. Please choose a different name.', 'error')
            return render_template('teams/register.html')
        
        # Check for duplicate email
        if users.find_one({'email': email}):
            flash('Email already registered', 'error')
            return render_template('teams/register.html')
        
        # Generate team code
        import random
        import string
        team_code = 'TF3-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # Create user (student leader)
        from werkzeug.security import generate_password_hash
        leader_user = {
            'name': leader_name,
            'email': email,
            'phone': mobile,
            'password_hash': generate_password_hash('welcome123'),  # Default password
            'role': 'student_leader',
            'status': 'active',
            'created_at': datetime.utcnow()
        }
        
        leader_id = users.insert_one(leader_user).inserted_id
        
        # Create team
        team = {
            'team_name': team_name,
            'team_code': team_code,
            'leader_id': str(leader_id),
            'leader_name': leader_name,
            'leader_email': email,
            'leader_mobile': mobile,
            'status': 'registered',
            'category': None,  # To be filled later
            'problem_statement': None,
            'created_at': datetime.utcnow()
        }
        
        team_id = teams.insert_one(team).inserted_id
        
        # Log audit
        log_audit(
            str(leader_id),
            'team_registration',
            'team',
            str(team_id),
            {'team_name': team_name, 'team_code': team_code}
        )
        
        session['registration_success'] = True
        session['registered_team_code'] = team_code
        flash('Registration successful!', 'success')
        return redirect(url_for('teams.registration_success', team_code=team_code))
    
    return render_template('teams/register.html')


@teams_bp.route('/registration-success')
def registration_success():
    """Registration success page - only accessible after a successful registration"""
    if not session.get('registration_success'):
        return redirect(url_for('index'))
    
    team_code = session.pop('registered_team_code', None) or request.args.get('team_code')
    session.pop('registration_success', None)
    return render_template('teams/registration_success.html', team_code=team_code)
