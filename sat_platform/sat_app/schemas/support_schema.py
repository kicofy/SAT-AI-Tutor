"""Schemas for user suggestions and general settings."""

from __future__ import annotations

from marshmallow import Schema, fields, validate


class SuggestionSchema(Schema):
    title = fields.String(required=True, validate=validate.Length(min=1, max=120))
    content = fields.String(required=True, validate=validate.Length(min=1, max=4000))
    contact = fields.String(required=False, allow_none=True, validate=validate.Length(max=255))


class GeneralSettingsSchema(Schema):
    suggestion_email = fields.Email(allow_none=True, load_default=None)

