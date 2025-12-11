"""Schemas for study session APIs."""

from __future__ import annotations

from marshmallow import Schema, fields, validate


class SessionStartSchema(Schema):
    num_questions = fields.Integer(load_default=10, validate=validate.Range(min=1, max=50))
    section = fields.String(load_default=None)
    source_id = fields.Integer(load_default=None, allow_none=True)


class SessionAnswerSchema(Schema):
    session_id = fields.Integer(required=True)
    question_id = fields.Integer(required=True)
    user_answer = fields.Dict(required=True)
    time_spent_sec = fields.Integer(load_default=None)


class SessionExplanationSchema(Schema):
    session_id = fields.Integer(required=True)
    question_id = fields.Integer(required=True)


class SessionSchema(Schema):
    id = fields.Integer(dump_only=True)
    user_id = fields.Integer(dump_only=True)
    started_at = fields.DateTime(dump_only=True)
    ended_at = fields.DateTime(dump_only=True, allow_none=True)
    questions_assigned = fields.List(fields.Dict())
    questions_done = fields.List(fields.Dict(), dump_only=True)
    summary = fields.Dict(dump_only=True)
    plan_block_id = fields.String(dump_only=True)
    session_type = fields.String(dump_only=True)
    diagnostic_attempt_id = fields.Integer(dump_only=True, allow_none=True)

