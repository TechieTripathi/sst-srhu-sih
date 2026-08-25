"""
Central MongoDB connection.

Uses PyMongo against MONGO_URI (MongoDB Atlas in production). The connection
is created once per process and reused via Flask's `g`/app context pattern
kept simple here as a module-level singleton, which is fine for a single
Flask app instance.
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure

_client = None
_db = None


def init_db(app):
    """Call once from the application factory."""
    global _client, _db
    uri = app.config.get("MONGO_URI")
    db_name = app.config.get("MONGO_DB_NAME")

    if not uri:
        # No URI configured — app still boots so pages can render empty
        # states instead of crashing. Every route must handle db is None.
        app.logger.warning("MONGO_URI not set — running without a database.")
        _client = None
        _db = None
        return

    try:
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        _client.admin.command("ping")
        _db = _client[db_name]
        _ensure_indexes(_db)
        app.logger.info("Connected to MongoDB (%s).", db_name)
    except ConnectionFailure as exc:
        app.logger.error("MongoDB connection failed: %s", exc)
        _client = None
        _db = None


def get_db():
    """Returns the database handle, or None if unavailable.
    Every caller MUST handle the None case gracefully (empty state)."""
    return _db


def _ensure_indexes(db):
    db.users.create_index([("email", ASCENDING)], unique=True)
    db.teams.create_index([("team_id", ASCENDING)], unique=True)
    db.teams.create_index([("status", ASCENDING)])
    db.jury.create_index([("jury_id", ASCENDING)], unique=True)
    db.jury.create_index([("email", ASCENDING)])
    db.assignments.create_index([("jury_id", ASCENDING), ("team_id", ASCENDING)], unique=True)
    db.evaluations.create_index(
        [("jury_id", ASCENDING), ("team_id", ASCENDING)], unique=True
    )
    db.evaluations.create_index([("status", ASCENDING)])
    db.hackathons.create_index([("hackathon_id", ASCENDING)], unique=True)
    db.projects.create_index([("team_id", ASCENDING)])
    db.results.create_index([("hackathon_id", ASCENDING)])
