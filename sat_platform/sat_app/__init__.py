"""sat_app package – application factory and blueprint registration."""

from __future__ import annotations

import os
from time import perf_counter

import click
from flask import Flask, g, request, current_app
from flask_jwt_extended import JWTManager
from sqlalchemy import inspect, text, event

from config import resolve_config
from .blueprints import BLUEPRINTS
from .extensions import cors, db, jwt, migrate, limiter
from .logging_config import configure_logging, assign_request_id
from .metrics import record_request
from .utils import hash_password
from .blueprints.admin_bp import schedule_import_autoresume


def create_app(config_name: str | None = None) -> Flask:
    """Application factory used by both CLI and runtime servers."""

    app = Flask(__name__)
    _configure_app(app, config_name)
    configure_logging(app)
    _register_extensions(app)
    _register_blueprints(app)
    schedule_import_autoresume(app)
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
    _configure_sqlite_engine(app)
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config.get("CORS_ORIGINS", "*")}},
        supports_credentials=True,
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


def _configure_sqlite_engine(app: Flask) -> None:
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri.startswith("sqlite"):
        return
    busy_timeout_ms = int(app.config.get("SQLITE_BUSY_TIMEOUT_MS", 15000))

    with app.app_context():
        engine = db.engine

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, connection_record):  # pragma: no cover
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms};")
                cursor.execute("PRAGMA synchronous=NORMAL;")
            finally:
                cursor.close()


def _ensure_schema(app: Flask) -> None:
    with app.app_context():
        db.create_all()
        _ensure_email_verification_columns()
        _ensure_user_status_columns()
        _ensure_password_reset_columns()
        _ensure_membership_columns()
        _ensure_question_explanation_columns()
        _ensure_ai_paper_job_columns()


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
                default_questions = app.config.get("PLAN_DEFAULT_QUESTIONS", 12)
                minutes_per_question = app.config.get("PLAN_MIN_PER_QUESTION", 5)
                admin_user.profile = UserProfile(
                    daily_available_minutes=default_questions * minutes_per_question,
                    daily_plan_questions=default_questions,
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
                    default_questions = app.config.get("PLAN_DEFAULT_QUESTIONS", 12)
                    minutes_per_question = app.config.get("PLAN_MIN_PER_QUESTION", 5)
                    student_user.profile = UserProfile(
                        daily_available_minutes=default_questions * minutes_per_question,
                        daily_plan_questions=default_questions,
                        language_preference="en",
                    )
                    db.session.add(student_user)
                    created.append("student")

            if created:
                db.session.commit()
                click.echo(f"Seeded accounts: {', '.join(created)}")
            else:
                click.echo("Seed users already exist; nothing to do.")

    @app.cli.group("plan")
    def plan_group():
        """Study plan management commands."""

    @plan_group.command("generate")
    @click.option("--user-id", type=int, help="Generate plan for a specific user ID.")
    @click.option(
        "--all",
        "generate_all",
        is_flag=True,
        default=False,
        help="Generate plans for all student accounts.",
    )
    @click.option(
        "--date",
        "plan_date",
        type=click.DateTime(formats=["%Y-%m-%d"]),
        help="Plan date (YYYY-MM-DD). Defaults to today.",
    )
    def generate_plan_command(user_id: int | None, generate_all: bool, plan_date):
        """Generate study plans via CLI."""

        if not generate_all and not user_id:
            raise click.UsageError("Provide --user-id or use --all to target students.")
        if generate_all and user_id:
            raise click.UsageError("Use either --user-id or --all, not both.")

        from werkzeug.exceptions import NotFound

        from .models import User
        from .services import learning_plan_service

        target_date = plan_date.date() if plan_date else None

        with app.app_context():
            if generate_all:
                users = User.query.filter_by(role="student").all()
                user_ids = [u.id for u in users]
                if not user_ids:
                    click.echo("No student accounts found; nothing to generate.")
                    return
            else:
                user_ids = [user_id]

            for target_user_id in user_ids:
                try:
                    plan = learning_plan_service.generate_daily_plan(
                        user_id=target_user_id, plan_date=target_date
                    )
                except NotFound as exc:  # pragma: no cover - defensive
                    raise click.ClickException(f"User {target_user_id} not found.") from exc
                click.echo(
                    f"Generated plan for user {target_user_id} on {plan.plan_date.isoformat()}."
                )


def _ensure_root_admin(app: Flask) -> None:
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
            is_email_verified=True,
        )
        default_questions = app.config.get("PLAN_DEFAULT_QUESTIONS", 12)
        minutes_per_question = app.config.get("PLAN_MIN_PER_QUESTION", 5)
        root.profile = UserProfile(
            daily_available_minutes=default_questions * minutes_per_question,
            daily_plan_questions=default_questions,
            language_preference="bilingual",
        )
        db.session.add(root)
        db.session.commit()


