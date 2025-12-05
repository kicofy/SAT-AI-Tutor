"""Learning session service functions."""

from __future__ import annotations

from datetime import datetime, timezone
from time import sleep
from typing import List, Optional

from sqlalchemy.exc import OperationalError
from flask import url_for
from sqlalchemy.orm.attributes import flag_modified

from ..extensions import db
from ..models import Question, StudySession, UserQuestionLog
from . import adaptive_engine, spaced_repetition, analytics_service


def select_questions(
    user_id: int,
    num_questions: int,
    section: str | None = None,
    focus_skill: str | None = None,
) -> List[Question]:
    last_summary = get_last_session_summary(user_id)
    questions = adaptive_engine.select_next_questions(
        user_id=user_id,
        num_questions=num_questions,
        section=section,
        focus_skill=focus_skill,
        last_summary=last_summary,
    )
    if questions:
        return questions
    query = Question.query
    if section:
        query = query.filter_by(section=section)
    if focus_skill:
        fallback = query.order_by(db.func.random()).all()
        prioritized = [q for q in fallback if focus_skill in (q.skill_tags or [])]
        prioritized.extend([q for q in fallback if focus_skill not in (q.skill_tags or [])])
        return prioritized[:num_questions]
    return query.order_by(db.func.random()).limit(num_questions).all()


def create_session(
    user_id: int,
    questions: List[Question],
    *,
    plan_block_id: str | None = None,
) -> StudySession:
    serialized = [_serialize_question(q) for q in questions]
    session = StudySession(
        user_id=user_id,
        questions_assigned=serialized,
        questions_done=[],
        plan_block_id=plan_block_id,
    )
    db.session.add(session)
    _commit_with_retry()
    return session


def log_answer(session: StudySession, question: Question, payload: dict, user_id: int) -> UserQuestionLog:
    is_correct = payload["user_answer"] == question.correct_answer
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
    return session


def abort_session(session: StudySession) -> StudySession:
    session.ended_at = datetime.now(timezone.utc)
    _commit_with_retry()
    if session.plan_block_id:
        from . import learning_plan_service

        learning_plan_service.handle_session_abort(session)
    return session


def get_active_session(user_id: int) -> Optional[StudySession]:
    return (
        StudySession.query.filter_by(user_id=user_id, ended_at=None)
        .order_by(StudySession.started_at.desc())
        .first()
    )


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
        "choices": question.choices,
        "skill_tags": question.skill_tags or [],
    }
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
    if figure_query is not None and payload["has_figure"]:
        try:
            figure_list = figure_query.all()
        except Exception:  # pragma: no cover - defensive fallback
            figure_list = []
        for figure in figure_list:
            if not getattr(figure, "image_path", None):
                continue
            figures.append(
                {
                    "id": figure.id,
                    "description": figure.description,
                    "bbox": figure.bbox,
                    "url": url_for(
                        "learning_bp.get_question_figure_image",
                        figure_id=figure.id,
                        _external=False,
                    ),
                }
            )
    if figures:
        payload["figures"] = figures
    return payload


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
        updated = serialized_map.get(question_id)
        if updated:
            if entry.get("unavailable_reason"):
                mutated = True
                updated = dict(updated)
                updated.pop("unavailable_reason", None)
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
    for entry in progress_list:
        if entry.get("question_id") == question.id:
            entry.update(
                {
                    "log_id": log.id,
                    "answered_at": log.answered_at.isoformat(),
                    "is_correct": log.is_correct,
                    "user_answer": log.user_answer,
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

