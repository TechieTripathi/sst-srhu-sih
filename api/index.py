"""Vercel serverless entrypoint.

The @vercel/python runtime looks for a module-level WSGI callable named `app`,
so we re-export the Flask instance from the project root.
"""
import os
import sys

# api/index.py lives one level below the project root; put the root on the path
# so `import app` resolves to /app.py rather than this package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402


class StripFunctionPrefix:
    """Give Flask the browser's path, not the rewrite destination.

    vercel.json rewrites every request to /api/index, and that rewritten path
    is what reaches the function as PATH_INFO -- so Flask sees /api/index for
    every URL and 404s. Strip the prefix and restore the real path. Note we do
    NOT set SCRIPT_NAME: url_for() must keep emitting /about, not
    /api/index/about.
    """

    PREFIXES = ("/api/index.py", "/api/index")

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        for prefix in self.PREFIXES:
            if path == prefix or path.startswith(prefix + "/"):
                environ["PATH_INFO"] = path[len(prefix):] or "/"
                break
        return self.wsgi_app(environ, start_response)


app.wsgi_app = StripFunctionPrefix(app.wsgi_app)

# Vercel invokes this WSGI callable for every request routed here.
application = app
