"""sat_app package – application factory and blueprint registration."""

from __future__ import annotations

import os
from time import perf_counter

import click
from flask import Flask, g, request
from flask_jwt_extended import JWTManager

from config import resolve_config
from .blueprints import BLUEPRINTS
from .extensions import cors, db, jwt, migrate, limiter
from .logging_config import configure_logging, assign_request_id
from .metrics import record_request
from .utils import hash_password


def create_app(config_name: str | None = None) -> Flask:
    """Application factory used by both CLI and runtime servers."""

    app = Flask(__name__)
    _configure_app(app, config_name)
    configure_logging(app)
    _register_extensions(app)
    _register_blueprints(app)
    _register_shellcontext(app)
    _register_cli(app)
    _register_bootstrap(app)
    _register_request_hooks(app)

    return app


def _configure_app(app: Flask, config_name: str | None) -> None:
    env_name = config_name or os.getenv("FLASK_CONFIG")
    config_obj = resolve_config(env_name)
    app.config.from_object(config_obj)


def _register_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    _configure_jwt(jwt)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*")}},
    )
    limiter.default_limits = app.config.get("RATE_LIMIT_DEFAULTS", [])
    limiter.init_app(app)


def _register_blueprints(app: Flask) -> None:
    for blueprint, prefix in BLUEPRINTS:
        app.register_blueprint(blueprint, url_prefix=prefix)


def _register_shellcontext(app: Flask) -> None:
    # Lazy import inside function to avoid circular dependencies.
    from . import models  # noqa: F401

    @app.shell_context_processor
    def shell_context():
        return {"db": db}


def _configure_jwt(jwt_manager: JWTManager) -> None:
    from flask import jsonify

    from .models import User

    @jwt_manager.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        identity = jwt_data.get("sub")
        if identity is None:
            return None
        try:
            identity_int = int(identity)
        except (TypeError, ValueError):
            return None
        return db.session.get(User, identity_int)

    @jwt_manager.expired_token_loader
    def expired_token_callback(jwt_header, jwt_data):
        return jsonify({"message": "Token has expired"}), 401

    @jwt_manager.invalid_token_loader
    def invalid_token_callback(error_string):
        return jsonify({"message": "Invalid token", "error": error_string}), 401

    @jwt_manager.unauthorized_loader
    def missing_token_callback(error_string):
        return jsonify({"message": "Missing authorization token"}), 401


def _register_bootstrap(app: Flask) -> None:
    @app.before_request
    def ensure_root_admin():
        if not app.config.get("_SCHEMA_READY"):
            try:
                _ensure_schema(app)
                app.config["_SCHEMA_READY"] = True
            except Exception as exc:  # pragma: no cover - defensive logging
                app.logger.debug("Schema bootstrap skipped: %s", exc)
                app.config["_SCHEMA_READY"] = False
                return

        if app.config.get("_ROOT_ADMIN_READY"):
            return

        try:
            _ensure_root_admin(app)
            app.config["_ROOT_ADMIN_READY"] = True
        except Exception as exc:  # pragma: no cover - defensive logging
            app.logger.debug("Root admin bootstrap skipped: %s", exc)
            app.config["_ROOT_ADMIN_READY"] = False


def _register_request_hooks(app: Flask) -> None:
    @app.before_request
    def start_request():
        assign_request_id()
        g.request_started_at = perf_counter()

    @app.after_request
    def finalize(response):
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers["X-Request-ID"] = request_id
        started = getattr(g, "request_started_at", None)
        latency = perf_counter() - started if started else 0.0
        endpoint = request.endpoint or request.path
        record_request(request.method, endpoint, response.status_code, latency)
        return response


def _ensure_schema(app: Flask) -> None:
    with app.app_context():
        db.create_all()


def _register_cli(app: Flask) -> None:
    @app.cli.command("seed-users")
    @click.option(
        "--skip-student",
        is_flag=True,
        default=False,
        help="Skip creating the sample student account.",
    )
    def seed_users(skip_student: bool) -> None:
        """Seed default admin / student accounts for local testing."""

        from .models import User, UserProfile

        created = []
        with app.app_context():
            _ensure_schema(app)
            _ensure_root_admin(app)

            admin_email = app.config["ADMIN_DEFAULT_EMAIL"].lower()
            admin_username = app.config["ADMIN_DEFAULT_USERNAME"].lower()
            admin_password = app.config["ADMIN_DEFAULT_PASSWORD"]

            admin_user = User.query.filter_by(email=admin_email).first()
            if not admin_user:
                admin_user = User(
                    email=admin_email,
                    username=admin_username,
                    password_hash=hash_password(admin_password),
                    role="admin",
                    is_root=False,
                )
                admin_user.profile = UserProfile(
                    daily_available_minutes=90,
                    language_preference="bilingual",
                )
                db.session.add(admin_user)
                created.append("admin")

            if not skip_student:
                student_email = app.config["SEED_STUDENT_EMAIL"].lower()
                student_username = app.config["SEED_STUDENT_USERNAME"].lower()
                student_password = app.config["SEED_STUDENT_PASSWORD"]

                student_user = User.query.filter_by(email=student_email).first()
                if not student_user:
                    student_user = User(
                        email=student_email,
                        username=student_username,
                        password_hash=hash_password(student_password),
                        role="student",
                        is_root=False,
                    )
                    student_user.profile = UserProfile(
                        daily_available_minutes=60,
                        language_preference="en",
                    )
                    db.session.add(student_user)
                    created.append("student")

            if created:
                db.session.commit()
                click.echo(f"Seeded accounts: {', '.join(created)}")
            else:
                click.echo("Seed users already exist; nothing to do.")


def _ensure_root_admin(app: Flask) -> None:
    from sqlalchemy import inspect

    from .models import User, UserProfile

    with app.app_context():
        inspector = inspect(db.engine)
        if not inspector.has_table("users"):
            return
        if User.query.filter_by(is_root=True).first():
            return

        username = app.config["ROOT_ADMIN_USERNAME"].lower()
        email = app.config["ROOT_ADMIN_EMAIL"].lower()
        password = app.config["ROOT_ADMIN_PASSWORD"]

        root = User(
            email=email,
            username=username,
            password_hash=hash_password(password),
            role="admin",
            is_root=True,
        )
        root.profile = UserProfile(
            daily_available_minutes=120,
            language_preference="bilingual",
        )
        db.session.add(root)
        db.session.commit()

