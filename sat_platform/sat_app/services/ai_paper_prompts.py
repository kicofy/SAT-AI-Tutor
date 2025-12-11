from __future__ import annotations

import random
from textwrap import dedent
from typing import Dict, List


SAT_RW_GUARDRAILS = dedent(
    """
    ABSOLUTE DIGITAL SAT READING & WRITING GUARDRAILS
    • One short passage per question, matching official Digital SAT design (many short texts, single question each).
    • Use the length hint supplied in the prompt (default 90–130 words; grammar/editing excerpts 35–70 words spread across 2–3 sentences). Never exceed 8 sentences.
    • Default to a single paragraph. Only split into two short paragraphs when explicitly comparing viewpoints or when a brief italicized intro sentence is required to set context.
    • Maintain official content domains (Information & Ideas, Craft & Structure, Expression of Ideas, Standard English Conventions).
    • Tone: exam-neutral, concise, grounded in evidence; no slang, melodrama, or creative-writing flourishes.
    • Question stem ≤ 35 words, starting with SAT-style phrasing (“Which choice…”, “Based on the passage…”, etc.).
    • Exactly four answer choices (A–D). Every distractor mirrors a realistic misread (scope shift, attitude error, detail distortion, faulty logic, or grammar slip).
    • If data support is required, reference it in prose or flag `has_figure=true` for a later diagram; no inline tables.
    • Evidence-based or line-reference questions must cite the precise sentence/line supporting the correct answer.
    """
).strip()

SAT_MATH_GUARDRAILS = dedent(
    """
    ABSOLUTE DIGITAL SAT MATH GUARDRAILS
    • Module timing ≈ 1.6 minutes/question. Keep setups ≤4 sentences with clearly defined variables.
    • Cover official domains: Algebra, Advanced Math, Problem-Solving & Data Analysis, Geometry & Trigonometry.
    • Numbers must be realistic and calculator-friendly; avoid ugly radicals or extreme fractions unless essential.
    • Default to four-option MC (A–D); dedicate ~25% of items to student-produced response (numeric answer only) when specified.
    • Require reasoning, not plug-and-chug guessing. Show relationships, proportional thinking, or algebraic manipulation.
    • Figures (if any) must be reproducible from text: specify coordinates, labels, units, and notable points/segments.
    • Stay within Digital SAT scope—no calculus, matrices, proofs, or multi-page derivations.
    """
).strip()

DIGITAL_SAT_BLUEPRINT = dedent(
    """
    ✅ Digital SAT structure (mirrors College Board specs)
    ─────────────────────────────────────────────────────────────
    Reading & Writing: 2 adaptive modules · 32 min each · 54 questions total
    Math:                2 adaptive modules · 35 min each · 44 questions total

    We still target 27+27 RW and 22+22 Math items so each module can include operational + pretest-style coverage.

    Reading & Writing module expectations:
    • Domain distribution per 27-item module (adjust by ±1 as needed):
      - Information & Ideas (central ideas, command of evidence, inference): 7–8 items
      - Craft & Structure (words in context, text structure/purpose, cross-text): 6–7 items
      - Expression of Ideas (transitions, rhetorical synthesis, text organization): 6–7 items
      - Standard English Conventions (grammar, usage, punctuation): 6–7 items
    • Module 1 difficulty skew: easy–medium mix. Module 2: medium–hard with subtler traps.

    Math module expectations:
    • Domain coverage per 22-item module:
      - Algebra: 6–7 items
      - Advanced Math (nonlinear equations/functions): 6–7 items
      - Problem-Solving & Data Analysis: 4–5 items
      - Geometry & Trigonometry: 4–5 items
    • Allocate ≈25% of math slots to student-produced responses (response_type: "spr"); remainder MCQ.
    • Module 1 phrasing stays direct; Module 2 adds multi-step reasoning or parameter twists.

    Difficulty calibration:
    • Module 1 targets medium difficulty (single inference or algebraic step).
    • Module 2 demands harder reasoning (combined evidence, layered logic, parameter constraints).
    • Every question must match official Digital SAT style: concise passages, evidence-backed claims,
      realistic numbers, exactly one correct answer, and distractors reflecting true misconceptions.
    """
).strip()


