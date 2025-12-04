"""Question bank models."""

from __future__ import annotations

from datetime import datetime, timezone

from ..extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class Passage(db.Model):
    __tablename__ = "passages"

    id = db.Column(db.Integer, primary_key=True)
    content_text = db.Column(db.Text, nullable=False)
    metadata_json = db.Column("metadata", db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    questions = db.relationship("Question", back_populates="passage")


class QuestionSet(db.Model):
    __tablename__ = "question_sets"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    type = db.Column(db.String(64), nullable=False)  # diagnostic, practice, etc.
    source = db.Column(db.String(255))
    metadata_json = db.Column("metadata", db.JSON)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    questions = db.relationship("Question", back_populates="question_set")


class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True)
    section = db.Column(db.String(32), nullable=False)  # RW / Math
    sub_section = db.Column(db.String(64))
    passage_id = db.Column(db.Integer, db.ForeignKey("passages.id"))
    question_set_id = db.Column(db.Integer, db.ForeignKey("question_sets.id"))
    stem_text = db.Column(db.Text, nullable=False)
    choices = db.Column(db.JSON, nullable=False)
    correct_answer = db.Column(db.JSON, nullable=False)
    difficulty_level = db.Column(db.Integer)
    irt_a = db.Column(db.Float)
    irt_b = db.Column(db.Float)
    skill_tags = db.Column(db.JSON)
    estimated_time_sec = db.Column(db.Integer)
    source = db.Column(db.String(255))
    page = db.Column(db.String(32))
    index_in_set = db.Column(db.Integer)
    metadata_json = db.Column("metadata", db.JSON)
    has_figure = db.Column(db.Boolean, nullable=False, server_default="0")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    passage = db.relationship("Passage", back_populates="questions")
    question_set = db.relationship("QuestionSet", back_populates="questions")


class QuestionFigure(db.Model):
    __tablename__ = "question_figures"

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=True)
    draft_id = db.Column(db.Integer, db.ForeignKey("question_drafts.id"), nullable=True)
    image_path = db.Column(db.String(512), nullable=False)
    description = db.Column(db.String(255))
    bbox = db.Column(db.JSON)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    question = db.relationship("Question", backref=db.backref("figures", lazy="dynamic"))


class QuestionExplanationCache(db.Model):
    __tablename__ = "question_explanations"

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False, index=True)
    language = db.Column(db.String(16), nullable=False, default="en")
    answer_value = db.Column(db.String(32))
    explanation = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    question = db.relationship("Question", backref=db.backref("explanations", lazy="dynamic"))

    __table_args__ = (
        db.UniqueConstraint(
            "question_id",
            "language",
            "answer_value",
            name="uq_question_explanations_question_language_answer",
        ),
    )

