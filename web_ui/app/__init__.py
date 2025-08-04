#!/usr/bin/env python3
"""
HuboluxTradingBot Web UI Application Factory
"""

from flask import Flask, session, redirect, url_for, render_template
from datetime import datetime
import logging
import os


def create_app(config_name='development'):
    """Create and configure the Flask application"""
    app = Flask(__name__)
    
    # Load configuration
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import config
    app.config.from_object(config[config_name])
    
    # Setup logging
    setup_logging(app)
    
    # Register blueprints
    register_blueprints(app)
    
    # Register template globals and filters
    register_template_globals(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    return app


def setup_logging(app):
    """Setup application logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Reduce werkzeug logging in development
    if app.config.get('DEBUG'):
        logging.getLogger('werkzeug').setLevel(logging.WARNING)


def register_blueprints(app):
    """Register all blueprints"""
    from .controllers.main_controller import main_bp
    from .controllers.auth_controller import auth_bp
    from .controllers.account_controller import account_bp
    from .controllers.admin_controller import admin_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(admin_bp)


def register_template_globals(app):
    """Register template global variables and functions"""
    
    @app.template_global()
    def current_user():
        """Get current user info for templates"""
        if session.get('is_authenticated'):
            return {
                'id': session.get('user_id'),
                'username': session.get('username'),
                'role': session.get('role'),
                'is_authenticated': True
            }
        return {'is_authenticated': False}
    
    @app.template_filter('datetime')
    def datetime_filter(dt):
        """Format datetime for templates"""
        if dt:
            if isinstance(dt, str):
                try:
                    dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
                except:
                    return dt
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        return ''
    
    @app.template_filter('date')
    def date_filter(dt):
        """Format date for templates"""
        if dt:
            if isinstance(dt, str):
                try:
                    dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
                except:
                    return dt
            return dt.strftime('%Y-%m-%d')
        return ''


def register_error_handlers(app):
    """Register error handlers"""
    
    @app.errorhandler(404)
    def not_found(error):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(403)
    def forbidden(error):
        return render_template('errors/403.html'), 403