RW_TYPE_RULES: Dict[str, Dict[str, str]] = {
    "main_idea": {
        "base": dedent(
            """
            Craft 1–2 paragraphs (130–170 words) with a single cohesive thesis.
            Wrong choices must follow SAT patterns:
            • overly narrow detail
            • scope too broad
            • attitude distortion
            • concept shift
            """
        ).strip(),
        "hard": "Hide the thesis away from the topic sentence, and include a mild tone shift near the end.",
    },
    "detail": {
        "base": dedent(
            """
            Ask for a fact explicitly stated in the passage.
            The correct answer must be a paraphrase or verbatim match.
            Wrong choices should sound almost right but contradict the passage.
            """
        ).strip(),
        "hard": "Scatter the supporting info across two sentences and force a light paraphrase.",
    },
    "inference": {
        "base": dedent(
            """
            Require a conclusion that is “almost explicitly” stated.
            No speculative psychology or biography; inference must stem from textual evidence.
            """
        ).strip(),
        "hard": "Combine two evidence points so that every distractor feels plausible unless both are synthesized.",
    },
    "vocabulary": {
        "base": dedent(
            """
            Pick a multi-meaning word in the passage (e.g., yield, impose, scale).
            Ask for “most nearly means” in context, with four realistic senses.
            """
        ).strip(),
        "hard": "Use an abstract or academic sense (economic, biological, metaphorical).",
    },
    "evidence_pair": {
        "base": dedent(
            """
            Build a two-question pair:
            • Q1 asks for the best-supported claim.
            • Q2 provides four line references; only one directly supports the correct Q1 choice.
            """
        ).strip(),
        "hard": "Make the support subtle (e.g., clause-level implication, not explicit restatement).",
    },
    "logic": {
        "base": dedent(
            """
            Test transitions / sentence function (However, Therefore, Moreover, For example, etc.).
            Provide four discourse markers; only one preserves coherence.
            """
        ).strip(),
        "hard": "Force students to weigh nuanced rhetorical roles (contrast vs. concession vs. elaboration).",
    },
    "purpose": {
        "base": "Ask why a given sentence or clause exists (illustrate, rebut, support, bridge).",
        "hard": "Blend two intents (e.g., both transitions and contrast) so only the precise label fits.",
    },
    "grammar": {
        "base": dedent(
            """
            Target official SAT grammar domains: verb tense/aspect, subject-verb agreement,
            pronoun clarity, parallelism, fragments/run-ons, punctuation (comma/semicolon/colon),
            concision, sentence order.
            Provide a short passage (2–3 sentences) with one error; choices should repair or break it.
            """
        ).strip(),
        "hard": "Layer two interacting issues (e.g., modifier + punctuation) while keeping only one fully correct option.",
    },
    "grammar_complex": {
        "base": "Same as grammar, but expect multi-rule editing and advanced rhetorical alignment.",
        "hard": "Ensure distractors appear grammatically sound yet subtly violate logic or emphasis.",
    },
}

RW_DOMAIN_SKILL: Dict[str, Dict[str, str]] = {
    "main_idea": {"domain": "Information & Ideas", "skill": "Central Ideas and Details"},
    "detail": {"domain": "Information & Ideas", "skill": "Command of Evidence – Textual"},
    "inference": {"domain": "Information & Ideas", "skill": "Inferences"},
    "vocabulary": {"domain": "Craft & Structure", "skill": "Words in Context"},
    "logic": {"domain": "Expression of Ideas", "skill": "Transitions / Rhetorical flow"},
    "purpose": {"domain": "Craft & Structure", "skill": "Text Structure and Purpose"},
    "evidence_pair": {"domain": "Information & Ideas", "skill": "Command of Evidence – Textual"},
    "grammar": {"domain": "Standard English Conventions", "skill": "Usage & Mechanics"},
    "grammar_complex": {"domain": "Standard English Conventions", "skill": "Advanced multi-rule editing"},
}
DEFAULT_RW_DOMAIN = {"domain": "Information & Ideas", "skill": "Evidence-based reasoning"}
RW_SKILL_TAGS: Dict[str, List[str]] = {
    "main_idea": ["RW_MainIdeasEvidence"],
    "detail": ["RW_MainIdeasEvidence"],
    "inference": ["RW_MainIdeasEvidence"],
    "evidence_pair": ["RW_MainIdeasEvidence"],
    "vocabulary": ["RW_WordsInContext"],
    "logic": ["RW_ExpressionOfIdeas"],
    "purpose": ["RW_CraftStructure"],
    "grammar": ["RW_StandardEnglish"],
    "grammar_complex": ["RW_StandardEnglish"],
}
DEFAULT_RW_SKILL_TAGS = ["RW_MainIdeasEvidence"]

