# Step 06 – Student Practice Sessions (Baseline)

## Goal
Enable students to request practice sessions, receive question sets, submit answers, and log performance data, matching `项目计划` sections 6.2 and 7.1 (session endpoints).

## Dependencies
- Step 05 (question bank CRUD)

## Detailed Tasks
1. Create learning models in `sat_app/models/learning.py`:
   - `StudySession` (user_id, start/end timestamps, questions_assigned JSON, questions_done JSON, summary).
   - `UserQuestionLog` (user_id, question_id, is_correct, user_answer, time_spent_sec, answered_at, viewed_explanation).
2. Implement schemas for session creation and answer submission (`sat_app/schemas/answer_schema.py`).
3. Build `sat_app/services/session_service.py` with functions to:
   - Select questions (simple random or stratified by section as interim logic).
   - Create session records and track state.
   - Persist logs when answers arrive.
4. Extend `sat_app/blueprints/learning_bp.py` with endpoints:
   - `POST /api/learning/session/start` → generates session, returns ordered questions.
   - `POST /api/learning/session/answer` → accepts `question_id`, `user_answer`, `time_spent`, returns correctness and optionally explanation placeholder ID.
   - `POST /api/learning/session/end` (optional) to finalize stats.
5. Integrate JWT user identity; ensure students can only access their own sessions.
6. Compute correctness locally (compare submitted choice to `Question.correct_answer`).
7. Emit events or logs for analytics (to be consumed in Step 10).
8. Add tests covering session lifecycle, logging, and invalid question IDs.
9. Update API docs with example request/response payloads.

## Deliverables
- Learning models and associated migrations.
- Session service and endpoints delivering baseline practice functionality.
- Tests validating answer recording and authorization.

## Verification
- Student user can hit `/api/learning/session/start` and receive N questions.
- Subsequent `answer` calls persist logs visible in the database.
- `pytest sat_app/tests/test_learning_sessions.py` passes.

## Notes
- Question selection can remain simple for now; Step 08 will replace it with the adaptive engine.

