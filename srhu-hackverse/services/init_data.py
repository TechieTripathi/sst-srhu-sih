"""
Initialize database with evaluation criteria and create a default admin user
Run this script once to set up the system
"""

from datetime import datetime
from werkzeug.security import generate_password_hash
from models.database import (
    get_evaluation_criteria_collection,
    get_users_collection,
    get_event_settings_collection
)
from config import Config


def init_evaluation_criteria():
    """Initialize evaluation criteria from config"""
    criteria_col = get_evaluation_criteria_collection()
    
    # Check if already initialized
    if criteria_col.count_documents({}) > 0:
        print("Evaluation criteria already initialized")
        return
    
    criteria = []
    for idx, c in enumerate(Config.EVALUATION_CRITERIA, 1):
        criteria.append({
            'criterion_id': c['id'],
            'name': c['name'],
            'weight': c['weight'],
            'description': c['description'],
            'max_score': Config.RAW_SCORE_MAX,
            'min_score': Config.RAW_SCORE_MIN,
            'order': idx,
            'active': True,
            'created_at': datetime.utcnow()
        })
    
    criteria_col.insert_many(criteria)
    print(f"[OK] Initialized {len(criteria)} evaluation criteria")


def create_super_admin_user(email=None, password=None, name=None):
    """Create default Super Admin user idempotently"""
    users_col = get_users_collection()
    
    super_email = (email or Config.SUPER_ADMIN_EMAIL).strip().lower()
    super_pass = password or Config.SUPER_ADMIN_PASSWORD
    super_name = name or Config.SUPER_ADMIN_NAME
    
    existing = users_col.find_one({'email': super_email})
    if existing:
        if existing.get('role') != 'super_admin':
            users_col.update_one(
                {'_id': existing['_id']},
                {'$set': {'role': 'super_admin', 'status': 'active', 'updated_at': datetime.utcnow()}}
            )
            print(f"[OK] Upgraded existing user {super_email} to super_admin role")
        else:
            print(f"Super Admin user {super_email} already exists")
        return
    
    super_admin_user = {
        'name': super_name,
        'email': super_email,
        'phone': None,
        'password_hash': generate_password_hash(super_pass),
        'role': 'super_admin',
        'status': 'active',
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    }
    
    users_col.insert_one(super_admin_user)
    print(f"[OK] Created Super Admin user: {super_email}")


def create_admin_user(email='admin@srhu.edu.in', password='admin123', name='System Administrator'):
    """Create default admin user"""
    users_col = get_users_collection()
    
    # Check if admin already exists
    if users_col.find_one({'email': email}):
        print(f"Admin user {email} already exists")
        return
    
    admin_user = {
        'name': name,
        'email': email,
        'phone': None,
        'password_hash': generate_password_hash(password),
        'role': 'admin',
        'status': 'active',
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    }
    
    users_col.insert_one(admin_user)
    print(f"[OK] Created admin user: {email} / {password}")


def init_event_settings():
    """Initialize event settings"""
    settings_col = get_event_settings_collection()
    
    # Check if already initialized
    if settings_col.count_documents({}) > 0:
        print("Event settings already initialized")
        return
    
    settings = {
        'judging_locked': False,
        'results_published': False,
        'registration_open': True,
        'evaluation_stages': [
            {
                'stage_id': 'checkpoint_1',
                'name': 'Checkpoint 1',
                'scheduled_time': '2026-08-26T12:00:00',
                'weight': 0.10,
                'description': '10% of ground (internal) evaluation'
            },
            {
                'stage_id': 'checkpoint_2',
                'name': 'Checkpoint 2',
                'scheduled_time': '2026-08-26T16:00:00',
                'weight': 0.10,
                'description': '10% of ground (internal) evaluation'
            },
            {
                'stage_id': 'checkpoint_3',
                'name': 'Checkpoint 3',
                'scheduled_time': '2026-08-26T22:00:00',
                'weight': 0.10,
                'description': '10% of ground (internal) evaluation'
            },
            {
                'stage_id': 'checkpoint_4',
                'name': 'Checkpoint 4',
                'scheduled_time': '2026-08-27T02:00:00',
                'weight': 0.20,
                'description': '20% of ground (internal) evaluation'
            },
            {
                'stage_id': 'checkpoint_5',
                'name': 'Checkpoint 5',
                'scheduled_time': '2026-08-26T10:00:00',
                'weight': 0.10,
                'description': '10% of ground (internal) evaluation'
            },
            {
                'stage_id': 'final_presentation',
                'name': 'Final Presentation',
                'scheduled_time': '2026-08-27T13:00:00',
                'weight': 0.40,
                'description': '40% final Evaluation'
            }
        ],
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    }
    
    settings_col.insert_one(settings)
    print("[OK] Initialized event settings with evaluation stages")


def init_database():
    """Initialize all database collections and data"""
    print("\n=== Initializing TechForge 3.0 Database ===\n")
    
    init_evaluation_criteria()
    create_super_admin_user()
    create_admin_user()
    init_event_settings()
    
    print("\n[OK] Database initialization complete!")
    print("\n--- Default Credentials ---")
    print("Super Admin: superadmin@srhu.edu.in / superadmin123")
    print("Admin:       admin@srhu.edu.in / admin123")
    print("\nPlease change passwords after first login in production.\n")


if __name__ == '__main__':
    # This requires the Flask app context
    from app import app
    with app.app_context():
        init_database()