RW_LENGTH_HINTS: Dict[str, str] = {
    "main_idea": "90–120 words (single paragraph, clear thesis)",
    "detail": "85–115 words (single paragraph)",
    "inference": "90–120 words (single paragraph)",
    "vocabulary": "65–95 words with the target word in context",
    "logic": "55–80 words highlighting the transition sentence",
    "purpose": "80–110 words with a pivotal sentence labeled",
    "evidence_pair": "120–160 words split into two short paragraphs to allow two evidence lines",
    "grammar": "35–50 words across 2 sentences with one underlined portion",
    "grammar_complex": "45–70 words across 3 sentences",
}
DEFAULT_RW_LENGTH = "85–125 words (single focused paragraph)"

RW_STEM_PATTERNS: Dict[str, List[str]] = {
    "main_idea": [
        "Which choice best states the main idea of the passage?",
        "Which choice best summarizes the passage?",
    ],
    "detail": [
        "According to the passage, which choice best describes {detail_target}?",
        "Which choice accurately describes {detail_target} as presented in the passage?",
    ],
    "inference": [
        "Which choice can be reasonably inferred from the passage?",
        "Which choice best supports the inference that {inference_target}?",
    ],
    "vocabulary": [
        "As used in the passage, the word \"{target_word}\" most nearly means which choice?",
        "In the passage, the word \"{target_word}\" is closest in meaning to which choice?",
    ],
    "logic": [
        "Which choice best introduces the sentence that follows?",
        "Which choice best maintains the logical progression of the paragraph?",
    ],
    "purpose": [
        "Which choice best describes the function of sentence {line_ref} in the passage?",
        "The author includes {detail_target} primarily to accomplish which goal?",
    ],
    "evidence_pair": [
        "Which choice best supports the answer to the previous question?",
    ],
    "grammar": [
        "Which choice completes the text most effectively?",
        "Which choice corrects the underlined portion?",
    ],
    "grammar_complex": [
        "Which choice best combines the sentences to improve the cohesion of the passage?",
        "Which choice maintains the tone and is free of errors?",
    ],
}
DEFAULT_RW_STEM_PATTERNS = ["Which choice best fits the passage?"]

