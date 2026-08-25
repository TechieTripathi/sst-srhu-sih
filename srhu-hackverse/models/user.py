"""
User document shape (collection: users)

{
    "_id": ObjectId,
    "name": str,
    "email": str,           # unique, lowercased
    "password_hash": str,
    "role": "admin" | "jury" | "team",
    "status": "active" | "disabled",
    "created_at": datetime,
    "updated_at": datetime,
}
"""

from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from models.db import get_db

ROLES = ("admin", "jury", "team")


def create_user(name, email, password, role):
    db = get_db()
    if db is None:
        return None
    if role not in ROLES:
        raise ValueError("Invalid role")

    doc = {
        "name": name.strip(),
        "email": email.strip().lower(),
        "password_hash": generate_password_hash(password),
        "role": role,
        "status": "active",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


def find_by_email(email):
    db = get_db()
    if db is None:
        return None
    return db.users.find_one({"email": email.strip().lower()})


def find_by_id(user_id):
    db = get_db()
    if db is None:
        return None
    from bson import ObjectId
    try:
        return db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None


def verify_password(user_doc, password):
    if not user_doc:
        return False
    return check_password_hash(user_doc["password_hash"], password)
