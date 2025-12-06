"""Helpers for difficulty rubric prompts and post-hoc calibration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from flask import current_app

from ..extensions import db
from ..models import Question, UserQuestionLog

DIFFICULTY_RUBRIC = """
Level 1 (Very Easy):
  - Single-step recall or direct lookup, no distractors.
  - Requires <30 seconds for a prepared student, >85% get it correct.
Level 2 (Easy):
  - Basic concept application or short calculation with 1 idea.
  - Contains mild distractors, solved in 30–60 seconds, 70–85% accuracy.
Level 3 (Medium):
  - Multi-step reasoning or pairing evidence, combines 2 ideas.
  - Normal SAT pace ~60–90 seconds, 55–70% accuracy.
Level 4 (Hard):
  - Requires chaining multiple deductions, tricky wording, or data synthesis.
  - Often >90 seconds, only 35–55% answer correctly.
Level 5 (Very Hard):
  - Expert-level inference or lengthy algebra, multiple traps.
  - >120 seconds for most candidates, <35% accuracy.
""".strip()


def difficulty_prompt_block() -> str:
    """Return a reusable text block for AI prompts."""
    return (
        "Use this SAT difficulty rubric when filling difficulty_level. "
        "Also produce a `difficulty_assessment` object describing the rationale, "
        "expected_time_sec, and primary obstacles so humans can audit it later:\n"
        f"{DIFFICULTY_RUBRIC}\n"
        "Example difficulty_assessment:\n"
        '{"level":3,"expected_time_sec":75,"rationale":"Two-step evidence match plus distractor elimination."}'
    )


def _infer_level_from_accuracy(accuracy: float) -> int:
    """Derive a suggested difficulty from observed accuracy."""
    if accuracy >= 0.85:
        return 1
    if accuracy >= 0.7:
        return 2
    if accuracy >= 0.55:
        return 3
    if accuracy >= 0.35:
        return 4
    return 5


def update_question_difficulty_stats(question: Question, log: UserQuestionLog) -> None:
    """Maintain rolling accuracy/time stats per question."""
    metadata: Dict[str, Any] = question.metadata_json or {}
    stats: Dict[str, Any] = metadata.get("difficulty_stats") or {
        "total_attempts": 0,
        "correct_attempts": 0,
        "avg_time_sec": None,
    }

    total_attempts = int(stats.get("total_attempts") or 0) + 1
    correct_attempts = int(stats.get("correct_attempts") or 0) + (1 if log.is_correct else 0)
    prev_avg_time = stats.get("avg_time_sec")
    time_spent = log.time_spent_sec or 0
    if time_spent and time_spent > 0:
        if prev_avg_time is None:
            avg_time = time_spent
        else:
            avg_time = (prev_avg_time * (total_attempts - 1) + time_spent) / total_attempts
    else:
        avg_time = prev_avg_time

    stats.update(
        {
            "total_attempts": total_attempts,
            "correct_attempts": correct_attempts,
            "avg_time_sec": avg_time,
            "last_observed_sec": time_spent,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    metadata["difficulty_stats"] = stats
    question.metadata_json = metadata

    min_samples = current_app.config.get("DIFFICULTY_AUTO_UPDATE_MIN_SAMPLES", 40)
    if total_attempts >= min_samples:
        observed_accuracy = correct_attempts / total_attempts if total_attempts else 0
        inferred_level = _infer_level_from_accuracy(observed_accuracy)
        existing_level = question.difficulty_level or inferred_level
        tolerance = current_app.config.get("DIFFICULTY_AUTO_UPDATE_TOLERANCE", 1)
        if abs(inferred_level - existing_level) >= tolerance:
            question.difficulty_level = inferred_level
            metadata.setdefault("difficulty_notes", {})
            metadata["difficulty_notes"]["auto_inferred_level"] = inferred_level
            metadata["difficulty_notes"]["observed_accuracy"] = round(observed_accuracy, 3)
            question.metadata_json = metadata

    db.session.add(question)

