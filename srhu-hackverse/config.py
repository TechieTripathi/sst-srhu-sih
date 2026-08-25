import os

class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-this'
    
    # MongoDB Configuration
    MONGO_URI = os.environ.get('MONGO_URI')
    MONGO_DB_NAME = os.environ.get('MONGO_DB_NAME', 'techforge3')
    
    # Session Configuration
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False') == 'True'
    SESSION_COOKIE_HTTPONLY = os.environ.get('SESSION_COOKIE_HTTPONLY', 'True') == 'True'
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    PERMANENT_SESSION_LIFETIME = 43200  # 12 hours
    
    # Event Configuration
    EVENT_NAME = os.environ.get('EVENT_NAME', 'TechForge 3.0')
    EVENT_TAGLINE = os.environ.get('EVENT_TAGLINE', 'Innovate. Build. Impact.')
    UNIVERSITY_NAME = os.environ.get('UNIVERSITY_NAME', 'Swami Rama Himalayan University')
    SCHOOL_NAME = os.environ.get('SCHOOL_NAME', 'School of Science & Technology')
    
    # Super Admin Configuration
    SUPER_ADMIN_EMAIL = os.environ.get('SUPER_ADMIN_EMAIL', 'superadmin@srhu.edu.in')
    SUPER_ADMIN_NAME = os.environ.get('SUPER_ADMIN_NAME', 'Super Administrator')
    SUPER_ADMIN_PASSWORD = os.environ.get('SUPER_ADMIN_PASSWORD', 'superadmin123')
    
    # SMTP Configuration for Jury OTP
    SMTP_HOST = os.environ.get('SMTP_HOST')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
    SMTP_FROM = os.environ.get('SMTP_FROM', 'techforge@srhu.edu.in')
    SMTP_USE_TLS = os.environ.get('SMTP_USE_TLS', 'true').lower() in ['true', '1', 'yes']
    
    # Evaluation Configuration
    EVALUATION_CRITERIA = [
        {
            'id': 'problem_understanding',
            'name': 'Problem Understanding & Relevance',
            'weight': 0.15,
            'description': 'Clarity of need, stakeholder insight, alignment with the selected statement and measurable objectives.'
        },
        {
            'id': 'innovation',
            'name': 'Innovation & Differentiation',
            'weight': 0.15,
            'description': 'Originality, value beyond existing alternatives and appropriateness of the approach.'
        },
        {
            'id': 'technical_design',
            'name': 'Technical Design & Feasibility',
            'weight': 0.20,
            'description': 'Architecture, technology choices, security, data/hardware plan, practicality and resource awareness.'
        },
        {
            'id': 'prototype',
            'name': 'Prototype & Implementation',
            'weight': 0.25,
            'description': 'Functional completeness, integration, robustness, testing and quality of demonstration.'
        },
        {
            'id': 'impact',
            'name': 'Impact, Scalability & Sustainability',
            'weight': 0.15,
            'description': 'Expected social/economic value, usability, deployment potential, scalability, maintainability and cost.'
        },
        {
            'id': 'presentation',
            'name': 'Presentation & Team Response',
            'weight': 0.10,
            'description': 'Clarity of pitch, documentation, live demonstration, teamwork and response to jury questions.'
        }
    ]
    
    # Scoring Configuration
    RAW_SCORE_MIN = 0
    RAW_SCORE_MAX = 10
    INTERNAL_WEIGHT = 0.40
    EXTERNAL_WEIGHT = 0.60


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    FLASK_ENV = 'development'


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    FLASK_ENV = 'production'
    SESSION_COOKIE_SECURE = True


def get_config():
    """Get configuration based on environment"""
    env = os.environ.get('FLASK_ENV', 'development')
    if env == 'production':
        return ProductionConfig
    return DevelopmentConfig
