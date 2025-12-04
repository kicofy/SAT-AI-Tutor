"""Application configuration objects."""

from __future__ import annotations

import os
from datetime import timedelta
from functools import lru_cache
from typing import Any, Type

from sqlalchemy.pool import NullPool


class BaseConfig:
    """Shared defaults across all environments."""

    APP_NAME = "SAT AI Tutor"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite+pysqlite:///sat_dev.db",
    )
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change_me")
    JWT_TOKEN_LOCATION = ("headers", "query_string")
    JWT_QUERY_STRING_NAME = "token"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        seconds=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_SEC", "43200"))
    )
    AI_MODEL_NAME = os.getenv("AI_MODEL_NAME", "gpt-5.1")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("AI_API_KEY", "")
    AI_API_KEY = OPENAI_API_KEY  # backwards-compatible alias
    AI_API_BASE = os.getenv("AI_API_BASE", "https://api.openai.com/v1")
    AI_API_MAX_RETRIES = int(os.getenv("AI_API_MAX_RETRIES", "3"))
    AI_API_RETRY_BACKOFF = float(os.getenv("AI_API_RETRY_BACKOFF", "2.0"))
    AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "120"))
    AI_CONNECT_TIMEOUT_SEC = int(os.getenv("AI_CONNECT_TIMEOUT_SEC", "15"))
    AI_READ_TIMEOUT_SEC = int(
        os.getenv("AI_READ_TIMEOUT_SEC", str(AI_TIMEOUT_SECONDS))
    )
    AI_EXPLAINER_MODEL = os.getenv("AI_EXPLAINER_MODEL", "gpt-5.1")
    AI_EXPLAINER_ENABLE = os.getenv("AI_EXPLAINER_ENABLE", "true").lower() in {"1", "true", "yes"}
    ADAPTIVE_DEFAULT_MASTERY = float(os.getenv("ADAPTIVE_DEFAULT_MASTERY", "0.5"))
    ADAPTIVE_CORRECT_INCREMENT = float(os.getenv("ADAPTIVE_CORRECT_INCREMENT", "0.05"))
    ADAPTIVE_INCORRECT_DECREMENT = float(os.getenv("ADAPTIVE_INCORRECT_DECREMENT", "0.1"))
    ADAPTIVE_REVIEW_INTERVAL_DAYS = int(os.getenv("ADAPTIVE_REVIEW_INTERVAL_DAYS", "1"))
    PLAN_DEFAULT_MINUTES = int(os.getenv("PLAN_DEFAULT_MINUTES", "60"))
    PLAN_BLOCK_MINUTES = int(os.getenv("PLAN_BLOCK_MINUTES", "25"))
    PLAN_REVIEW_MINUTES = int(os.getenv("PLAN_REVIEW_MINUTES", "10"))
    ANALYTICS_HISTORY_DAYS = int(os.getenv("ANALYTICS_HISTORY_DAYS", "30"))
    AI_DIAGNOSTIC_ENABLE = os.getenv("AI_DIAGNOSTIC_ENABLE", "true").lower() in {"1", "true", "yes"}
    AI_DIAGNOSTIC_MODEL = os.getenv("AI_DIAGNOSTIC_MODEL", "gpt-5.1")
    AI_PARSER_ENABLE = os.getenv("AI_PARSER_ENABLE", "true").lower() in {"1", "true", "yes"}
    AI_PARSER_MODEL = os.getenv("AI_PARSER_MODEL", "gpt-5.1")
    AI_PDF_VISION_MODEL = os.getenv("AI_PDF_VISION_MODEL") or AI_PARSER_MODEL
    AI_PDF_NORMALIZE_MODEL = os.getenv("AI_PDF_NORMALIZE_MODEL") or AI_PARSER_MODEL
    AI_PDF_SOLVER_MODEL = (
        os.getenv("AI_PDF_SOLVER_MODEL")
        or os.getenv("AI_EXPLAINER_MODEL")
        or "gpt-5.1"
    )
    PDF_INGEST_RESOLUTION = int(os.getenv("PDF_INGEST_RESOLUTION", "220"))
    PDF_INGEST_MAX_PAGES = int(os.getenv("PDF_INGEST_MAX_PAGES", "200"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    RATE_LIMIT_DEFAULTS = [limit.strip() for limit in os.getenv("RATE_LIMIT_DEFAULTS", "200 per minute;1000 per day").split(";") if limit.strip()]
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
    JSON_SORT_KEYS = False
    ROOT_ADMIN_USERNAME = os.getenv("ROOT_ADMIN_USERNAME", "ha22y")
    ROOT_ADMIN_PASSWORD = os.getenv("ROOT_ADMIN_PASSWORD", "Kicofy5438")
    ROOT_ADMIN_EMAIL = os.getenv("ROOT_ADMIN_EMAIL", "ha22y@example.com")
    ADMIN_DEFAULT_USERNAME = os.getenv("ADMIN_DEFAULT_USERNAME", "admin")
    ADMIN_DEFAULT_EMAIL = os.getenv("ADMIN_DEFAULT_EMAIL", "admin@example.com")
    ADMIN_DEFAULT_PASSWORD = os.getenv("ADMIN_DEFAULT_PASSWORD", "AdminPass123!")
    SEED_STUDENT_USERNAME = os.getenv("SEED_STUDENT_USERNAME", "student")
    SEED_STUDENT_EMAIL = os.getenv("SEED_STUDENT_EMAIL", "student@example.com")
    SEED_STUDENT_PASSWORD = os.getenv("SEED_STUDENT_PASSWORD", "StudentPass123!")
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtppro.zoho.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() in {"1", "true", "yes"}
    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "false").lower() in {"1", "true", "yes"}
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "noreply@example.com")
    MAIL_DEFAULT_NAME = os.getenv("MAIL_DEFAULT_NAME", "SAT AI Tutor")
    MAIL_REPLY_TO = os.getenv("MAIL_REPLY_TO", "")
    MAIL_IMAP_SERVER = os.getenv("MAIL_IMAP_SERVER", "imappro.zoho.com")
    MAIL_IMAP_PORT = int(os.getenv("MAIL_IMAP_PORT", "993"))
    MAIL_IMAP_USE_SSL = os.getenv("MAIL_IMAP_USE_SSL", "true").lower() in {"1", "true", "yes"}
    if SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
        SQLALCHEMY_ENGINE_OPTIONS = {"poolclass": NullPool}
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True,
            "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
            "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
            "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
        }


class DevConfig(BaseConfig):
    DEBUG = True


class ProdConfig(BaseConfig):
    DEBUG = False


class TestConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite+pysqlite:///:memory:"
    JWT_SECRET_KEY = "test-secret"


CONFIG_ALIASES: dict[str, Type[BaseConfig]] = {
    "dev": DevConfig,
    "development": DevConfig,
    "prod": ProdConfig,
    "production": ProdConfig,
    "test": TestConfig,
    "testing": TestConfig,
}


@lru_cache
def resolve_config(name_or_class: Any) -> Any:
    """Resolve config argument to the object expected by `app.config.from_object`."""

    if name_or_class is None:
        return DevConfig
    if isinstance(name_or_class, str):
        return CONFIG_ALIASES.get(name_or_class, name_or_class)
    return name_or_class

