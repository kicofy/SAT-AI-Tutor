# SAT AI Tutor – Backend API & CLI Reference

Base URL: `http(s)://<host>:5080`

Unless stated otherwise, send `Content-Type: application/json` and include `Authorization: Bearer <token>` for authenticated requests. Errors follow the form `{ "message": "...", "status": ... }`.

---

## 1. Authentication (`/api/auth`)

| Endpoint | Auth | Body example | Notes |
| --- | --- | --- | --- |
| `POST /api/auth/register` | ❌ | ```{"email":"student@example.com","password":"StrongPass123!","username":"student1","profile":{"daily_available_minutes":90,"language_preference":"bilingual","exam_date":"2025-05-01","target_score_rw":700,"target_score_math":750}}``` | Always creates a `student`. Response: `{ user, access_token }`. |
| `POST /api/auth/login` | ❌ | `{"identifier":"student@example.com","password":"StrongPass123!"}` | `identifier` accepts email or username. Response includes JWT + user payload. |
| `GET /api/auth/me` | ✅ | n/a | Returns current user (profile, role). |
| `POST /api/auth/admin/create` | ✅ (root) | `{"email":"coach@example.com","username":"coach1","password":"StrongPass123!"}` | Only the root admin (defaults: `ha22y` / `Kicofy5438`) may call; creates a new admin. |
| `GET /api/auth/ping` | ❌ | n/a | Health check. |

---

## 2. Admin Question Management (`/api/admin`)

All endpoints require an admin JWT.

### 2.1 CRUD

| Endpoint | Description / Payload |
| --- | --- |
| `GET /api/admin/questions?page=1&per_page=20&section=RW` | Paginated listing with optional section filter. |
| `POST /api/admin/questions` | Body must satisfy `QuestionCreateSchema`. Example: ```{"section":"RW","sub_section":"Grammar","stem_text":"Which choice corrects the sentence?","choices":{"A":"Choice A","B":"Choice B","C":"Choice C","D":"Choice D"},"correct_answer":{"value":"A"},"difficulty_level":2,"skill_tags":["RW_Grammar"],"passage":{"content_text":"Passage text","metadata":{"source":"demo"}}}``` |
| `GET /api/admin/questions/<id>` | Fetch single question. |
| `PUT /api/admin/questions/<id>` | Replace an existing record (same schema as create). |
| `DELETE /api/admin/questions/<id>` | Remove the question. |

### 2.2 AI Parsing & Ingestion

| Endpoint | Content | Notes |
| --- | --- | --- |
| `POST /api/admin/questions/upload` | `multipart/form-data` (`file=@questions.txt`) | “Classic” ingest (`ingest_strategy="classic"`). Saves the file to `instance/uploads/` and runs `ai_question_parser`. Response: `{ job: {...} }`. |
| `POST /api/admin/questions/ingest-pdf` | `multipart/form-data` (`file=@paper.pdf`) | Multimodal GPT Vision ingest (`ingest_strategy="vision_pdf"`). Each page (text + rendered image) is extracted and normalized into drafts. |
| `POST /api/admin/questions/parse` | `{"blocks":[{"type":"text","content":"Stem\nA\nB", "metadata":{"source":"manual"}}]}` | Manually submit parsed blocks without uploading a file. |
| `GET /api/admin/questions/imports` | n/a | Lists recent jobs and all `question_drafts` (payload contains normalized question JSON ready for review). |

---

## 3. Learning & Practice (`/api/learning`)

Requires a student JWT.

