"""
Jury document shape (collection: jury)

{
    "_id": ObjectId,
    "jury_id": str,
    "user_id": ObjectId,        # link to users collection (login identity)
    "name": str,
    "email": str,
    "designation": str,
    "organization": str,
    "expertise": [str],
    "assigned_teams": [ObjectId],
    "status": "active" | "inactive",
}

Assignment document shape (collection: assignments)
{
    "_id": ObjectId,
    "jury_id": ObjectId,
    "team_id": ObjectId,
    "assigned_at": datetime,
}
"""

from datetime import datetime, timezone
from bson import ObjectId
from models.db import get_db


def list_jury():
    db = get_db()
    if db is None:
        return []
    return list(db.jury.find().sort("name", 1))


def get_jury_by_user_id(user_id):
    db = get_db()
    if db is None:
        return None
    return db.jury.find_one({"user_id": ObjectId(user_id)})


def create_jury(data):
    db = get_db()
    if db is None:
        return None
    data["assigned_teams"] = data.get("assigned_teams", [])
    data["status"] = data.get("status", "active")
    result = db.jury.insert_one(data)
    data["_id"] = result.inserted_id
    return data


def assign_team(jury_id, team_id):
    db = get_db()
    if db is None:
        return False
    now = datetime.now(timezone.utc)
    db.assignments.update_one(
        {"jury_id": ObjectId(jury_id), "team_id": ObjectId(team_id)},
        {"$setOnInsert": {"assigned_at": now}},
        upsert=True,
    )
    db.jury.update_one(
        {"_id": ObjectId(jury_id)},
        {"$addToSet": {"assigned_teams": ObjectId(team_id)}},
    )
    return True


def get_assigned_teams(jury_id):
    db = get_db()
    if db is None:
        return []
    jury_doc = db.jury.find_one({"_id": ObjectId(jury_id)})
    if not jury_doc or not jury_doc.get("assigned_teams"):
        return []
    return list(db.teams.find({"_id": {"$in": jury_doc["assigned_teams"]}}))


def is_team_assigned_to_jury(jury_id, team_id):
    db = get_db()
    if db is None:
        return False
    return db.assignments.find_one(
        {"jury_id": ObjectId(jury_id), "team_id": ObjectId(team_id)}
    ) is not None


def count_jury():
    db = get_db()
    if db is None:
        return 0
    return db.jury.count_documents({})
