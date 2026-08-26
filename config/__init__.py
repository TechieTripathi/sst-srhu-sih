import os
from datetime import timedelta


class Config:
    """Base configuration for TechForge 3.0 — reads from environment variables."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-this")
    MONGO_URI = os.environ.get("MONGO_URI", "")
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "techforge3")

    # Public base URL of this deployment (no trailing slash). Used for absolute links in
    # emails and on-screen copy so they point at the real domain, not the request host.
    FRONTEND_URL = os.environ.get("FRONTEND_URL", "").rstrip("/")

    # Session
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False') == 'True'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)

    # Event branding
    EVENT_NAME = os.environ.get("EVENT_NAME", "TechForge 3.0")
    EVENT_TAGLINE = os.environ.get("EVENT_TAGLINE", "Innovate. Build. Impact.")
    UNIVERSITY_NAME = os.environ.get("UNIVERSITY_NAME", "Swami Rama Himalayan University")
    SCHOOL_NAME = os.environ.get("SCHOOL_NAME", "School of Science & Technology")

    # Super Admin Configuration
    SUPER_ADMIN_EMAIL = os.environ.get('SUPER_ADMIN_EMAIL', 'superadmin@srhu.edu.in')
    SUPER_ADMIN_NAME = os.environ.get('SUPER_ADMIN_NAME', 'Super Administrator')
    SUPER_ADMIN_PASSWORD = os.environ.get('SUPER_ADMIN_PASSWORD', 'superadmin123')

    # SMTP Configuration (judge credential emails)
    SMTP_HOST = os.environ.get('SMTP_HOST')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
    SMTP_FROM = os.environ.get('SMTP_FROM', 'techforge@srhu.edu.in')
    SMTP_USE_TLS = os.environ.get('SMTP_USE_TLS', 'true').lower() in ['true', '1', 'yes']

    # Official TechForge 3.0 Evaluation Criteria (6 criteria, configurable weights)
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

    # Scoring bounds
    RAW_SCORE_MIN = 0
    RAW_SCORE_MAX = 10
    MIN_SCORE = 0
    MAX_SCORE = 10

    # Scoring weights deliberately live in services/results_calculator.py only
    # (EXCEPTION_WEIGHT / GROUP_WEIGHT). Duplicates here were dead code that
    # nothing imported, and would now be wrong as well as unused.


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    FLASK_ENV = 'development'
    SESSION_COOKIE_SECURE = False


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
