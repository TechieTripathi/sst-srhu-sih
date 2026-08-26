"""Vercel serverless entrypoint: re-export the Flask app from the project root.

Creating the app at import time (not inside a handler) is deliberate - Vercel
reuses a warm instance across invocations, so the MongoClient built here is
reused too instead of reconnecting on every request.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402

application = app
