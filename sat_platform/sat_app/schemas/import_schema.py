"""Schemas for question import endpoints."""

from __future__ import annotations

from marshmallow import Schema, fields, validate


class QuestionBlockSchema(Schema):
    type = fields.String(required=True, validate=validate.OneOf(["text", "image", "binary"]))
    content = fields.String(load_default="")
    metadata = fields.Dict(load_default=dict)


class ManualParseSchema(Schema):
    blocks = fields.List(fields.Nested(QuestionBlockSchema), required=True, validate=validate.Length(min=1))

