from pymongo import MongoClient
import logging

logger = logging.getLogger(__name__)


class Database:
    """MongoDB database connection manager"""
    
    client = None
    db = None
    
    @staticmethod
    def initialize(app):
        """Attach a lazily-connecting MongoClient to the app.

        Tuned for Vercel: the client is built once per instance at import time (not
        per request) so warm invocations reuse its connections, and it is configured
        for many small short-lived instances rather than one long-lived server.
        """
        Database.client = MongoClient(
            app.config['MONGO_URI'],

            # No network I/O at import time. PyMongo opens sockets in the background
            # on first real use, so a cold Vercel instance starts serving immediately
            # instead of blocking on a ping. Index creation moved to ensure_indexes().
            connect=False,

            # Each warm Vercel instance holds its own pool and handles one request at
            # a time, so a large pool would just idle. Vercel scales by adding
            # instances, and every instance costs (maxPoolSize + 2) connections per
            # replica member against the M0 tier's 500-connection cap.
            maxPoolSize=5,

            # Zero, not 2: a frozen serverless instance cannot keep sockets warm, so
            # pre-opening them only burns Atlas connections that will never be used.
            minPoolSize=0,

            maxIdleTimeMS=30_000,        # release sockets quickly; instances get frozen
            connectTimeoutMS=10_000,     # tolerate a slow first handshake
            socketTimeoutMS=30_000,      # these are short OLTP queries
            serverSelectionTimeoutMS=5_000,
            retryWrites=True,
        )

        Database.db = Database.client[app.config['MONGO_DB_NAME']]
        logger.info("MongoDB client configured for %s", app.config['MONGO_DB_NAME'])

    @staticmethod
    def ping():
        """Verify the connection. Used by the health check, never on the hot path."""
        Database.client.admin.command('ping')

    @staticmethod
    def ensure_indexes():
        """Create database indexes for performance and constraints.

        Run once from init_db.py after a schema change - never on a cold start.
        Each create_index() is a separate round trip to Atlas, and there are twenty.
        """
        try:
            # Users collection
            Database.db.users.create_index('email', unique=True)
            Database.db.users.create_index('role')
            
            # Teams collection
            Database.db.teams.create_index('team_name', unique=True)
            Database.db.teams.create_index('team_code', unique=True, sparse=True)
            Database.db.teams.create_index('leader_id')
            
            # Judges collection
            Database.db.judges.create_index('user_id', unique=True)
            Database.db.judges.create_index('email', unique=True, sparse=True)
            Database.db.judges.create_index('judge_type')
            Database.db.judges.create_index('status')
            
            # OTP sessions collection
            Database.db.otp_sessions.create_index('email')
            Database.db.otp_sessions.create_index('expires_at', expireAfterSeconds=0)
            Database.db.otp_sessions.create_index([('email', 1), ('used', 1), ('expires_at', -1)])
            
            # Evaluations collection - prevent duplicate submissions
            Database.db.evaluations.create_index([('judge_id', 1), ('team_id', 1), ('stage_id', 1)], unique=True)
            Database.db.evaluations.create_index('team_id')
            Database.db.evaluations.create_index('judge_id')
            Database.db.evaluations.create_index('status')
            
            # Team results collection
            Database.db.team_results.create_index([('team_id', 1), ('stage_id', 1)], unique=True)
            Database.db.team_results.create_index('final_score')
            
            # Audit logs collection
            Database.db.audit_logs.create_index('created_at')
            Database.db.audit_logs.create_index('actor_id')
            Database.db.audit_logs.create_index('action')
            
            logger.info("Database indexes created successfully")

        except Exception as e:
            logger.warning(f"Error creating indexes: {e}")

    @staticmethod
    def get_collection(name):
        """Get a collection from the database"""
        if Database.db is None:
            raise RuntimeError("Database not initialized")
        return Database.db[name]


# Collection shortcuts
def get_users_collection():
    return Database.get_collection('users')


def get_teams_collection():
    return Database.get_collection('teams')


def get_team_members_collection():
    return Database.get_collection('team_members')


def get_judges_collection():
    return Database.get_collection('judges')


def get_otp_sessions_collection():
    return Database.get_collection('otp_sessions')




def get_evaluation_criteria_collection():
    return Database.get_collection('evaluation_criteria')



def get_evaluations_collection():
    return Database.get_collection('evaluations')


def get_evaluation_scores_collection():
    return Database.get_collection('evaluation_scores')


def get_results_collection():
    return Database.get_collection('results')


def get_team_results_collection():
    return Database.get_collection('team_results')


def get_audit_logs_collection():
    return Database.get_collection('audit_logs')


def get_event_settings_collection():
    return Database.get_collection('event_settings')
