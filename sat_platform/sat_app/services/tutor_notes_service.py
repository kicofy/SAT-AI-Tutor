"""Generate and cache AI-powered tutor notes."""

from __future__ import annotations

import json
from typing import List, Tuple

from flask import current_app

from ..extensions import db
from ..models import TutorNote, User, StudySession
from .learning_plan_service import get_or_generate_plan, _resolve_today, _resolve_language
from .adaptive_engine import get_mastery_snapshot
from .ai_client import get_ai_client


def _serialize_session(session: StudySession) -> dict:
    summary = session.summary or {}
    return {
        "id": session.id,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "summary": summary,
        "questions_done": len(session.questions_done or []),
    }


def _prepare_mastery_payload(mastery_entries: List[dict]) -> Tuple[List[dict], dict]:
    transformed: List[dict] = []
    missing_labels: List[str] = []
    observed = 0
    for entry in mastery_entries:
        label = entry.get("label") or entry.get("skill_tag")
        observed_score = entry.get("observed_score")
        has_data = bool(entry.get("has_data") or entry.get("sample_count", 0))
        if has_data:
            observed += 1
        else:
            missing_labels.append(label)
        transformed.append(
            {
                "skill_tag": entry.get("skill_tag"),
                "label": label,
                "has_data": has_data,
                "observed_score": observed_score,
                "observed_percent": round(observed_score * 100, 1) if isinstance(observed_score, (int, float)) else None,
                "last_practiced_at": entry.get("last_practiced_at"),
            }
        )
    total = len(mastery_entries)
    summary = {
        "total_skills": total,
        "skills_with_data": observed,
        "skills_without_data": total - observed,
        "missing_skill_labels": missing_labels,
    }
    return transformed, summary


def _build_payload(user: User, plan_detail: dict, sessions: List[StudySession], mastery: List[dict]) -> dict:
    session_payload = [_serialize_session(s) for s in sessions]
    mastery_payload, mastery_summary = _prepare_mastery_payload(mastery)
    return {
        "student": {
            "id": user.id,
            "email": user.email,
            "language": _resolve_language(user.profile),
            "target_minutes": plan_detail.get("target_minutes"),
            "target_questions": plan_detail.get("target_questions"),
        },
        "plan": plan_detail,
        "sessions": session_payload,
        "mastery": mastery_payload,
        "meta": {
            "recent_session_count": len(session_payload),
            "has_recent_sessions": bool(session_payload),
            "has_mastery_observations": mastery_summary["skills_with_data"] > 0,
            "missing_mastery_skills": mastery_summary["missing_skill_labels"],
            "mastery_summary": mastery_summary,
        },
    }


def _fallback_notes(language: str, plan_detail: dict, has_history: bool) -> dict:
    if has_history:
        body_en = (
            "Keep following today's plan: "
            f"{plan_detail.get('target_minutes')} min · {plan_detail.get('target_questions')} questions."
        )
        body_zh = (
            f"继续执行今天的 {plan_detail.get('target_minutes')} 分钟 · {plan_detail.get('target_questions')} 题计划。"
        )
        if language == "zh":
            return {"notes": [{"title": "今日目标", "body": body_zh, "priority": "info"}]}
        return {"notes": [{"title": "Today's target", "body": body_en, "priority": "info"}]}

    body_en = (
        "You're just starting—focus on finishing "
        f"{plan_detail.get('target_minutes')} min · {plan_detail.get('target_questions')} questions in order."
    )
    body_zh = (
        "目前还没有练习记录，先按顺序完成 "
        f"{plan_detail.get('target_minutes')} 分钟 · {plan_detail.get('target_questions')} 题。"
    )
    if language == "zh":
        return {"notes": [{"title": "新用户提示", "body": body_zh, "priority": "info"}]}
    return {"notes": [{"title": "New student tip", "body": body_en, "priority": "info"}]}


def _call_ai(payload: dict, language: str) -> dict:
    client = get_ai_client()
    system_prompt = (
        "You are an SAT study tutor. Respond with compact JSON: "
        '{"notes":[{"title":"","body":"","priority":"info|warning|success"}]}. '
        "Return at most 3 notes, each no more than 25 words. Use the student's language preference."
        "If meta.has_recent_sessions is false, treat the student as brand new and mention that practice data is not yet available."
        "Mastery items include has_data and observed_score. Only cite percentages when has_data is true."
        "When has_data is false, explicitly state that there is no data for that skill instead of assuming 50%."
    )
    user_prompt = json.dumps(payload, ensure_ascii=False)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Student language: {language}\nData: {user_prompt}"},
    ]
    response = client.chat(messages, model=current_app.config.get("AI_TUTOR_NOTES_MODEL"))
    try:
        content = response.content[0].text if hasattr(response, "content") else response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, AttributeError):
        content = "{}"
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {}
    notes = parsed.get("notes") if isinstance(parsed, dict) else None
    if not isinstance(notes, list):
        return {}
    compact = []
    for entry in notes[:3]:
        title = entry.get("title")
        body = entry.get("body")
        if not title or not body:
            continue
        compact.append(
            {
                "title": title.strip(),
                "body": body.strip(),
                "priority": entry.get("priority", "info"),
            }
        )
    return {"notes": compact}


def get_or_generate_tutor_notes(user_id: int) -> dict:
    today = _resolve_today()
    cached = TutorNote.query.filter_by(user_id=user_id, plan_date=today).first()
    if cached:
        return cached.payload

    user = db.session.get(User, user_id)
    if not user:
        raise ValueError("User not found")

    plan = get_or_generate_plan(user_id)
    plan_detail = plan.generated_detail or {}
    language = _resolve_language(user.profile)
    sessions = (
        StudySession.query.filter_by(user_id=user_id)
        .order_by(StudySession.started_at.desc())
        .limit(10)
        .all()
    )
    mastery = get_mastery_snapshot(user_id)
    payload = _build_payload(user, plan_detail, sessions, mastery)
    has_history = bool(sessions)

    notes_payload = {}
    config_flag = current_app.config.get("AI_TUTOR_NOTES_ENABLE")
    if config_flag is None:
        config_flag = current_app.config.get("AI_COACH_NOTES_ENABLE", True)
    if config_flag:
        try:
            notes_payload = _call_ai(payload, language)
        except Exception as exc:  # pragma: no cover - defensive
            current_app.logger.warning("Tutor notes AI failed: %s", exc)

    if not notes_payload.get("notes"):
        notes_payload = _fallback_notes(language, plan_detail, has_history)

    record = TutorNote(
        user_id=user_id,
        plan_date=today,
        language=language,
        payload=notes_payload,
    )
    db.session.add(record)
    db.session.commit()
    return notes_payload

