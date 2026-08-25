"""
Judge Management Service
Handles judge account creation and delivery of login credentials.
"""

from datetime import datetime
from werkzeug.security import generate_password_hash
from bson.objectid import ObjectId

from models.database import get_users_collection, get_judges_collection
from services.audit import log_audit
from services.password_generator import generate_secure_jury_password
from services.email_service import send_jury_credentials_email


def create_judge(name, email, phone, judge_type, actor_id=None):
    """
    Create a new judge account with a freshly generated secure password.

    Args:
        name: Judge's full name
        email: Email address (login username)
        phone: Phone number
        judge_type: 'internal' or 'external'
        actor_id: User ID performing this action

    Returns:
        dict: {'success', 'judge_id', 'user_id', 'temp_password'} or {'error'}
    """
    users_col = get_users_collection()
    judges_col = get_judges_collection()

    email = email.strip().lower()
    if users_col.find_one({'email': email}):
        return {'error': 'Email already exists'}

    clean_type = str(judge_type).lower().replace('_judge', '')
    if clean_type not in ['internal', 'external']:
        return {'error': 'Invalid judge type. Must be "internal" or "external"'}
    db_judge_type = 'INTERNAL_JUDGE' if clean_type == 'internal' else 'EXTERNAL_JUDGE'

    temp_password = generate_secure_jury_password()
    now = datetime.utcnow()

    user_id = users_col.insert_one({
        'name': name,
        'email': email,
        'phone': phone,
        'password_hash': generate_password_hash(temp_password),
        'role': 'judge',
        'status': 'active',
        'credentials_sent': False,
        'created_at': now
    }).inserted_id

    judge_doc = {
        'user_id': str(user_id),
        'name': name,
        'email': email,
        'judge_type': db_judge_type,
        'status': 'active',
        'credentials_sent': False,
        'created_at': now
    }
    if db_judge_type == 'EXTERNAL_JUDGE':
        # External jury are guests who are often handed their sign-in details in
        # person on event day, so admins can copy the current password any time.
        # Internal (faculty) passwords are never stored in retrievable form.
        judge_doc['temp_password'] = temp_password
    judge_id = judges_col.insert_one(judge_doc).inserted_id

    log_audit(actor_id, 'judge_created', 'judge', str(judge_id),
              {'name': name, 'email': email, 'judge_type': db_judge_type})

    return {
        'success': True,
        'judge_id': str(judge_id),
        'user_id': str(user_id),
        'temp_password': temp_password
    }


def is_external_judge(judge):
    return 'external' in str((judge or {}).get('judge_type', '')).lower()


def regenerate_external_password(judge_id, actor_id=None):
    """External judges only: set a new password and store it so admins can copy it later."""
    users_col, judges_col = get_users_collection(), get_judges_collection()
    try:
        judge = judges_col.find_one({'_id': ObjectId(judge_id)})
    except Exception:
        judge = None
    if not judge:
        return {'success': False, 'error': 'Judge not found'}
    if not is_external_judge(judge):
        return {'success': False, 'error': 'Passwords can only be stored for external judges'}
    user = None
    try:
        user = users_col.find_one({'_id': ObjectId(judge.get('user_id'))})
    except Exception:
        pass
    user = user or users_col.find_one({'email': judge.get('email', '').lower()})
    if not user:
        return {'success': False, 'error': 'Judge user account not found'}
    new_password = generate_secure_jury_password()
    now = datetime.utcnow()
    users_col.update_one({'_id': user['_id']}, {'$set': {'password_hash': generate_password_hash(new_password), 'updated_at': now}})
    judges_col.update_one({'_id': judge['_id']}, {'$set': {'temp_password': new_password, 'password_generated_at': now}})
    log_audit(actor_id, 'judge_password_regenerated', 'judge', str(judge['_id']), {'email': user['email'], 'external': True})
    return {'success': True, 'password': new_password, 'email': user['email'], 'name': judge.get('name') or user.get('name')}


