from flask import Flask
from app.config import Config
from app.extensions import db, bcrypt, login_manager, limiter, migrate, scheduler

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    
    # Configure limiter storage if needed, otherwise defaults to in-memory
    limiter.init_app(app)
    migrate.init_app(app, db)
    
    # Init scheduler if not already running
    if not scheduler.running:
        scheduler.init_app(app)
        scheduler.start()

    # Import models to register them
    from app import models

    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        from app.models.user import User
        return db.session.get(User, user_id)

    # Register blueprints
    from app.auth.routes import auth_bp
    from app.learning.routes import learning_bp
    from app.tutor.routes import tutor_bp
    from app.analytics.routes import analytics_bp
    from app.compiler.routes import compiler_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(learning_bp)
    app.register_blueprint(tutor_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(compiler_bp)

    # Root redirect → auth page
    from flask import redirect, url_for
    @app.route("/")
    def index():
        return redirect(url_for("auth.auth_page"))

    @app.route("/dashboard")
    def dashboard_redirect():
        return redirect(url_for("learning.dashboard"))

    @app.route("/new")
    def new_redirect():
        return redirect(url_for("learning.new_path"))

    @app.route("/assessment")
    def assessment_redirect():
        return redirect(url_for("learning.assessment"))

    @app.route("/playground")
    def playground_redirect():
        return redirect(url_for("compiler.playground"))

    login_manager.login_view = "auth.auth_page"

    from app.cli import register_commands
    register_commands(app)

    return app
