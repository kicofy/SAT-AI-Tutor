"""Canonical SAT skill taxonomy helpers and utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence


@dataclass(frozen=True)
class SkillDescriptor:
    tag: str
    label: str
    domain: str
    description: str
    order: int


_SKILL_TAXONOMY: List[SkillDescriptor] = [
    SkillDescriptor(
        tag="RW_MainIdeasEvidence",
        label="Reading & Writing · Main Ideas & Evidence",
        domain="Reading & Writing",
        description="Identify central ideas, thesis statements, and the evidence that supports them.",
        order=10,
    ),
    SkillDescriptor(
        tag="RW_CraftStructure",
        label="Reading & Writing · Craft & Structure",
        domain="Reading & Writing",
        description="Analyze text structure, point of view, and how specific choices shape meaning.",
        order=20,
    ),
    SkillDescriptor(
        tag="RW_WordsInContext",
        label="Reading & Writing · Words in Context",
        domain="Reading & Writing",
        description="Interpret vocabulary, phrases, and figurative language using contextual clues.",
        order=30,
    ),
    SkillDescriptor(
        tag="RW_DataInterpretation",
        label="Reading & Writing · Quantitative Info",
        domain="Reading & Writing",
        description="Read and reason about tables, charts, and science / social science data within passages.",
        order=40,
    ),
    SkillDescriptor(
        tag="RW_ExpressionOfIdeas",
        label="Reading & Writing · Expression of Ideas",
        domain="Reading & Writing",
        description="Revise text for precision, organization, cohesion, and rhetorical effectiveness.",
        order=50,
    ),
    SkillDescriptor(
        tag="RW_StandardEnglish",
        label="Reading & Writing · Standard English",
        domain="Reading & Writing",
        description="Apply grammar, usage, agreement, and punctuation conventions.",
        order=60,
    ),
    SkillDescriptor(
        tag="M_Algebra",
        label="Math · Algebra",
        domain="Math",
        description="Create, interpret, and solve linear expressions and equations.",
        order=110,
    ),
    SkillDescriptor(
        tag="M_AdvancedMath",
        label="Math · Advanced Math",
        domain="Math",
        description="Manipulate nonlinear expressions, functions, and equations.",
        order=120,
    ),
    SkillDescriptor(
        tag="M_ProblemSolvingData",
        label="Math · Problem Solving & Data",
        domain="Math",
        description="Model real-world situations, analyze ratios/proportions, and interpret statistics.",
        order=130,
    ),
    SkillDescriptor(
        tag="M_Geometry",
        label="Math · Geometry & Measurement",
        domain="Math",
        description="Reason about shapes, angles, area/volume, and coordinate geometry.",
        order=140,
    ),
    SkillDescriptor(
        tag="M_Trigonometry",
        label="Math · Trigonometry",
        domain="Math",
        description="Apply trigonometric ratios, the unit circle, and periodic functions.",
        order=150,
    ),
]

SKILL_ORDERED_TAGS: Sequence[str] = tuple(entry.tag for entry in sorted(_SKILL_TAXONOMY, key=lambda entry: entry.order))
_SKILL_LOOKUP: Dict[str, SkillDescriptor] = {entry.tag: entry for entry in _SKILL_TAXONOMY}
_SKILL_LOWER_LOOKUP: Dict[str, str] = {entry.tag.lower(): entry.tag for entry in _SKILL_TAXONOMY}

_SKILL_SYNONYMS: Dict[str, str] = {
    # Legacy canonical tags
    "rw_mainidea": "RW_MainIdeasEvidence",
    "rw_detailevidence": "RW_MainIdeasEvidence",
    "rw_wordsincontext": "RW_WordsInContext",
    "rw_textstructure": "RW_CraftStructure",
    "rw_expressionofideas": "RW_ExpressionOfIdeas",
    "rw_standardenglish": "RW_StandardEnglish",
    "rw_datainterpretation": "RW_DataInterpretation",
    "m_algebra": "M_Algebra",
    "m_advancedmath": "M_AdvancedMath",
    "m_problemsolving": "M_ProblemSolvingData",
    "m_dataanalysis": "M_ProblemSolvingData",
    "m_geometry": "M_Geometry",
    "m_trigonometry": "M_Trigonometry",
    # Free-form tags observed in legacy data
    "main-idea": "RW_MainIdeasEvidence",
    "main idea": "RW_MainIdeasEvidence",
    "reading-comprehension": "RW_MainIdeasEvidence",
    "reading comprehension": "RW_MainIdeasEvidence",
    "detail-evidence": "RW_MainIdeasEvidence",
    "context-clues": "RW_WordsInContext",
    "contextual-vocabulary": "RW_WordsInContext",
    "vocabulary-in-context": "RW_WordsInContext",
    "vocabulary": "RW_WordsInContext",
    "literary-text": "RW_CraftStructure",
    "literary-fiction": "RW_CraftStructure",
    "precision": "RW_ExpressionOfIdeas",
    "rw_grammar": "RW_StandardEnglish",
    "grammar": "RW_StandardEnglish",
    "rw_grammarusage": "RW_StandardEnglish",
    "science": "RW_DataInterpretation",
    "table-reading": "RW_DataInterpretation",
    "data-analysis": "RW_DataInterpretation",
    "vision": "RW_DataInterpretation",
    "rw_data": "RW_DataInterpretation",
    "m_statistics": "M_ProblemSolvingData",
}


def iter_skill_tags() -> Sequence[str]:
    """Return canonical tags in display order."""
    return SKILL_ORDERED_TAGS


def describe_skill(tag: str) -> dict:
    descriptor = _SKILL_LOOKUP.get(tag)
    if descriptor:
        return {
            "tag": descriptor.tag,
            "label": descriptor.label,
            "domain": descriptor.domain,
            "description": descriptor.description,
            "order": descriptor.order,
        }
    return {
        "tag": tag,
        "label": tag,
        "domain": "General",
        "description": "",
        "order": 999,
    }


def canonicalize_tag(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    lowered = normalized.lower()
    if lowered in _SKILL_SYNONYMS:
        return _SKILL_SYNONYMS[lowered]
    return _SKILL_LOWER_LOOKUP.get(lowered)


def canonicalize_tags(values: Iterable[str] | None, *, limit: int | None = 2) -> List[str]:
    normalized: List[str] = []
    if not values:
        return normalized
    for raw in values:
        canonical = canonicalize_tag(raw)
        if canonical and canonical not in normalized:
            normalized.append(canonical)
            if limit is not None and len(normalized) >= limit:
                break
    return normalized


def infer_section_from_tag(tag: str) -> str:
    descriptor = _SKILL_LOOKUP.get(tag)
    if descriptor:
        return "RW" if descriptor.domain == "Reading & Writing" else "Math"
    return "RW" if tag.lower().startswith("rw") else "Math"


