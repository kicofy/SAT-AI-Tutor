from __future__ import annotations

from typing import Iterable
from types import SimpleNamespace

from flask import current_app

from ..extensions import db
from ..models import Question, QuestionExplanationCache
from . import ai_explainer
from sqlalchemy.exc import OperationalError
import time

DEFAULT_LANGUAGES = ("en", "zh")


def get_explanation(question_id: int, language: str) -> QuestionExplanationCache | None:
    return QuestionExplanationCache.query.filter_by(
        question_id=question_id,
        language=language,
    ).first()


def ensure_explanation(
    *,
    question: Question,
    language: str,
    source: str = "runtime",
    answer_payload: dict | None = None,
) -> QuestionExplanationCache:
    record = get_explanation(question.id, language)
    if record:
        return record
    payload = answer_payload or question.correct_answer
    explanation = ai_explainer.generate_explanation(
        question=question,
        user_answer=payload or question.correct_answer,
        user_language=language,
        depth="standard",
    )
    record = QuestionExplanationCache(
        question_id=question.id,
        language=language,
        explanation=explanation,
    )
    db.session.add(record)
    _commit_with_retry()
    return record


def ensure_explanations_for_languages(
    *,
    question: Question,
    languages: Iterable[str] | None = None,
    source: str = "runtime",
) -> dict[str, QuestionExplanationCache]:
    langs = list(languages or DEFAULT_LANGUAGES)
    results: dict[str, QuestionExplanationCache] = {}
    for lang in langs:
        try:
            results[lang] = ensure_explanation(question=question, language=lang, source=source)
        except ai_explainer.AiExplainerError as exc:  # pragma: no cover - defensive logging
            current_app.logger.warning(
                "Skipping explanation generation due to AI error",
                extra={"question_id": question.id, "language": lang, "error": str(exc)},
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            db.session.rollback()
            current_app.logger.exception(
                "Failed to generate explanation",
                extra={"question_id": question.id, "language": lang, "error": str(exc)},
            )
    return results


def delete_explanation(question_id: int, language: str | None = None) -> int:
    query = QuestionExplanationCache.query.filter_by(question_id=question_id)
    if language:
        query = query.filter_by(language=language)
    deleted = query.delete(synchronize_session=False)
    db.session.commit()
    return deleted


def _commit_with_retry(attempts: int = 5, base_delay: float = 0.2) -> None:
    """Commit with backoff to mitigate SQLite 'database is locked'."""
    for attempt in range(attempts):
        try:
            db.session.commit()
            return
        except OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == attempts - 1:
                db.session.rollback()
                raise
            db.session.rollback()
            time.sleep(base_delay * (attempt + 1))
    db.session.commit()


class _PayloadQuestion:
    def __init__(self, payload: dict):
        self.id = payload.get("id") or payload.get("question_uid") or payload.get("source_question_number") or 0
        self.section = payload.get("section") or "RW"
        self.sub_section = payload.get("sub_section")
        self.question_type = payload.get("question_type") or "choice"
        self.answer_schema = payload.get("answer_schema")
        self.stem_text = payload.get("stem_text") or ""
        self.choices = payload.get("choices") or {}
        self.correct_answer = payload.get("correct_answer") or {}
        self.skill_tags = payload.get("skill_tags") or []
        self.metadata_json = payload.get("metadata") or payload.get("metadata_json") or {}
        self.has_figure = bool(payload.get("has_figure"))
        self.page_image_b64 = None
        meta_img = self.metadata_json.get("page_image_b64")
        if isinstance(meta_img, str) and meta_img.strip():
            self.page_image_b64 = meta_img.strip()
        direct_img = payload.get("page_image_b64")
        if isinstance(direct_img, str) and direct_img.strip():
            self.page_image_b64 = direct_img.strip()
        # Accept pre-resolved figures (with image_url) from payload
        self.figures = []
        raw_figs = payload.get("figures") or []
        if isinstance(raw_figs, list):
            for fig in raw_figs:
                if not isinstance(fig, dict):
                    continue
                url = fig.get("image_url")
                if not url:
                    continue
                self.figures.append(
                    {
                        "id": fig.get("id"),
                        "description": fig.get("description"),
                        "image_url": url,
                    }
                )
        passage_payload = payload.get("passage")
        passage_text = None
        if isinstance(passage_payload, dict):
            passage_text = passage_payload.get("content_text") or passage_payload.get("text")
        if not passage_text:
            passage_text = self.metadata_json.get("passage_text") or self.metadata_json.get("passage_excerpt")
        self.passage = SimpleNamespace(content_text=passage_text) if passage_text else None


def generate_explanations_for_payload(payload: dict, languages: Iterable[str] | None = None) -> dict[str, dict]:
    question_like = _PayloadQuestion(payload)
    figures: list[dict] = []
    if question_like.has_figure and question_like.page_image_b64:
        figures.append({"id": "page", "description": "page_image", "image_url": question_like.page_image_b64})
    if question_like.figures:
        figures.extend(question_like.figures)
    # If has_figure but no usable image, log to aid debugging
    if question_like.has_figure and not figures:
        current_app.logger.warning(
            "AI explanation: has_figure but no images available", extra={"question_id": question_like.id}
        )
    langs = list(languages or DEFAULT_LANGUAGES)
    results: dict[str, dict] = {}
    for lang in langs:
        results[lang] = ai_explainer.generate_explanation(
            question=question_like,
            user_answer=payload.get("correct_answer"),
            user_language=lang,
            depth="standard",
            figures=figures,
        )
    return results


def store_precomputed_explanations(
    question: Question, explanations: dict[str, dict] | None
) -> dict[str, QuestionExplanationCache]:
    stored: dict[str, QuestionExplanationCache] = {}
    if not explanations:
        return stored
    for lang, explanation in explanations.items():
        if not explanation:
            continue
        existing = get_explanation(question.id, lang)
        if existing:
            stored[lang] = existing
            continue
        record = QuestionExplanationCache(
            question_id=question.id,
            language=lang,
            explanation=explanation,
        )
        db.session.add(record)
        stored[lang] = record
    return stored

