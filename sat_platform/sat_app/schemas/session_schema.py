"""Schemas for study session APIs."""

from __future__ import annotations

from marshmallow import Schema, fields, validate


class SessionStartSchema(Schema):
    num_questions = fields.Integer(load_default=10, validate=validate.Range(min=1, max=50))
    section = fields.String(load_default=None)


class SessionAnswerSchema(Schema):
    session_id = fields.Integer(required=True)
    question_id = fields.Integer(required=True)
    user_answer = fields.Dict(required=True)
    time_spent_sec = fields.Integer(load_default=None)


class SessionSchema(Schema):
    id = fields.Integer(dump_only=True)
    user_id = fields.Integer(dump_only=True)
    started_at = fields.DateTime(dump_only=True)
    ended_at = fields.DateTime(dump_only=True)
    questions_assigned = fields.List(fields.Dict())
    questions_done = fields.Dict()
    summary = fields.Dict()

