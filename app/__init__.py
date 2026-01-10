import os
from flask import Flask
from datetime import timedelta
from dotenv import load_dotenv
from .models import db, User, Log, QSO, Park, QsoPark, DailyMultiplier

load_dotenv()

def create_app():
    app = Flask(__name__, instance_relative_config=True)

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Database stored in instance folder
    db_path = os.path.join(app.instance_path, "parkmas.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # Load secret key from environment or use dev key
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "devkey")
    
    # Session timeout: 2 hours of inactivity
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=2)

    db.init_app(app)

    # -----------------------------------------
    # Create all tables on startup
    # -----------------------------------------
    with app.app_context():
        db.create_all()

    # -----------------------------------------
    # Jinja Filters
    # -----------------------------------------
    from datetime import datetime

    @app.template_filter("datetimeformat")
    def datetimeformat(value):
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M")

    # -----------------------------------------
    # Register blueprints
    # -----------------------------------------
    from .auth import auth
    from .routing import bp as main_bp

    app.register_blueprint(auth)
    app.register_blueprint(main_bp)

    # NEW: Setup centralized authentication routes
    from .client_auth import setup_auth_routes
    setup_auth_routes(app)

    print("Using DB:", db_path)
    
    return app