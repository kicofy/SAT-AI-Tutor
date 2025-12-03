"""AI-assisted diagnostic report generation."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from flask import current_app

from ..extensions import db
from ..models import DiagnosticReport, User
from .ai_client import get_ai_client
from . import analytics_service, score_predictor


def _build_prompt(user: User, predictor_payload: dict, progress: list[dict]) -> list[dict[str, str]]:
    system_prompt = (
        "You are an SAT diagnostics coach. Respond with JSON containing "
        "{protocol_version, score_summary, risk_factors, recommendations_en, recommendations_zh}. "
        "Use bilingual concise wording."
    )
    user_prompt = json.dumps(
        {
            "student": {"email": user.email, "level": user.profile.language_preference if user.profile else "en"},
            "predictor": predictor_payload,
            "progress": progress[-10:],
        },
        ensure_ascii=False,
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Generate diagnostic for: {user_prompt}"},
    ]


def _fallback_narrative(predictor_payload: dict, progress: list[dict]) -> dict:
    latest_accuracy = progress[-1]["accuracy"] if progress else None
    return {
        "protocol_version": "diagnostic.stub",
        "score_summary": predictor_payload,
        "risk_factors": [
            "AI diagnostic disabled; showing heuristic summary only.",
            f"Recent accuracy: {latest_accuracy:.2f}" if latest_accuracy is not None else "Insufficient data.",
        ],
        "recommendations_en": [
            "Continue focusing on weakest skills identified in mastery dashboard.",
            "Schedule an additional practice session this week.",
        ],
        "recommendations_zh": [
            "继续针对掌握度最低的技能练习。",
            "本周额外安排一次练习，巩固错题。",
        ],
    }


def _store_report(user_id: int, predictor_payload: dict, narrative: dict) -> DiagnosticReport:
    report = DiagnosticReport(
        user_id=user_id,
        generated_at=datetime.now(timezone.utc),
        predictor_payload=predictor_payload,
        narrative=narrative,
    )
    db.session.add(report)
    db.session.commit()
    return report


def generate_report(user_id: int) -> DiagnosticReport:
    user = User.query.get_or_404(user_id)
    progress = analytics_service.get_progress(user_id)
    predictor_payload = score_predictor.estimate_scores(user_id)

    if not current_app.config.get("AI_DIAGNOSTIC_ENABLE", True):
        narrative = _fallback_narrative(predictor_payload, progress)
        return _store_report(user_id, predictor_payload, narrative)

    client = get_ai_client()
    messages = _build_prompt(user, predictor_payload, progress)
    try:
        raw = client.chat(messages, model=current_app.config.get("AI_DIAGNOSTIC_MODEL"))
        content = raw["choices"][0]["message"]["content"]
        narrative = json.loads(content)
    except Exception as exc:  # pragma: no cover - fallback path
        current_app.logger.warning("AI diagnostic fallback due to error: %s", exc)
        narrative = _fallback_narrative(predictor_payload, progress)
    return _store_report(user_id, predictor_payload, narrative)