def send_judge_credentials(judge_id, recipient_email=None, actor_id=None, login_url=None):
    """
    Generate a NEW password for a judge and email the login credentials.

    The recipient defaults to the judge's own email; an admin may direct the
    email elsewhere (e.g. a coordinator who hands it over in person).

    Args:
        judge_id: judges collection _id (string)
        recipient_email: where to send; None → judge's own email
        actor_id: admin performing the action (audit)
        login_url: absolute URL of the jury login page

    Returns:
        dict: {'success': bool, 'password': str, 'recipient': str, 'error': str|None}
        'password' is always returned so the caller can show it once if email fails.
    """
    users_col = get_users_collection()
    judges_col = get_judges_collection()

    try:
        judge = judges_col.find_one({'_id': ObjectId(judge_id)})
    except Exception:
        judge = None
    if not judge:
        return {'success': False, 'error': 'Judge not found', 'password': None, 'recipient': None}

    user = None
    if judge.get('user_id'):
        try:
            user = users_col.find_one({'_id': ObjectId(judge['user_id'])})
        except Exception:
            user = None
    if not user:
        user = users_col.find_one({'email': judge.get('email', '').lower()})
    if not user:
        return {'success': False, 'error': 'Judge user account not found', 'password': None, 'recipient': None}

    recipient = (recipient_email or judge.get('email') or user['email']).strip().lower()
    to_judge_email = recipient == user['email'].lower()

    new_password = generate_secure_jury_password()
    now = datetime.utcnow()
    users_col.update_one({'_id': user['_id']},
                         {'$set': {'password_hash': generate_password_hash(new_password), 'updated_at': now}})

    send_res = send_jury_credentials_email(
        user['email'], new_password, login_url=login_url, judge_name=judge.get('name') or user.get('name'),
        deliver_to=recipient
    )
    # A 'simulated' result means SMTP isn't configured: nothing was actually
    # delivered, so report it as not sent and let the caller show the password.
    ok = bool(send_res.get('success')) and send_res.get('mode') != 'simulated'
    error = send_res.get('error') or (None if ok else 'SMTP_NOT_CONFIGURED')

    mark = {'credentials_sent': ok, 'credentials_sent_at': now if ok else None,
            'credentials_sent_to': recipient if ok else None}
    users_col.update_one({'_id': user['_id']}, {'$set': mark})
    judge_mark = dict(mark)
    if is_external_judge(judge):
        judge_mark['temp_password'] = new_password
    judges_col.update_one({'_id': judge['_id']}, {'$set': judge_mark})

    log_audit(actor_id, 'judge_credentials_sent' if ok else 'judge_credentials_send_failed',
              'judge', str(judge['_id']),
              {'recipient': recipient, 'to_judge_email': to_judge_email, 'error': error})

    return {'success': ok, 'password': new_password, 'recipient': recipient, 'error': error}


def reset_judge_password(judge_id, actor_id=None):
    """
    Generate a NEW password for a judge WITHOUT emailing it — for handing over
    in person / copying from the admin screen. Returns {'success','password','name','email'}.
    """
    users_col = get_users_collection()
    judges_col = get_judges_collection()
    try:
        judge = judges_col.find_one({'_id': ObjectId(judge_id)})
    except Exception:
        judge = None
    if not judge:
        return {'success': False, 'error': 'Judge not found'}
    user = None
    if judge.get('user_id'):
        try:
            user = users_col.find_one({'_id': ObjectId(judge['user_id'])})
        except Exception:
            user = None
    if not user:
        user = users_col.find_one({'email': judge.get('email', '').lower()})
    if not user:
        return {'success': False, 'error': 'Judge user account not found'}

    new_password = generate_secure_jury_password()
    now = datetime.utcnow()
    users_col.update_one({'_id': user['_id']},
                         {'$set': {'password_hash': generate_password_hash(new_password), 'updated_at': now}})
    log_audit(actor_id, 'judge_password_regenerated', 'judge', str(judge['_id']),
              {'email': user['email'], 'delivery': 'shown_on_screen'})
    return {'success': True, 'password': new_password, 'name': judge.get('name') or user.get('name'), 'email': user['email']}
