# Step 08 – Adaptive Engine and Mastery Tracking

## Goal
Replace random question selection with the adaptive engine outlined in `项目计划` section 6.2, leveraging mastery scores and spaced repetition to optimize practice.

## Dependencies
- Step 07 (AI explanation integrated into answer flow)

## Detailed Tasks
1. Extend `sat_app/models/learning.py` with:
   - `SkillMastery` (user_id, skill_tag, mastery_score, last_practiced_at, success_streak).
   - Optional `ReviewSchedule` or reuse existing fields to flag due questions.
2. Implement `sat_app/services/adaptive_engine.py` containing:
   - `load_user_mastery(user_id)` and `update_mastery_from_log(log_entry)`.
   - Priority calculation (`correct_gap`, `recency_factor`) to rank skills.
   - Question selection functions (`select_next_questions(user_id, n_questions)`).
3. Add spaced repetition helper in `sat_app/services/spaced_repetition.py` to determine which missed questions require review (Leitner-style or custom logic).
4. Update `session_service` to call the adaptive engine when generating sessions, blending new questions with review items (per plan’s “merge and shuffle” guidance).
5. Create background jobs or synchronous routines to update mastery after each answer (success streaks, decay).
6. Provide admin controls or debug endpoints to inspect a user’s mastery vector (useful during testing).
7. Add migrations for new tables/columns and data backfill scripts if needed.
8. Expand tests:
   - Engine returns prioritized skills based on synthetic mastery data.
   - Review questions are inserted when due.
   - Mastery scores adjust correctly after correct/incorrect answers.
9. Document the adaptive logic (formulas, thresholds) for stakeholders and future tuning.

## Deliverables
- Adaptive engine service powering session generation.
- Mastery data persisted per user and kept in sync with logs.
- Tests demonstrating deterministic behavior around priority calculations.

## Verification
- Starting a session for a user with known weak skills yields appropriately targeted questions.
- Repeatedly answering a skill correctly increases mastery and eventually deprioritizes it.
- Review queue surfaces previously missed questions according to spacing rules.

## Notes
- Keep tuning parameters configurable (thresholds, weighting) via settings or database to support experimentation without code changes.

