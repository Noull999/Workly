"""
Blueprints module for organizing Flask routes by functionality
"""

def register_blueprints(app):
    """Register all blueprints with the Flask application"""
    
    # Import blueprints
    from .auth import auth
    from .admin import admin
    from .inventory import inventory
    from .pos import pos
    from .appointments import appointments
    from .scrum import scrum
    from .notion import notion
    from .public import public
    from .reports import reports
    
    # Register blueprints with their URL prefixes
    app.register_blueprint(auth)
    app.register_blueprint(admin, url_prefix='/admin')
    app.register_blueprint(inventory, url_prefix='/inventory')
    app.register_blueprint(pos, url_prefix='/pos')
    app.register_blueprint(appointments, url_prefix='/appointments')
    app.register_blueprint(scrum, url_prefix='/scrum')
    app.register_blueprint(notion, url_prefix='/notion')
    app.register_blueprint(public, url_prefix='/public')
    app.register_blueprint(reports, url_prefix='/reports')