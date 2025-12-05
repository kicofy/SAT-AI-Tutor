"""Diagnostic onboarding assessment service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Tuple

from werkzeug.exceptions import BadRequest
from sqlalchemy import func

from ..extensions import db
from ..models import DiagnosticAttempt, Question, StudySession
from .skill_taxonomy import iter_skill_tags, describe_skill, infer_section_from_tag

QUESTIONS_PER_SKILL = 2
SKILL_SEQUENCE = list(iter_skill_tags())
TOTAL_TARGET = QUESTIONS_PER_SKILL * len(SKILL_SEQUENCE)
COMPLETED_STATES = {"completed", "skipped"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def requires_diagnostic(user_id: int) -> bool:
    attempt = _latest_attempt(user_id)
    if attempt is None:
        return True
    return attempt.status not in COMPLETED_STATES


def get_status_payload(user_id: int) -> Tuple[dict, StudySession | None]:
    attempt = _latest_attempt(user_id)
    requires_flag = requires_diagnostic(user_id)
    session = _active_session_from_attempt(attempt)
    progress = _summarize_progress(attempt, session)
    attempt_payload = _serialize_attempt(attempt, progress)
    payload = {
        "requires_diagnostic": requires_flag,
        "attempt": attempt_payload,
        "progress": progress,
    }
    return payload, session


def start_attempt(user_id: int) -> Tuple[DiagnosticAttempt, StudySession]:
    attempt = _latest_attempt(user_id)
    if attempt and attempt.status in COMPLETED_STATES:
        raise BadRequest("diagnostic_already_completed")
    if attempt is None or attempt.status != "pending":
        attempt = DiagnosticAttempt(user_id=user_id, status="pending", total_questions=TOTAL_TARGET)
        db.session.add(attempt)
        db.session.commit()

    session = _active_session_from_attempt(attempt)
    if session:
        _ensure_session_fresh(session)
        return attempt, session

    questions, overrides = _build_question_bundle(user_id)
    attempt.total_questions = len(questions)
    attempt.result_summary = None
    attempt.status = "pending"
    attempt.started_at = attempt.started_at or _now()
    attempt.completed_at = None

    from . import session_service  # local import to avoid circular dependency

    session = session_service.create_session(
        user_id=user_id,
        questions=questions,
        session_type="diagnostic",
        question_overrides=overrides,
        diagnostic_attempt_id=attempt.id,
    )
    db.session.commit()
    session_service.refresh_assigned_questions(session)
    return attempt, session


def skip_attempt(user_id: int) -> DiagnosticAttempt:
    attempt = _latest_attempt(user_id)
    if attempt and attempt.status in COMPLETED_STATES:
        return attempt

    if attempt and attempt.session:
        from . import session_service  # local import

        session = attempt.session
        if session and session.ended_at is None:
            session_service.abort_session(session)

    if attempt is None:
        attempt = DiagnosticAttempt(user_id=user_id)
        db.session.add(attempt)

    attempt.status = "skipped"
    attempt.completed_at = _now()
    attempt.result_summary = {"status": "skipped"}
    attempt.session = None
    db.session.commit()
    return attempt


def handle_session_end(session: StudySession) -> None:
    attempt = session.diagnostic_attempt
    if not attempt:
        return
    stats = _summarize_progress(attempt, session)
    attempt.status = "completed"
    attempt.completed_at = _now()
    attempt.total_questions = stats.get("total_questions", attempt.total_questions or TOTAL_TARGET)
    attempt.result_summary = stats
    db.session.commit()


def handle_session_abort(session: StudySession) -> None:
    attempt = session.diagnostic_attempt
    if not attempt:
        return
    attempt.session = None
    db.session.commit()


def _latest_attempt(user_id: int) -> DiagnosticAttempt | None:
    if not user_id:
        return None
    return (
        DiagnosticAttempt.query.filter_by(user_id=user_id)
        .order_by(DiagnosticAttempt.started_at.desc())
        .first()
    )


def _active_session_from_attempt(attempt: DiagnosticAttempt | None) -> StudySession | None:
    if not attempt or not attempt.session:
        return None
    session = attempt.session
    if session.ended_at is not None:
        return None
    return session


def _ensure_session_fresh(session: StudySession) -> None:
    from . import session_service  # local import

    session_service.refresh_assigned_questions(session)


def _build_question_bundle(user_id: int) -> Tuple[List[Question], List[dict]]:
    used_ids: set[int] = set()
    questions: List[Question] = []
    overrides: List[dict] = []
    for skill_tag in SKILL_SEQUENCE:
        batch, extra_overrides = _fetch_for_skill(skill_tag, QUESTIONS_PER_SKILL, used_ids)
        questions.extend(batch)
        overrides.extend(extra_overrides)
    if len(questions) < TOTAL_TARGET:
        deficit = TOTAL_TARGET - len(questions)
        fallback_query = Question.query
        if used_ids:
            fallback_query = fallback_query.filter(~Question.id.in_(used_ids))
        fallback_questions = fallback_query.order_by(func.random()).limit(deficit).all()
        for idx, question in enumerate(fallback_questions):
            questions.append(question)
            overrides.append({"diagnostic_skill": SKILL_SEQUENCE[idx % len(SKILL_SEQUENCE)]})
            used_ids.add(question.id)
        if len(questions) < TOTAL_TARGET:
            deficit = TOTAL_TARGET - len(questions)
            repeat_pool = Question.query.order_by(func.random()).limit(deficit).all()
            for idx, question in enumerate(repeat_pool):
                questions.append(question)
                overrides.append({"diagnostic_skill": SKILL_SEQUENCE[idx % len(SKILL_SEQUENCE)]})
    if not questions:
        raise BadRequest("diagnostic_questions_unavailable")
    return questions, overrides


def _fetch_for_skill(skill_tag: str, target_count: int, used_ids: set[int]):
    batch: List[Question] = []
    overrides: List[dict] = []
    remaining = target_count
    primary_query = Question.query.filter(Question.skill_tags.contains([skill_tag]))
    if used_ids:
        primary_query = primary_query.filter(~Question.id.in_(used_ids))
    primary = primary_query.order_by(func.random()).limit(target_count * 3).all()
    for question in primary:
        if question.id in used_ids:
            continue
        batch.append(question)
        overrides.append({"diagnostic_skill": skill_tag})
        used_ids.add(question.id)
        remaining -= 1
        if remaining <= 0:
            break
    if remaining > 0:
        section = infer_section_from_tag(skill_tag)
        fallback_query = Question.query.filter(Question.section == section)
        if used_ids:
            fallback_query = fallback_query.filter(~Question.id.in_(used_ids))
        fallback = fallback_query.order_by(func.random()).limit(remaining * 3).all()
        for question in fallback:
            if question.id in used_ids:
                continue
            batch.append(question)
            overrides.append({"diagnostic_skill": skill_tag})
            used_ids.add(question.id)
            remaining -= 1
            if remaining <= 0:
                break
    if remaining > 0:
        random_fallback = (
            Question.query.order_by(func.random()).limit(remaining).all()
        )
        for question in random_fallback:
            batch.append(question)
            overrides.append({"diagnostic_skill": skill_tag})
    return batch, overrides


def _summarize_progress(
    attempt: DiagnosticAttempt | None, session: StudySession | None
) -> dict:
    skills: Dict[str, Dict[str, float]] = {
        tag: {"completed": 0, "total": 0} for tag in SKILL_SEQUENCE
    }
    total_questions = attempt.total_questions if attempt and attempt.total_questions else TOTAL_TARGET
    completed_questions = 0
    if session:
        assigned = session.questions_assigned or []
        done = {entry.get("question_id"): entry for entry in (session.questions_done or [])}
        for entry in assigned:
            tag = entry.get("diagnostic_skill") or _infer_fallback_tag(entry)
            if tag not in skills:
                skills[tag] = {"completed": 0, "total": 0}
            skills[tag]["total"] += 1
            question_id = entry.get("question_id")
            progress = done.get(question_id)
            if progress and progress.get("log_id"):
                skills[tag]["completed"] += 1
                completed_questions += 1
        total_questions = len(assigned) or total_questions
    elif attempt and attempt.result_summary:
        summary_skills = attempt.result_summary.get("skills", {})
        for tag, stats in summary_skills.items():
            skills.setdefault(tag, {"completed": 0, "total": 0})
            skills[tag]["total"] = stats.get("total", skills[tag]["total"])
            skills[tag]["completed"] = stats.get("correct", stats.get("completed", 0))
        completed_questions = attempt.result_summary.get("completed_questions", 0)
        total_questions = attempt.result_summary.get("total_questions", total_questions)
    return {
        "total_questions": int(total_questions),
        "completed_questions": int(completed_questions),
        "skills": [
            {
                "tag": tag,
                "label": describe_skill(tag)["label"],
                "completed": skills[tag]["completed"],
                "total": skills[tag]["total"] or QUESTIONS_PER_SKILL,
            }
            for tag in SKILL_SEQUENCE
        ],
    }


def _serialize_attempt(attempt: DiagnosticAttempt | None, progress: dict) -> dict | None:
    if not attempt:
        return None
    return {
        "id": attempt.id,
        "status": attempt.status,
        "total_questions": attempt.total_questions,
        "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
        "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None,
        "result_summary": attempt.result_summary,
        "progress_snapshot": progress,
    }


def _infer_fallback_tag(entry: dict) -> str:
    tags = entry.get("skill_tags") or []
    for tag in tags:
        if tag in SKILL_SEQUENCE:
            return tag
    return SKILL_SEQUENCE[0]

