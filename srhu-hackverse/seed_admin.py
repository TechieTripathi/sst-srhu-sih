"""
Run once to create the first Admin account:
    python seed_admin.py
Requires MONGO_URI to already be set in your environment / .env file.
"""
import getpass
from app import create_app
from models.user import create_user, find_by_email

app = create_app()

with app.app_context():
    print("=== SRHU HACKVERSE — Create Admin Account ===")
    name = input("Full name: ").strip()
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")

    if find_by_email(email):
        print("A user with this email already exists.")
    else:
        create_user(name, email, password, "admin")
        print(f"Admin account created for {email}.")