| Endpoint | Body | Result |
| --- | --- | --- |
| `GET /api/learning/ping` | n/a | Health check. |
| `POST /api/learning/session/start` | `{"num_questions":3,"section":"RW"}` (section optional) | Opens a `StudySession` using adaptive engine + review queue. Returns `{ "session": { id, questions_assigned, ... } }`. |
| `POST /api/learning/session/answer` | `{"session_id":1,"question_id":10,"user_answer":{"value":"B"},"time_spent_sec":45}` | Logs answer, updates mastery / spaced repetition / analytics, and returns `{ "is_correct": bool, "explanation": {...} }`. |
| `POST /api/learning/session/end` | `{"session_id":1}` | Finalizes the session and updates daily metrics. |
| `GET /api/learning/mastery` | n/a | `{ "mastery": [{ "skill_tag":"RW_Grammar","mastery_score":0.42,...}, ...] }`. |
| `GET /api/learning/plan/today` | n/a | Returns today’s `StudyPlan` (auto-generated if missing). |
| `POST /api/learning/plan/regenerate` | n/a | Force regeneration for the current day. |

---

## 4. AI Services (`/api/ai`)

| Endpoint | Body | Notes |
| --- | --- | --- |
| `GET /api/ai/ping` | n/a | Health check. |
| `POST /api/ai/explain` | `{"question_id":42,"user_answer":{"value":"C"},"user_language":"bilingual","depth":"standard"}` | Returns detailed explanation blocks. Requires `OPENAI_API_KEY` + `AI_EXPLAINER_ENABLE=true`. |
| `POST /api/ai/diagnose` | n/a | Generates `{ predictor:{rw,math}, narrative:{...} }` for the logged-in student. Controlled by `AI_DIAGNOSTIC_ENABLE`. |

---

## 5. Analytics & Metrics

| Endpoint | Auth | Description |
| --- | --- | --- |
| `GET /api/analytics/progress` | ✅ student | Returns up to `ANALYTICS_HISTORY_DAYS` entries with sessions/questions per day, accuracy, average difficulty, predicted scores, etc. |
| `GET /metrics` | ❌ | Prometheus exposition (`sat_requests_total`, `sat_request_latency_seconds`, AI call metrics). Protect at the ingress layer in production. |

---

## 6. CLI Commands

All commands run from `sat_platform/` with `FLASK_APP=app.py`.

| Command | Description |
| --- | --- |
| `flask seed-users [--skip-student]` | Seeds default admin + student accounts using credentials defined in `.env`. Safe to re-run (will report when records already exist). |
| `flask plan generate --user-id <id> [--date YYYY-MM-DD]` | Generates or refreshes a `StudyPlan` for a single student. Date defaults to today (UTC). |
| `flask plan generate --all [--date YYYY-MM-DD]` | Generates plans for all student accounts; exits early if none exist. |

---

## 7. Supporting Notes

- **Authentication**: Acquire JWT via `/api/auth/login`; include `Authorization: Bearer <token>` for all protected endpoints. Token lifetime is governed by `JWT_ACCESS_TOKEN_EXPIRES`.
- **AI configuration**: Set `OPENAI_API_KEY` (or `AI_API_KEY`). Tunables: `AI_EXPLAINER_MODEL`, `AI_DIAGNOSTIC_MODEL`, `AI_PARSER_MODEL`, `AI_PDF_VISION_MODEL`, `AI_PDF_NORMALIZE_MODEL`, `AI_TIMEOUT_SECONDS`, `PDF_INGEST_RESOLUTION`, `PDF_INGEST_MAX_PAGES`. Toggles: `AI_EXPLAINER_ENABLE`, `AI_DIAGNOSTIC_ENABLE`, `AI_PARSER_ENABLE`.
- **Email**: `.env.example` ships with Zoho defaults; `config.BaseConfig` loads them for future email delivery.
- **Rate limiting & observability**: `RATE_LIMIT_DEFAULTS` (default `200 per minute;1000 per day`) powers Flask-Limiter. Every response includes `X-Request-ID`. `/metrics` exposes Prometheus counters/histograms.
- **Testing & tooling**: `scripts/test_stepXX.sh` chain per-step suites; `scripts/test.py` serves as an end-to-end smoke (admin question CRUD → student practice → AI explain/diagnose → metrics). `scripts/pdf_ai_ingest.py` mirrors the backend’s multimodal PDF workflow for manual ingestion.



