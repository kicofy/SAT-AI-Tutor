"""Learning session service functions."""

from __future__ import annotations

from datetime import datetime, timezone
from time import sleep
from typing import List, Optional, Dict, Iterable

from sqlalchemy.exc import OperationalError
from sqlalchemy import or_
from flask import current_app, url_for
import re
from sqlalchemy.orm.attributes import flag_modified

from ..extensions import db
from ..models import Question, StudySession, UserQuestionLog
from . import adaptive_engine, spaced_repetition, analytics_service
from .difficulty_service import update_question_difficulty_stats


def _round_robin_by_difficulty(candidates: Iterable[Question], limit: int) -> List[Question]:
    """Ensure we don't return only 'easy' questions when variety exists."""
    buckets: Dict[int, List[Question]] = {}
    for question in candidates:
        level = question.difficulty_level or 2
        buckets.setdefault(level, []).append(question)
    order = [3, 2, 4, 1, 5]
    picked: List[Question] = []
    while len(picked) < limit and any(buckets.values()):
        for level in order:
            bucket = buckets.get(level)
            if bucket:
                picked.append(bucket.pop())
                if len(picked) >= limit:
                    break
        else:
            break
    if len(picked) < limit:
        for bucket in buckets.values():
            while bucket and len(picked) < limit:
                picked.append(bucket.pop())
    return picked[:limit]


def select_questions(
    user_id: int,
    num_questions: int,
    section: str | None = None,
    focus_skill: str | None = None,
    exclude_ids: Optional[Iterable[int]] = None,
    source_id: int | None = None,
) -> List[Question]:
    excluded_set = {int(qid) for qid in (exclude_ids or [])}
    if source_id:
        query = Question.query.filter_by(source_id=source_id)
        if section:
            query = query.filter_by(section=section)
        pool = [q for q in query.order_by(Question.id.asc()).all() if q.id not in excluded_set]
        # Admin “test this collection” expects all questions in the collection, not a sample.
        return pool

    last_summary = get_last_session_summary(user_id)
    initial = adaptive_engine.select_next_questions(
        user_id=user_id,
        num_questions=num_questions,
        section=section,
        focus_skill=focus_skill,
        last_summary=last_summary,
    )
    filtered: List[Question] = [q for q in initial if q.id not in excluded_set]
    if len(filtered) >= num_questions:
        return filtered[:num_questions]

    needed = num_questions - len(filtered)
    used_ids = {q.id for q in filtered}.union(excluded_set)

    query = Question.query
    if section:
        query = query.filter_by(section=section)
    if focus_skill:
        filtered_query = query.filter(Question.skill_tags.contains([focus_skill]))
        fallback = [q for q in filtered_query.order_by(db.func.random()).all() if q.id not in used_ids]
        if not fallback:
            fallback = [q for q in query.order_by(db.func.random()).all() if q.id not in used_ids]
        prioritized = [q for q in fallback if focus_skill in (q.skill_tags or [])]
        prioritized.extend([q for q in fallback if focus_skill not in (q.skill_tags or [])])
        extras = _round_robin_by_difficulty(prioritized, needed)
    else:
        fallback = [q for q in query.order_by(db.func.random()).all() if q.id not in used_ids]
        extras = _round_robin_by_difficulty(fallback, needed)

    filtered.extend(extras)
    return filtered[:num_questions]


def create_session(
    user_id: int,
    questions: List[Question],
    *,
    plan_block_id: str | None = None,
    session_type: str = "practice",
    diagnostic_attempt_id: int | None = None,
    question_overrides: List[dict] | None = None,
) -> StudySession:
    serialized: List[dict] = []
    overrides = question_overrides or []
    for idx, question in enumerate(questions):
        payload = _serialize_question(question)
        extra = overrides[idx] if idx < len(overrides) else None
        if isinstance(extra, dict):
            for key, value in extra.items():
                if value is not None:
                    payload[key] = value
        serialized.append(payload)
    session = StudySession(
        user_id=user_id,
        questions_assigned=serialized,
        questions_done=[],
        plan_block_id=plan_block_id,
        session_type=session_type,
        diagnostic_attempt_id=diagnostic_attempt_id,
    )
    db.session.add(session)
    _commit_with_retry()
    return session


def _eval_choice_answer(question: Question, user_answer: dict) -> bool:
    return user_answer == question.correct_answer


def _parse_numeric(value: str):
    raw = value.strip().replace(" ", "")
    if not raw:
        return None
    # simple fraction support
    if "/" in raw and all(part.replace(".", "", 1).lstrip("-").isdigit() for part in raw.split("/", 1)):
        try:
            num, den = raw.split("/", 1)
            return float(num) / float(den)
        except Exception:
            return None
    try:
        return float(raw)
    except Exception:
        return None


