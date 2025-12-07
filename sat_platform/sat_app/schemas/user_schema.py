"""Schemas for user-related payloads."""

from __future__ import annotations

from marshmallow import EXCLUDE, Schema, fields, validate

ROLE_CHOICES = ("student", "admin")
LANG_CHOICES = ("en", "zh", "bilingual")


class UserProfileSchema(Schema):
    target_score_rw = fields.Integer(allow_none=True)
    target_score_math = fields.Integer(allow_none=True)
    exam_date = fields.Date(allow_none=True)
    daily_available_minutes = fields.Integer(validate=validate.Range(min=10, max=600))
    language_preference = fields.String(validate=validate.OneOf(LANG_CHOICES))


class RegisterSchema(Schema):
    email = fields.Email(required=True)
    password = fields.String(required=True, validate=validate.Length(min=8))
    username = fields.String(validate=validate.Length(min=3, max=64))
    code = fields.String(required=True, validate=validate.Length(equal=6))
    profile = fields.Nested(UserProfileSchema, load_default=dict)

    class Meta:
        unknown = EXCLUDE


class LoginSchema(Schema):
    identifier = fields.String(required=True)
    password = fields.String(required=True)


class AdminCreateSchema(Schema):
    email = fields.Email(required=True)
    username = fields.String(required=True, validate=validate.Length(min=3, max=64))
    password = fields.String(required=True, validate=validate.Length(min=8))


class PublicUserProfileSchema(UserProfileSchema):
    id = fields.Integer(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class UserSchema(Schema):
    id = fields.Integer(dump_only=True)
    email = fields.Email(dump_only=True)
    username = fields.String(dump_only=True)
    role = fields.String(dump_only=True)
    is_root = fields.Boolean(dump_only=True)
    is_email_verified = fields.Boolean(dump_only=True)
    is_active = fields.Boolean(dump_only=True)
    locked_reason = fields.String(dump_only=True, allow_none=True)
    locked_at = fields.DateTime(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    profile = fields.Nested(PublicUserProfileSchema, dump_only=True)


class UpdateProfileSchema(Schema):
    language_preference = fields.String(validate=validate.OneOf(LANG_CHOICES))


class PasswordChangeSchema(Schema):
    current_password = fields.String(required=True)
    new_password = fields.String(required=True, validate=validate.Length(min=8))


class PasswordResetRequestSchema(Schema):
    identifier = fields.String(required=True, validate=validate.Length(min=3, max=255))


class PasswordResetConfirmSchema(Schema):
    token = fields.String(required=True, validate=validate.Length(min=10))
    new_password = fields.String(required=True, validate=validate.Length(min=8))


class EmailVerifySchema(Schema):
    email = fields.Email(required=True)
    code = fields.String(required=True, validate=validate.Length(equal=6))


class EmailResendSchema(Schema):
    email = fields.Email(required=True)


class VerificationRequestSchema(Schema):
    email = fields.Email(required=True)
    language_preference = fields.String(validate=validate.OneOf(("en", "zh")), load_default="en")


class EmailChangeRequestSchema(Schema):
    new_email = fields.Email(required=True)


class EmailChangeConfirmSchema(Schema):
    new_email = fields.Email(required=True)
    code = fields.String(required=True, validate=validate.Length(equal=6))