def _ensure_email_verification_columns() -> None:
    inspector = inspect(db.engine)
    if "users" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("users")}
    statements: list[str] = []
    dialect = db.engine.dialect.name
    boolean_type = "BOOLEAN" if dialect != "sqlite" else "INTEGER"
    datetime_type = "TIMESTAMP" if dialect != "sqlite" else "TEXT"
    default_true = "TRUE" if dialect != "sqlite" else "1"

    if "is_email_verified" not in columns:
        statements.append(
            f"ALTER TABLE users ADD COLUMN is_email_verified {boolean_type} NOT NULL DEFAULT {default_true}"
        )
    if "email_verification_code" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN email_verification_code VARCHAR(12)")
    if "email_verification_expires_at" not in columns:
        statements.append(
            f"ALTER TABLE users ADD COLUMN email_verification_expires_at {datetime_type}"
        )
    if "email_verification_attempts" not in columns:
        statements.append(
            "ALTER TABLE users ADD COLUMN email_verification_attempts INTEGER NOT NULL DEFAULT 0"
        )
    if "email_verification_sent_at" not in columns:
        statements.append(
            f"ALTER TABLE users ADD COLUMN email_verification_sent_at {datetime_type}"
        )
    if "email_verification_sent_count" not in columns:
        statements.append(
            "ALTER TABLE users ADD COLUMN email_verification_sent_count INTEGER NOT NULL DEFAULT 0"
        )
    if "email_verification_sent_window_start" not in columns:
        statements.append(
            f"ALTER TABLE users ADD COLUMN email_verification_sent_window_start {datetime_type}"
        )

    if not statements:
        return

    connection = db.engine.connect()
    trans = connection.begin()
    try:
        for statement in statements:
            connection.execute(text(statement))
        trans.commit()
    except Exception:  # pragma: no cover - defensive logging
        trans.rollback()
        current_app.logger.debug(
            "Skipping automatic email verification column patch",
            exc_info=True,
        )
    finally:
        connection.close()


def _ensure_user_status_columns() -> None:
    inspector = inspect(db.engine)
    if "users" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("users")}
    dialect = db.engine.dialect.name
    boolean_type = "BOOLEAN" if dialect != "sqlite" else "INTEGER"
    datetime_type = "TIMESTAMP" if dialect != "sqlite" else "TEXT"
    default_true = "TRUE" if dialect != "sqlite" else "1"

    statements: list[str] = []

    if "is_active" not in columns:
        statements.append(
            f"ALTER TABLE users ADD COLUMN is_active {boolean_type} NOT NULL DEFAULT {default_true}"
        )
    if "locked_reason" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN locked_reason VARCHAR(255)")
    if "locked_at" not in columns:
        statements.append(f"ALTER TABLE users ADD COLUMN locked_at {datetime_type}")

    if not statements:
        return

    connection = db.engine.connect()
    trans = connection.begin()
    try:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(text("UPDATE users SET is_active = 1 WHERE is_active IS NULL"))
        trans.commit()
    except Exception:  # pragma: no cover - defensive logging
        trans.rollback()
        current_app.logger.debug(
            "Skipping automatic user status column patch",
            exc_info=True,
        )
    finally:
        connection.close()


