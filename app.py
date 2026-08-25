import os
from dotenv import load_dotenv

# Load environment variables BEFORE importing config
load_dotenv()

from flask import Flask, render_template, session, url_for
from config import get_config
from models.database import Database


def create_app():
    """Application factory"""
    app = Flask(__name__)
    app.config.from_object(get_config())
    
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
    
    @app.context_processor
    def inject_static_url():
        import os as _os
        def static_url(filename):
            path = _os.path.join(app.static_folder, filename)
            try:
                v = int(_os.path.getmtime(path))
            except OSError:
                v = 0
            return url_for('static', filename=filename, v=v)
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
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(debug=debug, host='0.0.0.0', port=5002)