RW_TOPIC_SEEDS: Dict[str, List[Dict[str, str]]] = {
    "main_idea": [
        {
            "id": "rw_main_civic_lab",
            "scenario": "community technologists running a data lab on coastal erosion mitigation projects",
            "voice": "third-person magazine report",
            "detail": "Reference a statistic gathered by the lab and a policymaker's reaction.",
        },
        {
            "id": "rw_main_rural_health",
            "scenario": "a rural nurse reflecting on the first months of telemedicine adoption",
            "voice": "first-person field memoir",
            "detail": "Contrast optimism about new tools with anxiety about unreliable connectivity.",
        },
        {
            "id": "rw_main_art_conservation",
            "scenario": "museum conservators debating restoration versus preservation for weathered murals",
            "voice": "formal panel recap",
            "detail": "Summarize at least two positions with distinct rationales.",
        },
    ],
    "inference": [
        {
            "id": "rw_inf_ocean_farm",
            "scenario": "scientists piloting offshore seaweed farms for carbon capture",
            "voice": "science news brief",
            "detail": "Mention logistical setbacks and funding uncertainty without explicitly stating conclusions.",
        },
        {
            "id": "rw_inf_archival_letters",
            "scenario": "archivists uncovering letters describing early aviation experiments",
            "voice": "curator discovery log",
            "detail": "Hint at motives and relationships indirectly through the letters.",
        },
    ],
    "vocabulary": [
        {
            "id": "rw_vocab_textile_coop",
            "scenario": "a cooperative of textile artisans debating sustainable dyes",
            "voice": "business profile",
            "detail": "Use a polysemous verb/adjective tied to materials or finance.",
        },
        {
            "id": "rw_vocab_research_diver",
            "scenario": "field notes from a marine ecologist diving beneath thinning ice shelves",
            "voice": "annotated journal",
            "detail": "Highlight a sensory description whose meaning depends on context.",
        },
    ],
    "logic": [
        {
            "id": "rw_logic_student_network",
            "scenario": "student organizers coordinating a multi-city debate tour",
            "voice": "email thread excerpt",
            "detail": "Include conflicting goals that require precise transitions.",
        },
        {
            "id": "rw_logic_orchestra",
            "scenario": "a conductor outlining rehearsal adjustments for a touring orchestra",
            "voice": "memo format",
            "detail": "Present successive instructions that need accurate discourse markers.",
        },
    ],
    "evidence_pair": [
        {
            "id": "rw_ev_climate_archive",
            "scenario": "a historian compiling accounts of a centuries-old drought",
            "voice": "archival digest",
            "detail": "Provide two paragraphs referencing different sources so evidence lines exist.",
        },
        {
            "id": "rw_ev_microgrids",
            "scenario": "engineers evaluating microgrid pilots on remote islands",
            "voice": "technical briefing",
            "detail": "Contrast metrics such as uptime versus cost for evidence citation.",
        },
    ],
    "grammar": [
        {
            "id": "rw_gram_volunteer_flyer",
            "scenario": "a nonprofit drafting a volunteer recruitment flyer",
            "voice": "second-person persuasive",
            "detail": "Include underlined segments with verb agreement or modifier errors.",
        },
        {
            "id": "rw_gram_maker_fair",
            "scenario": "organizers preparing a makers' fair announcement",
            "voice": "friendly newsletter",
            "detail": "Create opportunities for concision and punctuation corrections.",
        },
    ],
    "grammar_complex": [
        {
            "id": "rw_gramc_spacecoop",
            "scenario": "international partners negotiating a shared space observatory budget",
            "voice": "diplomatic memo",
            "detail": "Embed clauses that require parallelism and logical ordering fixes.",
        }
    ],
    "default": [
        {
            "id": "rw_default_green_corridor",
            "scenario": "urban designers proposing pollinator corridors alongside commuter rail lines",
            "voice": "proposal summary",
            "detail": "Refer to one metric and one stakeholder quote.",
        },
        {
            "id": "rw_default_food_lab",
            "scenario": "chefs collaborating with food scientists on climate-resilient crops",
            "voice": "feature article",
            "detail": "Compare lab-tested varieties with heirloom crops.",
        },
    ],
}


MATH_TYPE_RULES: Dict[str, Dict[str, str]] = {
    "algebra": {
        "base": "Linear equations, systems, or expressions that require symbolic manipulation. Avoid trivial arithmetic.",
        "hard": "Use parameters or require reasoning about the structure before solving.",
    },
    "quadratic": {
        "base": "Quadratic equations/functions (roots, factoring, vertex form).",
        "hard": "Include discriminant logic, parameter constraints, or transformations.",
    },
    "ratio_statistics": {
        "base": "Percent, proportional relationships, or descriptive statistics (mean/median).",
        "hard": "Combine multiple ratios or analyze how statistics shift after an adjustment.",
    },
    "geometry": {
        "base": "Triangles, circles, area/volume, coordinate geometry.",
        "hard": "Blend coordinate + Euclidean reasoning or include loci/constraint arguments.",
    },
    "mixed_model": {
        "base": "Word problems requiring translation to equations or multi-step modeling.",
        "hard": "Use layered context (rates + constraints + optimization).",
    },
    "parameter_quadratic": {
        "base": "Quadratics with parameters (k, a, b). Ask about solution conditions.",
        "hard": "Force reasoning about discriminant equality, vertex alignment, or system intersections.",
    },
    "statistics": {
        "base": "Standard deviation, data shifts, probability.",
        "hard": "Introduce conditional probability or compare two distributions analytically.",
    },
    "advanced_geometry": {
        "base": "Coordinate-circle hybrids, transformations, or composite figures.",
        "hard": "Require algebraic proofs or multi-step derivations of geometric constraints.",
    },
    "modeling": {
        "base": "Real-world scenario requiring equation setup, interpretation, and solution.",
        "hard": "Demand multi-equation modeling with parameter inference or piecewise logic.",
    },
}