def _ensure_password_reset_columns() -> None:
    inspector = inspect(db.engine)
    if "users" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("users")}
    dialect = db.engine.dialect.name
    varchar_type = "VARCHAR(255)" if dialect != "sqlite" else "TEXT"
    datetime_type = "TIMESTAMP" if dialect != "sqlite" else "TEXT"

    statements: list[str] = []

    if "password_reset_token" not in columns:
        statements.append(f"ALTER TABLE users ADD COLUMN password_reset_token {varchar_type}")
    if "password_reset_requested_at" not in columns:
        statements.append(
            f"ALTER TABLE users ADD COLUMN password_reset_requested_at {datetime_type}"
        )
    if "password_reset_expires_at" not in columns:
        statements.append(
            f"ALTER TABLE users ADD COLUMN password_reset_expires_at {datetime_type}"
        )

    if not statements:
        return

    connection = db.engine.connect()
    trans = connection.begin()
    try:
        for statement in statements:
            connection.execute(text(statement))
        trans.commit()
    except Exception:  # pragma: no cover - defensive logging
        trans.rollback()
        current_app.logger.debug(
            "Skipping automatic password reset column patch",
            exc_info=True,
        )
    finally:
        connection.close()


def _ensure_membership_columns() -> None:
    inspector = inspect(db.engine)
    if "users" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("users")}
    dialect = db.engine.dialect.name
    datetime_type = "TIMESTAMP" if dialect != "sqlite" else "TEXT"
    date_type = "DATE" if dialect != "sqlite" else "TEXT"

    statements: list[str] = []

    if "membership_expires_at" not in columns:
        statements.append(f"ALTER TABLE users ADD COLUMN membership_expires_at {datetime_type}")
    if "ai_explain_quota_date" not in columns:
        statements.append(f"ALTER TABLE users ADD COLUMN ai_explain_quota_date {date_type}")
    if "ai_explain_quota_used" not in columns:
        statements.append(
            "ALTER TABLE users ADD COLUMN ai_explain_quota_used INTEGER NOT NULL DEFAULT 0"
        )

    if not statements:
        return

    connection = db.engine.connect()
    trans = connection.begin()
    try:
        for statement in statements:
            connection.execute(text(statement))
        trans.commit()
    except Exception:  # pragma: no cover - defensive logging
        trans.rollback()
        current_app.logger.debug(
            "Skipping automatic membership column patch",
            exc_info=True,
        )
    finally:
        connection.close()


def _ensure_question_explanation_columns() -> None:
    inspector = inspect(db.engine)
    if "question_explanations" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("question_explanations")}
    statements: list[str] = []
    if "source" not in columns:
        statements.append("ALTER TABLE question_explanations ADD COLUMN source VARCHAR(32)")

    if not statements:
        return

    connection = db.engine.connect()
    trans = connection.begin()
    try:
        for statement in statements:
            connection.execute(text(statement))
        trans.commit()
    except Exception:  # pragma: no cover - defensive logging
        trans.rollback()
        current_app.logger.debug(
            "Skipping automatic question explanation patch",
            exc_info=True,
        )
    finally:
        connection.close()


def _ensure_ai_paper_job_columns() -> None:
    inspector = inspect(db.engine)
    if "ai_paper_jobs" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("ai_paper_jobs")}
    statements: list[str] = []
    dialect = db.engine.dialect.name
    text_type = "TEXT" if dialect == "sqlite" else "VARCHAR(255)"

    if "stage" not in columns:
        statements.append(
            f"ALTER TABLE ai_paper_jobs ADD COLUMN stage {text_type} NOT NULL DEFAULT 'pending'"
        )
    if "stage_index" not in columns:
        statements.append(
            "ALTER TABLE ai_paper_jobs ADD COLUMN stage_index INTEGER NOT NULL DEFAULT 0"
        )
    if "status_message" not in columns:
        statements.append("ALTER TABLE ai_paper_jobs ADD COLUMN status_message TEXT")

    if not statements:
        return

    connection = db.engine.connect()
    trans = connection.begin()
    try:
        for statement in statements:
            connection.execute(text(statement))
        trans.commit()
    except Exception:  # pragma: no cover - defensive logging
        trans.rollback()
        current_app.logger.debug(
            "Skipping automatic ai_paper_jobs column patch",
            exc_info=True,
        )
    finally:
        connection.close()

