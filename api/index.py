"""Vercel serverless entrypoint.

The @vercel/python runtime looks for a module-level WSGI callable named `app`,
so we just re-export the Flask instance from the project root.
"""
import os
import sys

# api/index.py lives one level below the project root; put the root on the path
# so `import app` resolves to /app.py rather than this package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402

# Vercel invokes this WSGI callable for every request routed here.
application = app
