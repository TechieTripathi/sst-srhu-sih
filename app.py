import os
from dotenv import load_dotenv

# Load environment variables BEFORE importing config
load_dotenv()

from datetime import timedelta

from flask import Flask, render_template, session, url_for
from flask_compress import Compress

from config import get_config
from models.database import Database


def create_app():
    """Application factory"""
    # Static files live under public/ so Vercel's CDN serves them directly. Anything
    # in public/ is exposed at the deployment root, so public/static/css/app.css is
    # still /static/css/app.css - the URLs and every template reference are unchanged,
    # but the requests no longer wake a Python function just to hand back a file.
    app = Flask(__name__, static_folder='public/static', static_url_path='/static')
    from utils.icons import icon
    app.jinja_env.globals['icon'] = icon
    app.config.from_object(get_config())

    # Rendered HTML still comes out of this function, and the landing page is 19K
    # uncompressed against roughly 4K gzipped - worth the ~1ms of CPU. Static assets
    # are compressed and cached by the CDN instead (see vercel.json).
    Compress(app)

    # Only affects local dev now that the CDN serves /static in production, but it
    # stops the dev server from sending no-cache on every asset of every page.
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = timedelta(days=365)

    # Initialize MongoDB
    Database.initialize(app)
    
    # Register blueprints
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.super_admin import super_admin_bp
    from routes.judge import judge_bp
    from routes.teams import teams_bp
    from routes.evaluations import evaluations_bp
    from routes.results import results_bp
    from routes.api import api_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(super_admin_bp, url_prefix='/super-admin')
    app.register_blueprint(judge_bp, url_prefix='/judge')
    app.register_blueprint(teams_bp, url_prefix='/teams')
    app.register_blueprint(evaluations_bp, url_prefix='/api/evaluations')
    app.register_blueprint(results_bp, url_prefix='/results')
    app.register_blueprint(api_bp)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register context processors
    register_context_processors(app)
    
    # Root route - Always renders the TechForge 3.0 Homepage
    @app.route('/')
    def index():
        return render_template('landing.html')
    
    @app.route('/home')
    def home():
        return render_template('landing.html')
    
    # Render pings this to decide whether the instance is live. It is the only
    # place that touches the database outside a real request.
    @app.route('/healthz')
    def healthz():
        try:
            Database.ping()
        except Exception:
            return {'status': 'degraded'}, 503
        return {'status': 'ok'}, 200

    # Common login redirect route
    @app.route('/login')
    def login_redirect():
        from flask import redirect, url_for
        return redirect(url_for('auth.login'))
    
    return app


def register_error_handlers(app):
    """Register error handlers"""
    
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/error.html',
                             code=403,
                             title='Access Denied',
                             message="You don't have permission to view this page."), 403
    
    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/error.html',
                             code=404,
                             title='Page Not Found',
                             message="The page you're looking for doesn't exist."), 404
    
    @app.errorhandler(500)
    def server_error(e):
        app.logger.exception("Unhandled server error")
        return render_template('errors/error.html',
                             code=500,
                             title='Something Went Wrong',
                             message="We couldn't complete that request. Please try again."), 500


def register_context_processors(app):
    """Register context processors"""
    
    # Static files cannot change without a redeploy, so their mtimes are stat'ed
    # once per process instead of on every asset of every page render. Debug builds
    # keep stat'ing so edits show up locally without a restart.
    _static_versions = {}

    @app.context_processor
    def inject_static_url():
        import os as _os

        def _version(filename):
            path = _os.path.join(app.static_folder, filename)
            try:
                return int(_os.path.getmtime(path))
            except OSError:
                return 0

        def static_url(filename):
            if app.debug:
                return url_for('static', filename=filename, v=_version(filename))
            if filename not in _static_versions:
                _static_versions[filename] = _version(filename)
            return url_for('static', filename=filename, v=_static_versions[filename])

        return {'static_url': static_url}

    @app.context_processor
    def inject_globals():
        from routes.teams import is_registration_open
        from utils.urls import public_url
        return {
            'frontend_url': app.config.get('FRONTEND_URL', ''),
            'jury_login_url': public_url('judge.login'),
            'registration_open': is_registration_open(),
            'event_name': app.config['EVENT_NAME'],
            'event_tagline': app.config['EVENT_TAGLINE'],
            'university_name': app.config['UNIVERSITY_NAME'],
            'school_name': app.config['SCHOOL_NAME'],
            'current_user': session.get('user_id'),
            'current_role': session.get('role'),
            'user_name': session.get('name')
        }


app = create_app()


if __name__ == '__main__':
    # Local development only. Production runs under gunicorn (see gunicorn.conf.py);
    # this server handles one request at a time and must never serve real traffic.
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(debug=debug, host='0.0.0.0', port=int(os.environ.get('PORT', 5002)))
