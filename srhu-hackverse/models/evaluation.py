"""
Criteria document shape (collection: criteria)
{
    "_id": ObjectId,
    "hackathon_id": str,
    "name": str,
    "description": str,
    "max_score": int,     # default 10
    "order": int,
    "active": bool,
}

Evaluation document shape (collection: evaluations) — one per (jury, team)
{
    "_id": ObjectId,
    "team_id": ObjectId,
    "jury_id": ObjectId,
    "scores": [{"criterion_id": ObjectId, "criterion_name": str, "score": int, "max_score": int}],
    "total_score": float,
    "max_total": float,
    "percentage": float,
    "comments": str,
    "status": "in_progress" | "submitted",
    "submitted_at": datetime | None,
    "created_at": datetime,
    "updated_at": datetime,
}
"""

from datetime import datetime, timezone
from bson import ObjectId
from models.db import get_db

DEFAULT_CRITERIA = [
    {"name": "Innovation", "description": "Originality and differentiation of the idea.", "max_score": 10, "order": 1},
    {"name": "Problem Relevance", "description": "Clarity and relevance of the problem addressed.", "max_score": 10, "order": 2},
    {"name": "Technical Implementation", "description": "Quality and robustness of the technical build.", "max_score": 10, "order": 3},
    {"name": "Creativity", "description": "Creative approach to the solution.", "max_score": 10, "order": 4},
    {"name": "Feasibility", "description": "Practicality of real-world implementation.", "max_score": 10, "order": 5},
    {"name": "Scalability", "description": "Ability to scale to more users/data.", "max_score": 10, "order": 6},
    {"name": "User Experience", "description": "Usability and design quality.", "max_score": 10, "order": 7},
    {"name": "Social/Real-World Impact", "description": "Potential positive impact.", "max_score": 10, "order": 8},
    {"name": "Presentation", "description": "Clarity and quality of the pitch.", "max_score": 10, "order": 9},
    {"name": "Overall Solution Quality", "description": "Holistic quality of the solution.", "max_score": 10, "order": 10},
]


def get_active_criteria(hackathon_id=None):
    db = get_db()
    if db is None:
        return []
    query = {"active": True}
    if hackathon_id:
        query["hackathon_id"] = hackathon_id
    criteria = list(db.criteria.find(query).sort("order", 1))
    return criteria


def seed_default_criteria(hackathon_id):
    db = get_db()
    if db is None:
        return
    if db.criteria.count_documents({"hackathon_id": hackathon_id}) > 0:
        return
    docs = []
    for c in DEFAULT_CRITERIA:
        doc = dict(c)
        doc["hackathon_id"] = hackathon_id
        doc["active"] = True
        docs.append(doc)
    db.criteria.insert_many(docs)


def get_evaluation(jury_id, team_id):
    db = get_db()
    if db is None:
        return None
    return db.evaluations.find_one({
        "jury_id": ObjectId(jury_id),
        "team_id": ObjectId(team_id),
    })


def upsert_draft_evaluation(jury_id, team_id, scores, comments):
    """Save/update an in-progress evaluation. Does NOT lock it."""
    db = get_db()
    if db is None:
        return None
    existing = get_evaluation(jury_id, team_id)
    if existing and existing.get("status") == "submitted":
        raise PermissionError("Evaluation already submitted and is locked.")

    from services.scoring import compute_totals
    totals = compute_totals(scores)
    now = datetime.now(timezone.utc)

    doc = {
        "team_id": ObjectId(team_id),
        "jury_id": ObjectId(jury_id),
        "scores": scores,
        "total_score": totals["total"],
        "max_total": totals["max_total"],
        "percentage": totals["percentage"],
        "comments": comments or "",
        "status": "in_progress",
        "updated_at": now,
    }
    db.evaluations.update_one(
        {"jury_id": ObjectId(jury_id), "team_id": ObjectId(team_id)},
        {"$set": doc, "$setOnInsert": {"created_at": now, "submitted_at": None}},
        upsert=True,
    )
    return get_evaluation(jury_id, team_id)


def submit_evaluation(jury_id, team_id):
    db = get_db()
    if db is None:
        return False
    existing = get_evaluation(jury_id, team_id)
    if not existing:
        raise ValueError("No draft evaluation found to submit.")
    if existing.get("status") == "submitted":
        raise PermissionError("Evaluation already submitted.")

    res = db.evaluations.update_one(
        {"jury_id": ObjectId(jury_id), "team_id": ObjectId(team_id), "status": {"$ne": "submitted"}},
        {"$set": {"status": "submitted", "submitted_at": datetime.now(timezone.utc)}},
    )
    return res.modified_count > 0


def reopen_evaluation(jury_id, team_id):
    """Admin-only action — see routes/admin.py for the authorization check."""
    db = get_db()
    if db is None:
        return False
    res = db.evaluations.update_one(
        {"jury_id": ObjectId(jury_id), "team_id": ObjectId(team_id)},
        {"$set": {"status": "in_progress", "submitted_at": None}},
    )
    return res.modified_count > 0


def evaluations_for_team(team_id):
    db = get_db()
    if db is None:
        return []
    return list(db.evaluations.find({"team_id": ObjectId(team_id)}))


def evaluations_for_jury(jury_id):
    db = get_db()
    if db is None:
        return []
    return list(db.evaluations.find({"jury_id": ObjectId(jury_id)}))


def count_completed():
    db = get_db()
    if db is None:
        return 0
    return db.evaluations.count_documents({"status": "submitted"})


def count_pending():
    db = get_db()
    if db is None:
        return 0
    return db.evaluations.count_documents({"status": "in_progress"})