MATH_DOMAIN_SKILL: Dict[str, Dict[str, str]] = {
    "algebra": {"domain": "Algebra", "skill": "Linear equations / systems"},
    "quadratic": {"domain": "Advanced Math", "skill": "Quadratic functions & forms"},
    "ratio_statistics": {"domain": "Problem-Solving & Data Analysis", "skill": "Ratios / percentages / descriptive stats"},
    "geometry": {"domain": "Geometry & Trigonometry", "skill": "Euclidean + coordinate geometry"},
    "mixed_model": {"domain": "Problem-Solving & Data Analysis", "skill": "Modeling multi-step scenarios"},
    "parameter_quadratic": {"domain": "Advanced Math", "skill": "Parameterized quadratics / discriminant"},
    "statistics": {"domain": "Problem-Solving & Data Analysis", "skill": "Probability / standard deviation"},
    "advanced_geometry": {"domain": "Geometry & Trigonometry", "skill": "Coordinate & circle constraints"},
    "modeling": {"domain": "Algebra", "skill": "Multi-equation modeling / interpretation"},
}
DEFAULT_MATH_DOMAIN = {"domain": "Algebra", "skill": "General reasoning"}
MATH_SKILL_TAGS: Dict[str, List[str]] = {
    "algebra": ["M_Algebra"],
    "quadratic": ["M_AdvancedMath"],
    "parameter_quadratic": ["M_AdvancedMath"],
    "ratio_statistics": ["M_ProblemSolvingData"],
    "mixed_model": ["M_ProblemSolvingData"],
    "statistics": ["M_ProblemSolvingData"],
    "geometry": ["M_Geometry"],
    "advanced_geometry": ["M_Geometry", "M_Trigonometry"],
    "modeling": ["M_ProblemSolvingData"],
}
DEFAULT_MATH_SKILL_TAGS = ["M_Algebra"]