def _eval_fill_answer(question: Question, user_answer: dict) -> bool:
    schema = getattr(question, "answer_schema", {}) or {}
    if not isinstance(schema, dict):
        schema = {}
    acceptable = schema.get("acceptable") or []
    if not acceptable:
        return False
    user_val = (user_answer or {}).get("value")
    if user_val is None:
        return False
    user_raw = str(user_val).strip()
    if not user_raw:
        return False
    ans_type = schema.get("type") or "text"
    if ans_type == "numeric":
        tol = schema.get("tolerance")
        # Build numeric set from acceptable
        targets = []
        for acc in acceptable:
            parsed = _parse_numeric(str(acc))
            if parsed is not None:
                targets.append(parsed)
        user_num = _parse_numeric(user_raw)
        if user_num is None or not targets:
            return False
        for target in targets:
            if tol is not None:
                try:
                    tol_f = float(tol)
                except Exception:
                    tol_f = None
                if tol_f is not None and abs(user_num - target) <= tol_f:
                    return True
            if user_num == target:
                return True
        return False
    else:
        # textual strict match (case-insensitive, trim)
        for acc in acceptable:
            if user_raw.lower() == str(acc).strip().lower():
                return True
        return False


def log_answer(session: StudySession, question: Question, payload: dict, user_id: int) -> UserQuestionLog:
    qtype = getattr(question, "question_type", "choice") or "choice"
    if qtype == "fill":
        is_correct = _eval_fill_answer(question, payload.get("user_answer") or {})
    else:
        is_correct = _eval_choice_answer(question, payload.get("user_answer") or {})
    log = UserQuestionLog(
        user_id=user_id,
        study_session_id=session.id,
        question_id=question.id,
        is_correct=is_correct,
        user_answer=payload["user_answer"],
        time_spent_sec=payload.get("time_spent_sec"),
    )
    db.session.add(log)
    db.session.flush()
    _append_question_progress(session, question, log)
    adaptive_engine.update_mastery_from_log(log, question)
    spaced_repetition.schedule_from_log(log)
    analytics_service.record_question_result(user_id, question, is_correct)
    try:
        update_question_difficulty_stats(question, log)
    except Exception:  # pragma: no cover - defensive
        current_app = None
        try:
            from flask import current_app  # lazy import to avoid circularity

            current_app.logger.warning("Failed to update difficulty stats", exc_info=True)
        except Exception:
            pass
    return log


def end_session(session: StudySession) -> StudySession:
    session.ended_at = datetime.now(timezone.utc)
    session.summary = _build_session_summary(session)
    _commit_with_retry()
    analytics_service.record_session_complete(session.user_id)
    _commit_with_retry()
    if session.plan_block_id:
        from . import learning_plan_service

        learning_plan_service.handle_session_end(session)
    if session.session_type == "diagnostic":
        from . import diagnostic_service

        diagnostic_service.handle_session_end(session)
    return session


def abort_session(session: StudySession) -> StudySession:
    session.ended_at = datetime.now(timezone.utc)
    _commit_with_retry()
    if session.plan_block_id:
        from . import learning_plan_service

        learning_plan_service.handle_session_abort(session)
    if session.session_type == "diagnostic":
        from . import diagnostic_service

        diagnostic_service.handle_session_abort(session)
    return session


def get_active_session(user_id: int, *, include_plan: bool = True) -> Optional[StudySession]:
    query = StudySession.query.filter_by(user_id=user_id, ended_at=None)
    if not include_plan:
        query = query.filter(StudySession.session_type != "plan")
    return query.order_by(StudySession.started_at.desc()).first()


def get_last_session_summary(user_id: int) -> Optional[dict]:
    session = (
        StudySession.query.filter_by(user_id=user_id)
        .filter(StudySession.summary.isnot(None))
        .order_by(StudySession.ended_at.desc())
        .first()
    )
    if session is None:
        return None
    return session.summary


