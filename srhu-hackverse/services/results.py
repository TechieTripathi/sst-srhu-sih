"""Leaderboard and final-results aggregation."""

from models.db import get_db


def build_leaderboard():
    """
    Returns a list of dicts per team:
    { team, project_name, track, avg_percentage, jury_count, status }
    sorted by avg_percentage descending.

    Uses only submitted evaluations — in-progress drafts never count.
    """
    db = get_db()
    if db is None:
        return []

    pipeline = [
        {"$match": {"status": "submitted"}},
        {"$group": {
            "_id": "$team_id",
            "avg_percentage": {"$avg": "$percentage"},
            "jury_count": {"$sum": 1},
        }},
        {"$sort": {"avg_percentage": -1}},
    ]
    rows = list(db.evaluations.aggregate(pipeline))

    leaderboard = []
    for row in rows:
        team = db.teams.find_one({"_id": row["_id"]})
        if not team:
            continue
        leaderboard.append({
            "team_id": str(team["_id"]),
            "team_name": team.get("team_name", "Unknown"),
            "project_name": team.get("project_name", ""),
            "track": team.get("track", ""),
            "avg_percentage": round(row["avg_percentage"], 2),
            "jury_count": row["jury_count"],
            "status": team.get("status", "registered"),
        })
    return leaderboard


def get_results_published(hackathon_id):
    db = get_db()
    if db is None:
        return False
    doc = db.results.find_one({"hackathon_id": hackathon_id})
    return bool(doc and doc.get("published"))


def publish_results(hackathon_id):
    db = get_db()
    if db is None:
        return False
    leaderboard = build_leaderboard()
    db.results.update_one(
        {"hackathon_id": hackathon_id},
        {"$set": {"leaderboard": leaderboard, "published": True}},
        upsert=True,
    )
    return True