MATH_TOPIC_SEEDS: Dict[str, List[Dict[str, str]]] = {
    "algebra": [
        {
            "id": "math_alg_solar_install",
            "scenario": "an installer modeling solar panel output versus tilt and shading changes",
            "context": "Translate seasonal sun angles into linear equations or systems.",
        },
        {
            "id": "math_alg_delivery_route",
            "scenario": "a robotics company optimizing timing for delivery drones on a fixed loop",
            "context": "Relate speed, distance, and loading delays using equations and inequalities.",
        },
    ],
    "quadratic": [
        {
            "id": "math_quad_water_jet",
            "scenario": "engineers tuning the arc of a programmable water fountain installation",
            "context": "Model projectile motion with vertex interpretations or root conditions.",
        }
    ],
    "ratio_statistics": [
        {
            "id": "math_stats_bee_colony",
            "scenario": "biologists comparing bee colony survival across three habitats",
            "context": "Use tables with multi-step ratio reasoning and percent change.",
        }
    ],
    "geometry": [
        {
            "id": "math_geo_stage_design",
            "scenario": "stage designers planning modular seating shapes for a traveling show",
            "context": "Invoke area/perimeter or coordinate geometry with actual measurements.",
        }
    ],
    "mixed_model": [
        {
            "id": "math_mix_smart_farm",
            "scenario": "agritech analysts combining linear growth and exponential nutrient decay in a greenhouse",
            "context": "Describe variables tied to sensor readings and predictions.",
        }
    ],
    "parameter_quadratic": [
        {
            "id": "math_paramwind",
            "scenario": "aerospace engineers tuning parameters in a lift equation to avoid stall conditions",
            "context": "Require solving for a parameter that enforces a single intersection or root.",
        }
    ],
    "statistics": [
        {
            "id": "math_stats_transit",
            "scenario": "public transit planners evaluating ridership variance before and after adding express routes",
            "context": "Contrast mean vs. standard deviation shifts.",
        }
    ],
    "advanced_geometry": [
        {
            "id": "math_adv_geom_sensor",
            "scenario": "designing a triangular sensor array that must cover a conservation zone",
            "context": "Use coordinate geometry or circle theorems tied to coverage requirements.",
        }
    ],
    "modeling": [
        {
            "id": "math_model_stream_restoration",
            "scenario": "hydrologists modeling sediment flow with piecewise functions during restoration",
            "context": "Mix algebraic expressions with constraints pulled from data.",
        }
    ],
    "default": [
        {
            "id": "math_default_energy_audit",
            "scenario": "energy auditors balancing consumption across lab equipment",
            "context": "Allow any function type but keep units realistic.",
        },
        {
            "id": "math_default_satellite",
            "scenario": "satellite teams budgeting bandwidth for multiple experiments",
            "context": "Encourage systems of equations or inequalities.",
        },
    ],
}

MATH_STEM_PATTERNS: Dict[str, List[str]] = {
    "algebra": [
        "What is the value of {variable}?",
        "Which equation represents the situation described?",
        "Which expression is equivalent to {expression}?",
    ],
    "quadratic": [
        "What is one possible value of {variable}?",
        "Which of the following is equivalent to the quadratic shown?",
    ],
    "parameter_quadratic": [
        "For what value of {parameter} does the equation have exactly one solution?",
    ],
    "ratio_statistics": [
        "Which of the following best represents the described ratio?",
        "What is the percent change in {quantity}?",
    ],
    "mixed_model": [
        "Which equation best models the relationship between {quantity1} and {quantity2}?",
    ],
    "statistics": [
        "What is the probability that {event}?",
        "Which statement must be true about the standard deviation / mean after the change?",
    ],
    "geometry": [
        "What is the area / circumference / length of {figure}?",
        "Which equation represents the circle / line described?",
    ],
    "advanced_geometry": [
        "What is the measure of {angle/arc}?",
        "Which of the following equations represents the described transformation?",
    ],
    "modeling": [
        "If {scenario}, what is the value of {unknown}?",
    ],
}
DEFAULT_MATH_STEM_PATTERNS = ["What is the value of {variable}?"]


def build_outline_prompt(paper_name: str) -> str:
    return dedent(
        f"""
        You are the chief test designer for the Digital SAT. Draft an outline for a brand-new mock paper titled "{paper_name}".
        Use only the official blueprint below and DO NOT invent new structures.

        {DIGITAL_SAT_BLUEPRINT}

        Requirements:
        1. Follow the module/topic/quantity ranges exactly.
        2. For every module, enumerate each question slot with:
           - `question_number`
           - `question_type` (use snake_case identifiers from the blueprint, e.g., main_idea, evidence_pair, algebra, parameter_quadratic)
           - `difficulty` ("medium" or "hard" exactly as the module demands)
           - `requires_passage` (true if prose passage is needed)
           - `requires_figure` (true if the blueprint mandates a chart/table/graph)
           - `skill_focus` (short note such as "Urban planning main idea" or "Quadratic discriminant condition").
        3. Respond with STRICT JSON: {{"modules":[{{"code":"ENG_M1","label":"...","questions":[...]}}]}}

        Keep descriptions concise yet descriptive enough for downstream generation.
        """
    ).strip()