def _serialize_question(question: Question) -> dict:
    payload: dict = {
        "question_id": question.id,
        "question_uid": getattr(question, "question_uid", None),
        "section": question.section,
        "stem_text": question.stem_text,
        "question_type": getattr(question, "question_type", "choice") or "choice",
        "choices": question.choices,
        "skill_tags": question.skill_tags or [],
    }
    if getattr(question, "answer_schema", None):
        payload["answer_schema"] = question.answer_schema
    metadata = getattr(question, "metadata_json", None)
    if metadata:
        payload["metadata"] = metadata
    if question.correct_answer is not None:
        payload["correct_answer"] = question.correct_answer
    if question.sub_section:
        payload["sub_section"] = question.sub_section
    if question.passage:
        passage_payload = {
            "id": question.passage.id,
            "content_text": question.passage.content_text,
        }
        metadata = getattr(question.passage, "metadata_json", None)
        if metadata:
            passage_payload["metadata"] = metadata
        payload["passage"] = passage_payload
    payload["has_figure"] = bool(getattr(question, "has_figure", False))
    figure_query = getattr(question, "figures", None)
    figures = []
    choice_figures: dict[str, dict] = {}
    if figure_query is not None:
        try:
            figure_list = figure_query.all()
        except Exception:  # pragma: no cover - defensive fallback
            figure_list = []
        for figure in figure_list:
            if not getattr(figure, "image_path", None):
                continue
            ref = {
                "id": figure.id,
                "description": figure.description,
                "bbox": figure.bbox,
                "url": url_for(
                    "learning_bp.get_question_figure_image",
                    figure_id=figure.id,
                    _external=False,
                ),
            }
            figures.append(ref)
            desc = (figure.description or "").lower()
            match = re.search(r"choice\s+([a-d])", desc)
            if match:
                key = match.group(1).upper()
                choice_figures[key] = ref
    if figures:
        payload["figures"] = figures
        payload["has_figure"] = True
    if choice_figures:
        payload["choice_figures"] = choice_figures
    return payload


def serialize_question(question: Question) -> dict:
    """Public helper to serialize questions for client consumption."""
    return _serialize_question(question)


def refresh_assigned_questions(session: StudySession | None, *, commit: bool = True):
    if session is None:
        return None
    assigned = session.questions_assigned or []
    if not assigned:
        return session
    answered_ids = {
        entry.get("question_id")
        for entry in (session.questions_done or [])
        if entry.get("question_id") and entry.get("log_id")
    }
    original_count = len(assigned)
    question_ids = [entry.get("question_id") for entry in assigned if entry.get("question_id")]
    questions = Question.query.filter(Question.id.in_(question_ids)).all() if question_ids else []
    serialized_map = {question.id: _serialize_question(question) for question in questions}
    refreshed_entries = []
    used_ids = set(serialized_map.keys())
    mutated = False

    for entry in assigned:
        question_id = entry.get("question_id")
        diagnostic_skill = entry.get("diagnostic_skill")
        updated = serialized_map.get(question_id)
        if updated:
            if entry.get("unavailable_reason"):
                mutated = True
                updated = dict(updated)
                updated.pop("unavailable_reason", None)
            if diagnostic_skill:
                updated = dict(updated)
                updated["diagnostic_skill"] = diagnostic_skill
            refreshed_entries.append(updated)
            if updated != entry:
                mutated = True
            continue

        if question_id and question_id in answered_ids:
            fallback = dict(entry)
            fallback["unavailable_reason"] = "question_deleted"
            mutated = True
            refreshed_entries.append(fallback)
            continue

        replacement = _select_replacement_question(
            section=entry.get("section"),
            sub_section=entry.get("sub_section"),
            skill_tags=entry.get("skill_tags"),
            exclude_ids=used_ids,
        )
        if replacement:
            serialized = _serialize_question(replacement)
            if diagnostic_skill:
                serialized["diagnostic_skill"] = diagnostic_skill
            used_ids.add(replacement.id)
            refreshed_entries.append(serialized)
            mutated = True
        else:
            mutated = True

    needed = original_count - len(refreshed_entries)
    if needed > 0:
        extras = _top_up_questions(session.user_id, needed, exclude_ids=used_ids, section=_dominant_section(refreshed_entries or assigned))
        if extras:
            refreshed_entries.extend(extras)
            used_ids.update([entry["question_id"] for entry in extras if entry.get("question_id")])
            mutated = True

    if not refreshed_entries:
        reseeded = _reseed_session_questions(session, original_count)
        if reseeded:
            refreshed_entries = reseeded
            mutated = True

    if mutated:
        session.questions_assigned = refreshed_entries
        flag_modified(session, "questions_assigned")
        if commit:
            _commit_with_retry()
    else:
        session.questions_assigned = refreshed_entries
    return session


