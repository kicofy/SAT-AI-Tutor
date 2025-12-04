# Step 07 – AI Explainer Integration

## Goal
Connect learning flows to the AI explainer service so students receive detailed bilingual explanations aligned with the JSON protocol in `项目计划` section 5.3.

## Dependencies
- Step 06 (session/answer endpoints)

## Detailed Tasks
1. Implement `sat_app/services/ai_client.py` encapsulating LLM access (API key, model name from config, retry/backoff, logging).
2. Create `sat_app/services/ai_explainer.py` with `explain_question(question, user_answer, user_language, depth)` that:
   - Builds prompts based on stored question data.
   - Calls `ai_client.chat`.
   - Validates the JSON structure (protocol_version, explanation_blocks with `text_en`/`text_zh`, related_parts).
3. Define schemas or Pydantic models for the explainer response to enforce structure and catch malformed output.
4. Add `sat_app/blueprints/ai_bp.py` endpoints:
   - `POST /api/ai/explain` for standalone use.
   - Internal helper invoked by `learning_bp` after answer submission (can return explanation inline or store an ID referencing cached output).
5. Decide on caching strategy (e.g., store explanation JSON in `UserQuestionLog.summary` or a dedicated `Explanation` table) to avoid repeated LLM calls for the same question/user combo.
6. Extend answer submission response to include `answer_correct`, `explanation` (or `explanation_id`) and fallback messaging if AI call fails.
7. Add settings to disable LLM usage in dev/test, using stubbed responses for predictable tests.
8. Write integration tests mocking the AI client to ensure prompts and outputs behave correctly.
9. Update documentation for AI dependencies (environment variables, rate limits, error handling expectations).

## Deliverables
- Production-ready AI client abstraction.
- Explainer service adhering to the JSON protocol.
- Learning and AI endpoints wired together with graceful degradation on failures.

## Verification
- Manual call to `/api/ai/explain` returns well-formed JSON with bilingual text fields.
- Practice session answer responses include explanation data.
- Tests pass with mocked AI client; real API key works in staging.

## Notes
- Keep prompts/configuration centralized so future services (diagnostic, parser) can reuse the same client.

