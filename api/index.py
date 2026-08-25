"""Vercel serverless entrypoint: re-export the Flask app from the project root.

The path-fixing middleware lives in app.py itself, so this file stays a thin
re-export and the app behaves the same no matter which entrypoint Vercel picks.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402

application = app
