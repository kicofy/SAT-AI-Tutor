"""Authentication endpoints (register/login/me)."""

from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, request
from flask_jwt_extended import current_user, get_jwt_identity, jwt_required
from marshmallow import ValidationError
from sqlalchemy import func
from werkzeug.exceptions import BadRequest

from ..extensions import db
from ..models import User, UserProfile
from ..schemas import (
    AdminCreateSchema,
    LoginSchema,
    RegisterSchema,
    UpdateProfileSchema,
    PasswordChangeSchema,
    VerificationRequestSchema,
    UserSchema,
)
from ..utils import generate_access_token, hash_password, verify_password
from ..services import verification_service

auth_bp = Blueprint("auth_bp", __name__)

register_schema = RegisterSchema()
login_schema = LoginSchema()
admin_create_schema = AdminCreateSchema()
user_schema = UserSchema()
update_profile_schema = UpdateProfileSchema()
password_change_schema = PasswordChangeSchema()
verification_request_schema = VerificationRequestSchema()


@auth_bp.errorhandler(ValidationError)
def handle_validation_error(err: ValidationError):
    return jsonify({"errors": err.messages}), HTTPStatus.BAD_REQUEST


@auth_bp.get("/ping")
def ping():
    return jsonify({"module": "auth", "status": "ok"})


@auth_bp.post("/register")
def register():
    payload = register_schema.load(request.get_json() or {})
    email = payload["email"].lower()
    if User.query.filter_by(email=email).first():
        return (
            jsonify({"message": "Email already registered"}),
            HTTPStatus.CONFLICT,
        )

    username = None
    if payload.get("username"):
        username = payload["username"].lower()
        if User.query.filter(
            func.lower(User.username) == username
        ).first():
            return (
                jsonify({"message": "Username already taken"}),
                HTTPStatus.CONFLICT,
            )

    try:
        verification_service.consume_signup_code(email, payload["code"])
    except BadRequest as exc:
        return jsonify({"message": exc.description}), HTTPStatus.BAD_REQUEST

    profile_payload = payload.get("profile") or {}
    password = payload.pop("password")

    user = User(
        email=email,
        username=username,
        password_hash=hash_password(password),
        role="student",
        is_root=False,
        is_email_verified=True,
    )
    user.profile = _build_profile(profile_payload)

    db.session.add(user)
    db.session.commit()

    return (
        jsonify(
            {
                "access_token": generate_access_token(user),
                "user": user_schema.dump(user),
            }
        ),
        HTTPStatus.CREATED,
    )


@auth_bp.post("/register/request-code")
def request_register_code():
    payload = verification_request_schema.load(request.get_json() or {})
    try:
        verification_service.request_signup_code(
            payload["email"].lower(), payload.get("language_preference", "en")
        )
    except BadRequest as exc:
        return jsonify({"message": exc.description}), HTTPStatus.BAD_REQUEST
    return jsonify({"message": "sent"})


@auth_bp.post("/login")
def login():
    payload = login_schema.load(request.get_json() or {})
    identifier = payload["identifier"].strip()
    password = payload["password"]

    if "@" in identifier:
        user = User.query.filter_by(email=identifier.lower()).first()
    else:
        user = User.query.filter(
            func.lower(User.username) == identifier.lower()
        ).first()
    if not user or not verify_password(password, user.password_hash):
        return (
            jsonify({"message": "Invalid email or password"}),
            HTTPStatus.UNAUTHORIZED,
        )

    if not user.is_email_verified:
        return (
            jsonify(
                {
                    "error": "email_not_verified",
                    "email": user.email,
                }
            ),
            HTTPStatus.FORBIDDEN,
        )

    return jsonify(
        {"access_token": generate_access_token(user), "user": user_schema.dump(user)}
    )


@auth_bp.get("/me")
@jwt_required()
def me():
    user_identity = get_jwt_identity()
    user = None
    if user_identity is not None:
        user = db.session.get(User, int(user_identity))
    if user is None:
        return jsonify({"message": "User not found"}), HTTPStatus.NOT_FOUND
    return jsonify({"user": user_schema.dump(user)})


@auth_bp.patch("/profile")
@jwt_required()
def update_profile():
    payload = update_profile_schema.load(request.get_json() or {})
    if not payload:
        return jsonify({"message": "No changes supplied"}), HTTPStatus.BAD_REQUEST

    updated = False
    email = payload.get("email")
    language = payload.get("language_preference")

    if email and email.lower() != current_user.email:
        if User.query.filter_by(email=email.lower()).first():
            return jsonify({"message": "Email already registered"}), HTTPStatus.CONFLICT
        current_user.email = email.lower()
        updated = True

    if language:
        if not current_user.profile:
            current_user.profile = UserProfile(language_preference=language)
        else:
            current_user.profile.language_preference = language
        updated = True

    if not updated:
        return jsonify({"message": "No changes supplied"}), HTTPStatus.BAD_REQUEST

    db.session.commit()
    return jsonify({"user": user_schema.dump(current_user)})


@auth_bp.post("/password")
@jwt_required()
def change_password():
    payload = password_change_schema.load(request.get_json() or {})
    if not verify_password(payload["current_password"], current_user.password_hash):
        return jsonify({"message": "Incorrect current password"}), HTTPStatus.BAD_REQUEST
    current_user.password_hash = hash_password(payload["new_password"])
    db.session.commit()
    return jsonify({"message": "Password updated"})


@auth_bp.post("/admin/create")
@jwt_required()
def create_admin():
    if not getattr(current_user, "is_root", False):
        return (
            jsonify({"message": "Only root admin can create admin accounts"}),
            HTTPStatus.FORBIDDEN,
        )

    payload = admin_create_schema.load(request.get_json() or {})
    email = payload["email"].lower()
    username = payload["username"].lower()
    password = payload["password"]

    if User.query.filter_by(email=email).first():
        return jsonify({"message": "Email already registered"}), HTTPStatus.CONFLICT
    if User.query.filter(func.lower(User.username) == username).first():
        return jsonify({"message": "Username already taken"}), HTTPStatus.CONFLICT

    user = User(
        email=email,
        username=username,
        password_hash=hash_password(password),
        role="admin",
        is_root=False,
        is_email_verified=True,
    )
    user.profile = UserProfile(daily_available_minutes=60, language_preference="bilingual")

    db.session.add(user)
    db.session.commit()

    return (
        jsonify(
            {
                "message": "Admin account created",
                "user": user_schema.dump(user),
            }
        ),
        HTTPStatus.CREATED,
    )


def _build_profile(profile_payload: dict) -> UserProfile:
    sanitized = {
        key: value for key, value in profile_payload.items() if value is not None
    }
    return UserProfile(**sanitized)

