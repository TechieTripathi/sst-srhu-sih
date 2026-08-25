"""
Seed the Admin (operations team) account — TechForge 3.0

    python admin_seed.py                              # uses ADMIN_* from .env, else defaults
    python admin_seed.py ops@srhu.edu.in 'Str0ngPass' 'Ops Team'
    python admin_seed.py --reset                      # also reset the password if the account exists

Idempotent: an existing account is left untouched unless --reset is given.
Defaults (dev only, change before the event): admin@srhu.edu.in / admin123
"""
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from werkzeug.security import generate_password_hash
from app import create_app
from models.database import get_users_collection
from services.audit import log_audit


def seed_admin(email, password, name, reset=False):
    users = get_users_collection()
    email = email.strip().lower()
    existing = users.find_one({'email': email})
    now = datetime.utcnow()

    if existing and not reset:
        print(f"[OK] Admin already exists: {email} (role={existing.get('role')}, status={existing.get('status')}) — unchanged")
        return 'exists'

    if existing:
        users.update_one({'_id': existing['_id']}, {'$set': {
            'name': name, 'password_hash': generate_password_hash(password),
            'role': 'admin', 'status': 'active', 'updated_at': now}})
        log_audit(None, 'admin_password_reset', 'user', str(existing['_id']), {'email': email, 'via': 'admin_seed.py'})
        print(f"[RESET] Admin password updated: {email}")
        return 'reset'

    uid = users.insert_one({
        'name': name, 'email': email, 'phone': None,
        'password_hash': generate_password_hash(password),
        'role': 'admin', 'status': 'active', 'created_at': now, 'updated_at': now,
    }).inserted_id
    log_audit(None, 'admin_created', 'user', str(uid), {'email': email, 'role': 'admin', 'via': 'admin_seed.py'})
    print(f"[CREATED] Admin account: {email}")
    return 'created'


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    reset = '--reset' in sys.argv
    email = args[0] if len(args) > 0 else os.environ.get('ADMIN_EMAIL', 'admin@srhu.edu.in')
    password = args[1] if len(args) > 1 else os.environ.get('ADMIN_PASSWORD', 'admin123')
    name = args[2] if len(args) > 2 else os.environ.get('ADMIN_NAME', 'Operations Admin')

    print("\n=== TechForge 3.0: Admin (operations) seeding ===")
    print(f"Email : {email}\nName  : {name}\nLogin : /auth/login  ->  /admin")
    with create_app().app_context():
        seed_admin(email, password, name, reset=reset)
    if password == 'admin123':
        print("[WARN] Default password in use — set ADMIN_PASSWORD in .env and re-run with --reset before the event.")
    print("=== Done ===\n")