def _rw_type_guidance(question_type: str, difficulty: str) -> str:
    spec = RW_TYPE_RULES.get(question_type, {"base": "Follow SAT reading/writing conventions."})
    text = spec["base"]
    if difficulty == "hard" and spec.get("hard"):
        text += "\nHard-mode adjustments: " + spec["hard"]
    return text


def _rw_length_hint(question_type: str) -> str:
    return RW_LENGTH_HINTS.get(question_type, DEFAULT_RW_LENGTH)


def _format_seed_context(seed: dict | None) -> str:
    if not seed:
        return ""
    lines = ["Context diversity requirements:"]
    if seed.get("scenario"):
        lines.append(f"• Scenario focus: {seed['scenario']}")
    if seed.get("voice"):
        lines.append(f"• Narrative voice or perspective: {seed['voice']}")
    if seed.get("context"):
        lines.append(f"• Modeling focus: {seed['context']}")
    if seed.get("detail"):
        lines.append(f"• Required detail: {seed['detail']}")
    lines.append("• Invent new names, data points, and imagery; do not reuse phrasing from earlier questions.")
    return "\n".join(lines)


def build_rw_question_prompt(
    module_label: str,
    difficulty: str,
    question_type: str,
    requires_passage: bool,
    requires_figure: bool,
    *,
    topic_seed: dict | None = None,
) -> str:
    length_hint = _rw_length_hint(question_type)
    passage_req = (
        f"Write a fresh passage first (target length: {length_hint}). Keep 1–2 paragraphs unless told otherwise."
        if requires_passage
        else f"This item embeds its excerpt directly in the stem. Craft a snippet of {length_hint} before presenting the question."
    )
    figure_req = (
        "The scenario must reference a graph/table/figure. Provide a concise textual description that can later be transformed into a visual (e.g., 'line graph comparing rainfall in 4 cities')."
        if requires_figure
        else "No external figure is needed; all info should be textual."
    )
    vocab_target_hint = ""
    if question_type == "vocabulary":
        vocab_target_hint = dedent(
            """
            Vocabulary item requirements:
            • Choose one polysemous target word in the passage and wrap it with <u>...</u> exactly once to mark it for underlining.
            • Do NOT cite line numbers. Stems must follow: “As used in the passage, the word “{target_word}” most nearly means which choice?”
            • Ensure the underlined word’s meaning is resolved by surrounding context; include a nearby clue for disambiguation.
            """
        ).strip()
    guidance = _rw_type_guidance(question_type, difficulty)
    domain_meta = RW_DOMAIN_SKILL.get(question_type, DEFAULT_RW_DOMAIN)
    skill_tags = RW_SKILL_TAGS.get(question_type, DEFAULT_RW_SKILL_TAGS)
    stem_templates = RW_STEM_PATTERNS.get(question_type, DEFAULT_RW_STEM_PATTERNS)
    template_text = "; ".join(stem_templates)
    seed_context = _format_seed_context(topic_seed)
    return dedent(
        f"""
        You are authoring a Digital SAT Reading & Writing question for {module_label}.
        Question type: {question_type.replace("_", " ").title()}
        Difficulty target: {difficulty.title()}
        Content domain: {domain_meta['domain']} · Skill focus: {domain_meta['skill']} (per official Digital SAT taxonomy).

        {passage_req}
        {figure_req}
        {seed_context or ""}
        {vocab_target_hint}

        {SAT_RW_GUARDRAILS}

        Guidance:
        {guidance}

        Output JSON with:
        {{
          "passage": "...",        # omit if not needed
          "stem_text": "...",      # the actual question prompt
          "choices": {{"A":"...", "B":"...", "C":"...", "D":"..."}},
          "correct_answer": {{"value":"A"}},
          "has_figure": {str(requires_figure).lower()},
          "metadata": {{
             "content_domain": "{domain_meta['domain']}",
             "skill_focus": "{domain_meta['skill']}"
          }},
          "skill_tags": {skill_tags},
          "explanation_plan": {{
             "english": "bullet outline for final explanation",
             "chinese": "中文要点大纲"
          }},
          "figure_prompt": "if has_figure, describe desired visual clearly"
        }}

        Rules:
        • One and only one correct answer.
        • Distractors must be pedagogically plausible (reflect common misreads).
        • Tone must feel identical to official Digital SAT content.
        • Use an SAT-style stem opener from this list: {template_text}. Paraphrase minimally so the question sounds like an official item.
        """
    ).strip()


