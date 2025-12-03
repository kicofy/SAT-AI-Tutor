"""Heuristic SAT score predictor based on mastery."""

from __future__ import annotations

from statistics import mean

from ..models import SkillMastery


def _score_from_mastery(mastery_value: float) -> int:
    mastery_value = max(0.0, min(1.0, mastery_value))
    return int(200 + mastery_value * 600)


def _filter_mastery(masteries, section: str):
    section = section.lower()
    filtered = [
        record.mastery_score
        for record in masteries
        if section in (record.skill_tag or "").lower()
    ]
    return filtered


def estimate_scores(user_id: int) -> dict:
    masteries = SkillMastery.query.filter_by(user_id=user_id).all()
    if not masteries:
        return {"rw": 400, "math": 400}

    rw_masteries = _filter_mastery(masteries, "rw")
    math_masteries = _filter_mastery(masteries, "math")

    fallback = [record.mastery_score for record in masteries]
    rw_avg = mean(rw_masteries) if rw_masteries else mean(fallback)
    math_avg = mean(math_masteries) if math_masteries else mean(fallback)

    return {"rw": _score_from_mastery(rw_avg), "math": _score_from_mastery(math_avg)}

