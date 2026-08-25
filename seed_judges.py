"""
TechForge 3.0 — Official Jury Account Seeding & Pre-Provisioning Script
Pre-provisions the 25 official SRHU Internal Jury accounts,
generates cryptographically secure unique passwords, hashes them,
and delivers credentials to the official email addresses.

Idempotent: Running multiple times preserves existing accounts and passwords without changes.
"""

from datetime import datetime, timezone
from werkzeug.security import generate_password_hash

from app import create_app
from models.database import get_users_collection, get_judges_collection
from services.password_generator import generate_secure_jury_password
from services.email_service import send_jury_credentials_email

# 25 Official SRHU Staff Jury Members
OFFICIAL_INTERNAL_JUDGES = [
    # Group 1
    {'name': 'Dr. Neel Mani', 'email': 'neelmani@srhu.edu.in', 'is_coordinator': True},
    {'name': 'Er. Deepak Srivastava', 'email': 'deepaksrivastava@srhu.edu.in'},
    {'name': 'Er. Vivek Katiyar', 'email': 'vivekkatiyar@srhu.edu.in'},
    {'name': 'Dr. Shefali Khatri', 'email': 'shefalikhatri@srhu.edu.in'},
    {'name': 'Er. Sanjay Kumar', 'email': 'sanjaykumar@srhu.edu.in'},

    # Group 2
    {'name': 'Dr. L.K. Tyagi', 'email': 'lktyagi@srhu.edu.in'},
    {'name': 'Dr. Suman Pant', 'email': 'sumanpant@srhu.edu.in'},
    {'name': 'Er. A.K. Choudhary', 'email': 'akchoudhary@srhu.edu.in'},
    {'name': 'Er. Radhe Shankar', 'email': 'radheshankar@srhu.edu.in'},
    {'name': 'Dr. Gaurav Aggarwal', 'email': 'gauravaggarwal@srhu.edu.in'},

    # Group 3
    {'name': 'Dr. Rohit Kanauzia', 'email': 'rohitkanauzia@srhu.edu.in'},
    {'name': 'Dr. Anupama Mishra', 'email': 'anupamamishra@srhu.edu.in'},
    {'name': 'Dr. Shivpreet', 'email': 'shivpreet@srhu.edu.in'},
    {'name': 'Er. Rachit Lakhera', 'email': 'rachitlakhera@srhu.edu.in'},
    {'name': 'Er. Vinod Raturi', 'email': 'vinodraturi@srhu.edu.in'},

    # Group 4
    {'name': 'Dr. Ashutosh Bhatt', 'email': 'ashutoshbhatt@srhu.edu.in'},
    {'name': 'Dr. Shikha Singh', 'email': 'shikhasingh@srhu.edu.in'},
    {'name': 'Dr. Pooja Joshi', 'email': 'poojajoshi@srhu.edu.in'},
    {'name': 'Er. Vibhor Sharma', 'email': 'vibhorsharma@srhu.edu.in'},
    {'name': 'Er. Princy Tyagi', 'email': 'princytyagi@srhu.edu.in'},

    # Group 5
    {'name': 'Dr. Gunjan Chhabra', 'email': 'gunjanchhabra@srhu.edu.in'},
    {'name': 'Dr. Gaurav Sharma', 'email': 'gauravsharma@srhu.edu.in'},
    {'name': 'Dr. Vaishali Gupta', 'email': 'vaishaligupta@srhu.edu.in'},
    {'name': 'Dr. Shivani Pant', 'email': 'shivanipant@srhu.edu.in'},
    {'name': 'Dr. Neelam Danu', 'email': 'Neelamdanu@srhu.edu.in'},
]


def seed_judges(send_emails: bool = True):
    """
    Provision the 25 official Internal Jury members.
    Idempotent: preserves existing accounts and passwords without changing them.
    
    Args:
        send_emails: Whether to trigger credential email sending (default: True)
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
                    'updated_at': now
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
            print(f"[OK] {normalized_email} -- CREATED -- (email sending skipped)")

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
        seed_judges()
