from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..models import Question, QuestionValidationIssue
from ..extensions import db
from .difficulty_service import difficulty_prompt_block
from .skill_taxonomy import _SKILL_LOOKUP


Issue = Dict[str, Any]


def validate_question(question: Question) -> Tuple[bool, List[Issue]]:
    issues: List[Issue] = []

    def add(code: str, message: str, severity: str = "error"):
        issues.append({"code": code, "message": message, "severity": severity})

    # Required fields
    if not question.section:
        add("missing_section", "Section is required")
    if not question.stem_text or not str(question.stem_text).strip():
        add("missing_stem", "Stem text is required")

    # Skill tags
    tags = question.skill_tags or []
    if not isinstance(tags, list):
        add("bad_skill_tags", "skill_tags must be a list")
    else:
        valid_tags = [tag for tag in tags if tag in _SKILL_LOOKUP]
        if not valid_tags:
            add("missing_skill_tag", "At least one valid skill tag is required")
        if len(tags) > 2:
            add("too_many_skill_tags", "Use at most two skill tags", severity="warning")

    qtype = (getattr(question, "question_type", None) or "choice").lower()
    choices = question.choices or {}
    if qtype == "choice":
        if not isinstance(choices, dict) or len(choices) < 4:
            add("choice_count", "Choice questions must have at least 4 options")
        correct = question.correct_answer or {}
        correct_val = correct.get("value") if isinstance(correct, dict) else None
        if not correct_val:
            add("missing_correct", "Correct answer is required for choice")
        elif correct_val not in choices:
            add("correct_not_in_choices", "Correct answer must be one of the choices")
    elif qtype == "fill":
        correct = question.correct_answer or {}
        correct_val = correct.get("value") if isinstance(correct, dict) else None
        schema = question.answer_schema or {}
        acceptable = schema.get("acceptable") if isinstance(schema, dict) else None
        if not correct_val and not acceptable:
            add("missing_fill_answer", "Fill question needs a correct value or acceptable list")
        if isinstance(acceptable, list):
            # SAT grid-in length hint: 5 chars max, decimal counts, leading minus ignored
            for ans in acceptable:
                s = str(ans).strip()
                if not s:
                    add("empty_acceptable", "Empty acceptable answer", severity="warning")
                    continue
                length = len(s.lstrip("-"))
                if length > 5:
                    add("acceptable_length", f"Acceptable answer '{s}' exceeds 5 characters", severity="warning")
    else:
        add("bad_type", f"Unknown question_type: {qtype}")

    if question.difficulty_level is not None:
        try:
            lvl = int(question.difficulty_level)
            if lvl < 1 or lvl > 5:
                add("bad_difficulty", "difficulty_level must be 1-5")
        except Exception:
            add("bad_difficulty", "difficulty_level must be integer 1-5")

    return (len([i for i in issues if i["severity"] == "error"]) == 0), issues


def record_issues(question: Question, issues: List[Issue]) -> None:
    if not issues:
        return
    source_id = getattr(question, "source_id", None)
    for issue in issues:
        db.session.add(
            QuestionValidationIssue(
                question_id=question.id,
                source_id=source_id,
                issue_code=issue.get("code", "unknown"),
                message=issue.get("message", ""),
                severity=issue.get("severity", "error"),
            )
        )
    db.session.commit()


