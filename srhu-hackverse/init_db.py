#!/usr/bin/env python3
"""
TechForge 3.0 Database Initialization Script
Run this once to set up evaluation criteria, admin user, and event settings
"""

from app import create_app
from services.init_data import init_database

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        init_database()
