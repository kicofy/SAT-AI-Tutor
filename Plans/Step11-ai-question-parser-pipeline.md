# Step 11 – AI Question Parser Pipeline

## Goal
Automate question ingestion from PDF/Word uploads using the AI parsing pipeline described in `项目计划` section 5.2, integrating with existing admin workflows.

## Dependencies
- Step 05 (manual question CRUD) for baseline storage

## Detailed Tasks
1. Implement `sat_app/utils/file_parser.py` to extract question-oriented blocks from uploads:
   - Text-first assets (PDF/Word) → use `pdfplumber`, `python-docx`, or `unstructured` to pull stems, choices, and surrounding passages; normalize whitespace and preserve numbering.
   - Image/scanned pages → capture the binary payload plus any quick OCR text (for ids/page references) so the downstream model can receive both text and image URIs/base64.
   - Emit a normalized structure `{type: "text" | "image", content, images, metadata}` for every block.
2. Create `sat_app/services/ai_question_parser.py` with `parse_raw_question_block(block)` that:
   - Builds prompts targeting the existing `Question` schema (stem_text, choices, correct_answer, difficulty_level, skill_tags, passage, explanation, metadata).
   - If `block.type === "image"`, use the GPT 通用多模态模型（例如 GPT‑4.1/4o）并传入图片 URL/base64；否则走文本模型。所有模型调用通过 `ai_client`.
   - Validate the returned JSON via Pydantic/Marshmallow; capture the model’s inferred image description inside `metadata` to aid human reviewers.
3. Introduce optional tagging helpers (`skill` inference, difficulty sanity checks) built atop同一 LLM，实现题目规范化逻辑的集中管理。
4. Add asynchronous processing via `sat_app/tasks/question_tasks.py` (Celery/RQ) so large uploads do not block requests; include status tracking in the database.
5. Extend `admin_bp` endpoints:
   - `POST /api/admin/questions/upload` (accepts file, stores raw blobs, triggers parser task).
   - `POST /api/admin/questions/parse` (manual trigger with raw text blocks).
   - `GET /api/admin/questions/imports` to monitor job status, errors, and parsed counts.
6. Ensure parsed questions can be reviewed/edited before publishing (e.g., store drafts flagged as `is_verified=False`).
7. Write tests mocking the AI parser to cover parsing success, validation failures, and admin review flow.
8. Update documentation outlining file format expectations, processing latency, and fallback to manual entry if parsing fails.
9. Capture detailed logging/telemetry for prompt/response pairs (scrub sensitive data) to assist debugging.

## Deliverables
- File parsing utility, AI parser service, and background task.
- Admin APIs for uploading, parsing, and reviewing AI-generated questions.
- Tests validating validation logic and user permissions.

## Verification
- Uploading a sample document results in parsed questions stored in draft state.
- Admins can edit/approve drafts and promote them to active questions.
- Parser gracefully reports errors for malformed blocks without crashing the job.

## Notes
- Keep prompts/versioning configurable so you can iterate on parsing quality without code changes; consider storing the prompt template alongside parsed questions for traceability.

