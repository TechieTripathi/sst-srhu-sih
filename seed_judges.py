"""
TechForge 3.0 — Official Jury Account Seeding Script
Pre-provisions the 25 official SRHU Internal Jury accounts in the database with
secure, hashed passwords. It does NOT email anyone by default — send sign-in
details later from Admin → Judges (per judge, or batched), where delivery is
tracked and failures are shown.

    python seed_judges.py            # database only (default)
    python seed_judges.py --email    # also email each newly created judge

Idempotent: existing accounts and passwords are never changed.
"""
import sys

from datetime import datetime, timezone
from werkzeug.security import generate_password_hash

from app import create_app
from models.database import get_users_collection, get_judges_collection
from services.password_generator import generate_secure_jury_password
from services.email_service import send_jury_credentials_email

# The 25 jury members who have a real SRHU mailbox, from the shared roster in
# services/jury_roster.py. Kept under this name and at exactly 25 entries
# because tests/test_jury_credentials.py imports it and asserts the count.
#
# The three outside guests are deliberately absent: they have placeholder
# addresses and their credentials are shown on screen, never emailed. They are
# provisioned by migrate_jury_panels.py.
from services.jury_roster import MAILBOX_JURY, EXCEPTION_JURY, GROUP_JURY

OFFICIAL_INTERNAL_JUDGES = MAILBOX_JURY

# email -> the panel/scope fields to stamp, so a freshly seeded database comes
# out already correct instead of needing the migration.
_SCOPE_BY_EMAIL = {}
for _j in EXCEPTION_JURY:
    _SCOPE_BY_EMAIL[_j['email'].strip().lower()] = {
        'jury_scope': 'all_teams', 'credentials_deliverable': True,
    }
for _j in GROUP_JURY:
    _SCOPE_BY_EMAIL[_j['email'].strip().lower()] = {
        'jury_scope': 'assigned_only',
        'panel_no': _j['panel_no'],
        'credentials_deliverable': _j.get('has_mailbox', True),
    }


def seed_judges(send_emails: bool = False):
    """
    Provision the 25 official Internal Jury members.
    Idempotent: preserves existing accounts and passwords without changing them.
    
    Args:
        send_emails: Email each new judge their password (default: False — use the admin panel instead)
    """
    print("\nJury Provisioning Started\n" + "=" * 55)

    users_col = get_users_collection()
    judges_col = get_judges_collection()

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Provision the 25 Official Jury Accounts
    total_judges = len(OFFICIAL_INTERNAL_JUDGES)
    created_count = 0
    existing_count = 0
    emails_sent_count = 0
    failed_emails_count = 0

    for judge_info in OFFICIAL_INTERNAL_JUDGES:
        name = judge_info['name']
        normalized_email = judge_info['email'].strip().lower()
        is_coord = judge_info.get('is_coordinator', False)

        # Check if user already exists
        existing_user = users_col.find_one({'email': normalized_email})
        existing_judge = judges_col.find_one({'email': normalized_email})

        if existing_user and existing_user.get('password_hash'):
            existing_count += 1
            print(f"[OK] {normalized_email} -- ALREADY EXISTS -- SKIPPED")
            continue

        # Generate a unique secure random password
        temp_password = generate_secure_jury_password()
        hashed_password = generate_password_hash(temp_password)

        if existing_user:
            # Update user with generated password hash
            users_col.update_one(
                {'_id': existing_user['_id']},
                {
                    '$set': {
                        'name': name,
                        'password_hash': hashed_password,
                        'role': 'JUDGE',
                        'judge_type': 'INTERNAL_JUDGE',
                        'status': 'ACTIVE',
                        'updated_at': now
                    }
                }
            )
            user_id = str(existing_user['_id'])
        else:
            # Create fresh user account in users collection
            user_doc = {
                'name': name,
                'email': normalized_email,
                'password_hash': hashed_password,
                'role': 'JUDGE',
                'judge_type': 'INTERNAL_JUDGE',
                'status': 'ACTIVE',
                'credentials_sent': False,
                'created_at': now,
                'updated_at': now
            }
            user_id = str(users_col.insert_one(user_doc).inserted_id)

        # Upsert in judges collection
        judges_col.update_one(
            {'email': normalized_email},
            {
                '$set': {
                    'user_id': user_id,
                    'name': name,
                    'email': normalized_email,
                    'judge_type': 'INTERNAL_JUDGE',
                    'status': 'ACTIVE',
                    'is_overall_jury_coordinator': is_coord,
                    'updated_at': now,
                    # Panel and scope, so a fresh database is correct without
                    # needing migrate_jury_panels.py. Existing databases are
                    # stamped by that script instead - the early `continue`
                    # above means this block never runs for them.
                    **_SCOPE_BY_EMAIL.get(normalized_email, {}),
                },
                '$setOnInsert': {
                    'credentials_sent': False,
                    'created_at': now
                }
            },
            upsert=True
        )

        created_count += 1

        # Deliver credentials email if enabled
        if send_emails:
            send_res = send_jury_credentials_email(normalized_email, temp_password, judge_name=name)
            if send_res.get('success'):
                emails_sent_count += 1
                users_col.update_one({'_id': existing_user['_id'] if existing_user else users_col.find_one({'email': normalized_email})['_id']}, {'$set': {'credentials_sent': True, 'credentials_sent_at': now}})
                judges_col.update_one({'email': normalized_email}, {'$set': {'credentials_sent': True, 'credentials_sent_at': now}})
                print(f"[OK] {normalized_email} -- CREATED -- credentials email sent")
            else:
                failed_emails_count += 1
                judges_col.update_one({'email': normalized_email}, {'$set': {'credentials_sent': False, 'credential_send_error': 'EMAIL_SEND_FAILED'}})
                print(f"[WARN] {normalized_email} -- CREATED -- email delivery failed")
        else:
            print(f"[OK] {normalized_email} -- CREATED -- not emailed (send from Admin → Judges)")

    print("\n" + "-" * 55)
    print("Summary:")
    print(f"Total Jury Accounts:      {total_judges}")
    print(f"Created:                  {created_count}")
    print(f"Existing:                 {existing_count}")
    print(f"Credential Emails Sent:   {emails_sent_count}")
    print(f"Failed Emails:            {failed_emails_count}")
    print("=" * 55 + "\n")


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        seed_judges(send_emails='--email' in sys.argv)
