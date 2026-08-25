"""
Seed Super Admin Account
TechForge 3.0 Platform - SRHU SST

Run this script to initialize or verify the Super Admin account idempotently:
    python seed_super_admin.py
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from app import create_app
from services.init_data import create_super_admin_user
from config import Config

def seed():
    app = create_app()
    with app.app_context():
        email = os.environ.get('SUPER_ADMIN_EMAIL', getattr(Config, 'SUPER_ADMIN_EMAIL', 'superadmin@srhu.edu.in'))
        print("\n=== TechForge 3.0: Super Admin Seeding ===")
        print(f"Target Email: {email}")
        create_super_admin_user()
        print("=== Done ===\n")

if __name__ == '__main__':
    seed()
