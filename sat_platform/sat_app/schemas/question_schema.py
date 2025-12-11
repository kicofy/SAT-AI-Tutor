"""Schemas for question CRUD."""

from __future__ import annotations

from marshmallow import Schema, fields, validate

SECTION_CHOICES = ("RW", "Math")


class PassageSchema(Schema):
    id = fields.Integer(dump_only=True)
    content_text = fields.String(required=True)
    metadata = fields.Dict(attribute="metadata_json", data_key="metadata", load_default=None)


class QuestionSourceSchema(Schema):
    id = fields.Integer(dump_only=True)
    filename = fields.String(dump_only=True)
    original_name = fields.String(dump_only=True)
    total_pages = fields.Integer(dump_only=True)


class QuestionCreateSchema(Schema):
    section = fields.String(required=True, validate=validate.OneOf(SECTION_CHOICES))
    sub_section = fields.String(allow_none=True)
    passage_id = fields.Integer(load_default=None, allow_none=True)
    question_set_id = fields.Integer(load_default=None, allow_none=True)
    passage = fields.Nested(PassageSchema, load_default=None)
    stem_text = fields.String(required=True)
    choices = fields.Dict(required=True)
    correct_answer = fields.Dict(required=True)
    difficulty_level = fields.Integer(validate=validate.Range(min=1, max=5), allow_none=True, load_default=None)
    irt_a = fields.Float(allow_none=True)
    irt_b = fields.Float(allow_none=True)
    skill_tags = fields.List(fields.String())
    estimated_time_sec = fields.Integer(allow_none=True, load_default=None)
    question_type = fields.String(load_default="choice")
    answer_schema = fields.Dict(load_default=None)
    source = fields.String()
    source_page = fields.Integer(allow_none=True, load_default=None)
    page = fields.String(allow_none=True, load_default=None)
    index_in_set = fields.Integer(allow_none=True, load_default=None)
    metadata = fields.Dict(attribute="metadata_json", data_key="metadata", load_default=None)
    has_figure = fields.Boolean(load_default=False)
    # Optional hint from ingestion: which choices require a figure/table capture.
    choice_figure_keys = fields.List(fields.String(), load_default=list)
    source_id = fields.Integer(load_default=None, allow_none=True)


class QuestionSchema(QuestionCreateSchema):
    id = fields.Integer(dump_only=True)
    question_uid = fields.String(dump_only=True)
    source_id = fields.Integer(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
    passage = fields.Nested(PassageSchema, dump_only=True)
    source = fields.Nested(QuestionSourceSchema, dump_only=True)