def _select_replacement_question(
    *,
    section: str | None,
    sub_section: str | None,
    skill_tags: list[str] | None,
    exclude_ids: set[int],
):
    query = Question.query
    if section:
        query = query.filter(Question.section == section)
    if sub_section:
        query = query.filter(Question.sub_section == sub_section)
    if skill_tags:
        conditions = [Question.skill_tags.contains([tag]) for tag in skill_tags if tag]
        if conditions:
            query = query.filter(or_(*conditions))
    if exclude_ids:
        query = query.filter(~Question.id.in_(exclude_ids))
    candidates = query.order_by(db.func.random()).limit(10).all()
    if not candidates and section:
        fallback = Question.query.filter(Question.section == section)
        if exclude_ids:
            fallback = fallback.filter(~Question.id.in_(exclude_ids))
        candidates = fallback.order_by(db.func.random()).limit(10).all()
    if not candidates:
        return None
    if skill_tags:
        target_set = set(skill_tags)
        candidates.sort(
            key=lambda q: len(target_set.intersection(set(q.skill_tags or []))),
            reverse=True,
        )
    return candidates[0]


def _top_up_questions(user_id: int, needed: int, *, exclude_ids: set[int], section: str | None):
    if needed <= 0:
        return []
    questions = select_questions(user_id=user_id, num_questions=needed, section=section)
    filtered = []
    for question in questions:
        if question.id in exclude_ids:
            continue
        exclude_ids.add(question.id)
        filtered.append(_serialize_question(question))
        if len(filtered) >= needed:
            break
    return filtered


def _dominant_section(entries: List[dict]):
    sections: dict[str, int] = {}
    for entry in entries:
        section = entry.get("section")
        if section:
            sections[section] = sections.get(section, 0) + 1
    if not sections:
        return None
    return max(sections, key=sections.get)


def _reseed_session_questions(session: StudySession, desired_count: int):
    if session.session_type == "diagnostic":
        return session.questions_assigned or []
    count = max(desired_count, 1)
    questions = select_questions(session.user_id, num_questions=count)
    if not questions:
        session.questions_assigned = []
        flag_modified(session, "questions_assigned")
        session.questions_done = []
        flag_modified(session, "questions_done")
        return []
    serialized = [_serialize_question(question) for question in questions]
    session.questions_assigned = serialized
    flag_modified(session, "questions_assigned")
    session.questions_done = []
    flag_modified(session, "questions_done")
    return serialized


def _append_question_progress(session: StudySession, question: Question, log: UserQuestionLog) -> None:
    progress_list = session.questions_done or []
    diagnostic_skill = None
    for assigned in session.questions_assigned or []:
        if assigned.get("question_id") == question.id:
            diagnostic_skill = assigned.get("diagnostic_skill")
            break
    for entry in progress_list:
        if entry.get("question_id") == question.id:
            entry.update(
                {
                    "log_id": log.id,
                    "answered_at": log.answered_at.isoformat(),
                    "is_correct": log.is_correct,
                    "user_answer": log.user_answer,
                    "diagnostic_skill": diagnostic_skill or entry.get("diagnostic_skill"),
                }
            )
            break
    else:
        progress_list.append(
            {
                "question_id": question.id,
                "log_id": log.id,
                "answered_at": log.answered_at.isoformat(),
                "is_correct": log.is_correct,
                "user_answer": log.user_answer,
                "diagnostic_skill": diagnostic_skill,
            }
        )
    session.questions_done = progress_list
    flag_modified(session, "questions_done")


def _commit_with_retry(max_attempts: int = 3, delay: float = 0.2) -> None:
    last_error: OperationalError | None = None
    for _ in range(max_attempts):
        try:
            db.session.commit()
            return
        except OperationalError as exc:  # pragma: no cover - sqlite specific
            last_error = exc
            if "database is locked" not in str(exc).lower():
                raise
            db.session.rollback()
            sleep(delay)
    if last_error:
        raise last_error


def _build_session_summary(session: StudySession) -> Optional[dict]:
    progress_list = session.questions_done or []
    if not progress_list:
        return None
    question_ids = [entry.get("question_id") for entry in progress_list if entry.get("question_id")]
    if not question_ids:
        return None
    questions = Question.query.filter(Question.id.in_(question_ids)).all()
    question_map = {question.id: question for question in questions}
    skills: dict[str, dict[str, float]] = {}
    total = 0
    correct = 0
    for entry in progress_list:
        qid = entry.get("question_id")
        question = question_map.get(qid)
        if question is None:
            continue
        total += 1
        if entry.get("is_correct"):
            correct += 1
        for tag in (question.skill_tags or []):
            stats = skills.setdefault(tag, {"total": 0, "correct": 0})
            stats["total"] += 1
            if entry.get("is_correct"):
                stats["correct"] += 1
    for tag, stats in skills.items():
        total_count = stats.get("total") or 0
        if total_count:
            stats["accuracy"] = stats.get("correct", 0) / total_count
    overall_accuracy = correct / total if total else 0
    return {
        "total_questions": total,
        "correct": correct,
        "accuracy": overall_accuracy,
        "skills": skills,
    }

