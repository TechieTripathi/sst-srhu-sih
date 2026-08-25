"""
Team document shape (collection: teams)

{
    "_id": ObjectId,
    "team_id": str,             # human-friendly unique code, e.g. "T-2026-014"
    "team_name": str,
    "project_name": str,
    "track": str,
    "problem_statement": str,
    "solution": str,
    "technologies": [str],
    "members": [{"name": str, "email": str, "role": str}],
    "presentation_slot": str,
    "status": "registered" | "checked_in" | "presenting" | "done",
    "created_at": datetime,
    "updated_at": datetime,
}
"""

from datetime import datetime, timezone
from bson import ObjectId
from models.db import get_db


def list_teams(track=None, status=None):
    db = get_db()
    if db is None:
        return []
    query = {}
    if track:
        query["track"] = track
    if status:
        query["status"] = status
    return list(db.teams.find(query).sort("team_name", 1))


def get_team(team_id):
    db = get_db()
    if db is None:
        return None
    try:
        return db.teams.find_one({"_id": ObjectId(team_id)})
    except Exception:
        return db.teams.find_one({"team_id": team_id})


def create_team(data):
    db = get_db()
    if db is None:
        return None
    now = datetime.now(timezone.utc)
    data["status"] = data.get("status", "registered")
    data["created_at"] = now
    data["updated_at"] = now
    result = db.teams.insert_one(data)
    data["_id"] = result.inserted_id
    return data


def update_team(team_id, updates):
    db = get_db()
    if db is None:
        return False
    updates["updated_at"] = datetime.now(timezone.utc)
    res = db.teams.update_one({"_id": ObjectId(team_id)}, {"$set": updates})
    return res.modified_count > 0


def delete_team(team_id):
    db = get_db()
    if db is None:
        return False
    res = db.teams.delete_one({"_id": ObjectId(team_id)})
    return res.deleted_count > 0


def count_teams():
    db = get_db()
    if db is None:
        return 0
    return db.teams.count_documents({})
