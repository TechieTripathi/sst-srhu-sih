from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from flask import current_app
import logging

logger = logging.getLogger(__name__)


class Database:
    """MongoDB database connection manager"""
    
    client = None
    db = None
    
    @staticmethod
    def initialize(app):
        """Initialize MongoDB connection"""
        try:
            Database.client = MongoClient(
                app.config['MONGO_URI'],
                serverSelectionTimeoutMS=5000
            )
            
            # Test connection
            Database.client.admin.command('ping')
            
            Database.db = Database.client[app.config['MONGO_DB_NAME']]
            
            logger.info(f"Connected to MongoDB: {app.config['MONGO_DB_NAME']}")
            
            # Create indexes
            Database._create_indexes()
            
        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
    
    @staticmethod
    def _create_indexes():
        """Create database indexes for performance and constraints"""
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
            Database.db.judges.create_index('panel_id')
            Database.db.judges.create_index('status')
            
            # OTP sessions collection
            Database.db.otp_sessions.create_index('email')
            Database.db.otp_sessions.create_index('expires_at', expireAfterSeconds=0)
            Database.db.otp_sessions.create_index([('email', 1), ('used', 1), ('expires_at', -1)])
            
            # Judge assignments collection
            Database.db.judge_assignments.create_index([('judge_id', 1), ('team_id', 1)], unique=True)
            Database.db.judge_assignments.create_index('panel_id')
            
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


def get_jury_panels_collection():
    return Database.get_collection('jury_panels')


def get_judge_assignments_collection():
    return Database.get_collection('judge_assignments')


def get_evaluation_criteria_collection():
    return Database.get_collection('evaluation_criteria')


def get_evaluation_stages_collection():
    return Database.get_collection('evaluation_stages')


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