def _math_type_guidance(question_type: str, difficulty: str) -> str:
    spec = MATH_TYPE_RULES.get(question_type, {"base": "Follow SAT Math conventions."})
    text = spec["base"]
    if difficulty == "hard" and spec.get("hard"):
        text += "\nHard-mode adjustments: " + spec["hard"]
    return text


def build_math_question_prompt(
    module_label: str,
    difficulty: str,
    question_type: str,
    requires_figure: bool,
    *,
    topic_seed: dict | None = None,
) -> str:
    figure_req = (
        "Include a description of the diagram (coordinates, labels, numeric relationships) so a separate image model can render it."
        if requires_figure
        else "Do not require an external figure; text and symbols must suffice."
    )
    guidance = _math_type_guidance(question_type, difficulty)
    domain_meta = MATH_DOMAIN_SKILL.get(question_type, DEFAULT_MATH_DOMAIN)
    skill_tags = MATH_SKILL_TAGS.get(question_type, DEFAULT_MATH_SKILL_TAGS)
    stem_templates = MATH_STEM_PATTERNS.get(question_type, DEFAULT_MATH_STEM_PATTERNS)
    stem_template_text = "; ".join(stem_templates)
    seed_context = _format_seed_context(topic_seed)
    return dedent(
        f"""
        You are creating a Digital SAT Math question for {module_label}.
        Question type: {question_type.replace("_", " ").title()}
        Difficulty target: {difficulty.title()}
        Content domain: {domain_meta['domain']} · Skill focus: {domain_meta['skill']} (per official Digital SAT taxonomy).

        {figure_req}
        {seed_context or ""}

        {SAT_MATH_GUARDRAILS}

        Guidance:
        {guidance}

        Output JSON with:
        {{
          "stem_text": "Problem statement with necessary context",
          "choices": {{"A":"...", "B":"...", "C":"...", "D":"..."}},  # omit for SPR and supply numeric answer only
          "correct_answer": {{"value":"C"}},
          "has_figure": {str(requires_figure).lower()},
          "metadata": {{
             "content_domain": "{domain_meta['domain']}",
             "skill_focus": "{domain_meta['skill']}",
             "response_type": "mcq_or_spr"  # set to 'spr' when no choices
          }},
          "skill_tags": {skill_tags},
          "solution_outline": "Step-by-step reasoning in English",
          "figure_prompt": "Detailed description for diagrams (if needed)"
        }}

        Requirements:
        • Use variables, realistic data, and SAT-style phrasing (no calculators beyond four-function assumptions).
        • Ensure the correct answer demands reasoning, not guessable patterns.
        • Distractors should reflect common algebraic or arithmetic missteps.
        • Start the stem with one of these SAT-style prompts: {stem_template_text}. Keep it to ≤3 sentences (≤20 words each).
        """
    ).strip()


def build_explanation_prompt(language: str) -> str:
    return dedent(
        f"""
        You are the AI Strategy Tutor. Produce a {language.upper()} explanation for a Digital SAT question.
        Requirements:
        • Start with the core idea (为什么 + 为什么 in CN / Why in EN).
        • Highlight textual evidence (Reading) or show numeric work (Math).
        • Explicitly mention traps in the incorrect choices.
        • Conclude with a mini strategy takeaway.
        Keep the tone encouraging, professional, and exam-focused.
        """
    ).strip()


def build_figure_prompt_guidance() -> str:
    return dedent(
        """
        For image generation, describe:
        • Chart type (bar, scatter, geometry diagram, etc.)
        • Axes/labels/numeric ranges
        • Any noteworthy datapoints or annotations
        • Desired visual style (clean SAT test prep aesthetic, high contrast, monochrome)
        Avoid colorful or playful styles; keep it exam-ready.
        """
    ).strip()


