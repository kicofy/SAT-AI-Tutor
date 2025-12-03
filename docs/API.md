# SAT AI Tutor – Backend API Overview

Base URL: `http(s)://<host>:5080`

All JSON payloads use `application/json` unless noted. Endpoints under `/api/*` return RFC 7807–style error objects with `{ "message": "...", ... }`. JWT access tokens are issued by `/api/auth/login` and must be sent via `Authorization: Bearer <token>`.

---

## 1. Authentication (`/api/auth`)

| Method & Path | Auth | Description |
| ------------- | ---- | ----------- |
| `POST /api/auth/register` | ❌ | Register a new student. Body: `{ "email", "password", "username", "profile": { "daily_available_minutes", "language_preference", "exam_date?", "target_score_rw?", "target_score_math?" } }`. Response includes `user` and `access_token`. Role is always `student`. |
| `POST /api/auth/login` | ❌ | Login with `{"identifier": "<email-or-username>", "password": "..."}`. Returns `access_token` with `role` claim (`student` or `admin`). |
| `GET /api/auth/me` | ✅ | Returns current user profile + role. |
| `POST /api/auth/admin/create` | ✅ (root admin) | Create additional admin accounts. Body mirrors register request but no `profile` needed. Only root admin (`ha22y`) may call. |
| `GET /api/auth/ping` | ❌ | Health check for the auth blueprint. |

---

## 2. Admin – Question Management (`/api/admin`)

All admin routes require a JWT whose `role` is `admin` (root or delegated).

### 2.1 CRUD

| Method & Path | Description |
| ------------- | ----------- |
| `GET /api/admin/questions?page=<n>&per_page=<m>&section?=RW|Math` | Paginated list of questions (includes passage info when present). |
| `POST /api/admin/questions` | Create a question. Body follows `QuestionCreateSchema` (section, sub_section, stem, choices map, `correct_answer`, optional `passage`, `difficulty_level`, `metadata`). Returns created question. |
| `GET /api/admin/questions/:id` | Fetch a single question. |
| `PUT /api/admin/questions/:id` | Replace an existing question (same schema as create). |
| `DELETE /api/admin/questions/:id` | Remove a question. |

### 2.2 AI Parsing Workflow

| Method & Path | Content | Notes |
| ------------- | ------- | ----- |
| `POST /api/admin/questions/upload` | `multipart/form-data` (`file` field) | Stores file under `instance/uploads/` and runs the AI parser task. Response contains a `job` object with status counters (`pending` → `processing` → `completed/failed`). |
| `POST /api/admin/questions/ingest-pdf` | `multipart/form-data` (`file` field) | Uses the multimodal GPT pipeline to read each PDF page (images + text), normalize every detected question, and save drafts. Ideal for scanned tests or image-heavy booklets. |
| `POST /api/admin/questions/parse` | JSON: `{ "blocks": [ { "type": "text\|image\|binary", "content": "...", "metadata": {...} }, ... ] }` | Skip file upload and submit pre-parsed blocks directly. Returns job info; parsed questions are stored as drafts. |
| `GET /api/admin/questions/imports` | None | Lists recent import jobs plus all `question_drafts` awaiting review (`payload` includes the AI-generated `QuestionCreateSchema` data). Drafts are not auto-published; use normal CRUD to persist after review. |

---

## 3. Learning & Practice (`/api/learning`)

All routes require a student JWT (`role=student`).

| Method & Path | Description |
| ------------- | ----------- |
| `GET /api/learning/ping` | Health check. |
| `POST /api/learning/session/start` | Body: `{ "num_questions": <int>, "section?": "RW"|"Math" }`. Uses adaptive engine + review queue to pick questions and opens a `StudySession`. Returns `session` object with ordered question stubs. |
| `POST /api/learning/session/answer` | Body: `{ "session_id", "question_id", "user_answer": {...}, "time_spent_sec?" }`. Records a `UserQuestionLog`, updates mastery & analytics, triggers AI explanation (if `AI_EXPLAINER_ENABLE=true`). Response: `{ "is_correct", "explanation" }`. |
| `POST /api/learning/session/end` | Body: `{ "session_id" }`. Closes the session, updates daily metrics. Returns the finalized `session`. |
| `GET /api/learning/mastery` | Returns ordered mastery snapshot: `[ { "skill_tag", "mastery_score", "success_streak", "last_practiced_at? } ]`. |
| `GET /api/learning/plan/today` | Fetch (or lazily generate) today’s `StudyPlan` for the student. |
| `POST /api/learning/plan/regenerate` | Force-regenerate the current day’s study plan. |

---

## 4. AI Services (`/api/ai`)

Require JWT (student or admin depending on use case).

| Method & Path | Description |
| ------------- | ----------- |
| `GET /api/ai/ping` | Health check. |
| `POST /api/ai/explain` | Body: `{ "question_id": <id>, "user_answer": {...}, "user_language": "bilingual\|en\|zh", "depth": "standard"|... }`. Returns `{"explanation": { protocol_version, answer_correct, explanation_blocks[] } }`. Requires valid `OPENAI_API_KEY` (or set `AI_EXPLAINER_ENABLE=false` to use fallback text). |
| `POST /api/ai/diagnose` | Generates a diagnostic report combining heuristic scores + optional LLM narrative. Response: `{ "predictor": {rw, math}, "narrative": {...} }`. Toggle via `AI_DIAGNOSTIC_ENABLE`. |

---

## 5. Analytics & Metrics

| Method & Path | Auth | Description |
| ------------- | ---- | ----------- |
| `GET /api/analytics/progress` | ✅ (student) | Returns up to `ANALYTICS_HISTORY_DAYS` entries such as `{ day, sessions_completed, questions_answered, accuracy, avg_difficulty, predicted_score_rw, predicted_score_math }`. |
| `GET /metrics` | ❌ | Prometheus exposition for runtime metrics (`sat_requests_total`, `sat_request_latency_seconds`, Python GC stats, etc.). Protect this endpoint at the ingress layer in production. |

---

## 6. Supporting Notes

- **Authentication flow**: Obtain tokens via `/api/auth/login` (students) or root admin credentials (`ha22y/Kicofy5438`). Attach `Authorization: Bearer <token>` on all secured routes. JWT expiration is controlled by `JWT_ACCESS_TOKEN_EXPIRES`.
- **AI configuration**: Set `OPENAI_API_KEY` (or legacy `AI_API_KEY`) plus `AI_EXPLAINER_MODEL`, `AI_DIAGNOSTIC_MODEL`, `AI_PARSER_MODEL`. PDF vision ingestion additionally honors `AI_PDF_VISION_MODEL`, `AI_PDF_NORMALIZE_MODEL`, `PDF_INGEST_RESOLUTION`, and `PDF_INGEST_MAX_PAGES`. Each subsystem can be disabled via `AI_EXPLAINER_ENABLE`, `AI_DIAGNOSTIC_ENABLE`, `AI_PARSER_ENABLE`; disabled services return deterministic stub JSON.
- **Rate limiting**: Driven by `RATE_LIMIT_DEFAULTS` (default `"200 per minute;1000 per day"`). For production use configure a persistent store via `RATELIMIT_STORAGE_URI` (e.g., Redis).
- **Observability**: All requests are logged as JSON with request IDs (also echoed in the `X-Request-ID` response header). `/metrics` exports Prometheus counters/histograms; integrate with your monitoring stack.
- **Testing**: `scripts/test_step12.sh` runs lint + Step05–12 suites. Feature-specific scripts live under `scripts/test_stepXX.sh`. For scripted end-to-end verification, see `scripts/test.py` which exercises the major workflows through real HTTP calls.


