"""Security helpers (password hashing, JWT token helpers)."""

from __future__ import annotations

from typing import Any, Dict

from flask_jwt_extended import create_access_token
from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using Werkzeug's PBKDF2 defaults."""

    return generate_password_hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Return True if the plaintext password matches the stored hash."""

    return check_password_hash(password_hash, plain_password)


def generate_access_token(user) -> str:
    """Create a JWT access token embedding the user's ID and role."""

    claims: Dict[str, Any] = {"role": user.role}
    return create_access_token(identity=str(user.id), additional_claims=claims)

