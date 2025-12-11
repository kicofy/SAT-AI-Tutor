" ""Schemas for membership orders.""" 

from __future__ import annotations

from marshmallow import Schema, fields, validate


class MembershipOrderSchema(Schema):
    id = fields.Integer(dump_only=True)
    user_id = fields.Integer(dump_only=True)
    plan = fields.String()
    price_cents = fields.Integer()
    currency = fields.String()
    status = fields.String()
    user_note = fields.String(allow_none=True)
    admin_note = fields.String(allow_none=True)
    created_at = fields.DateTime()
    reviewed_at = fields.DateTime(allow_none=True)
    reviewed_by = fields.Integer(allow_none=True)
    user = fields.Nested("UserSchema", only=("id", "email", "username"), dump_only=True)


class MembershipOrderCreateSchema(Schema):
    plan = fields.String(required=True, validate=validate.OneOf(["monthly", "quarterly"]))
    note = fields.String(validate=validate.Length(max=255), allow_none=True)


class MembershipOrderDecisionSchema(Schema):
    action = fields.String(required=True, validate=validate.OneOf(["approve", "reject"]))
    note = fields.String(validate=validate.Length(max=255), allow_none=True)

