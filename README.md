# SAT AI Tutor

Flask + Next.js platform for adaptive practice, AI explanations, PDF parsing, and question generation.

## Quick start
1) Python/Deps
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r sat_platform/requirements.txt
```
2) Environment
 - Fill `sat_platform/.env` (see `.env.example`): `DATABASE_URL`, `CORS_ORIGINS`, `OPENAI_API_KEY`, `AI_EXPLAINER_MODEL`, `AI_PARSER_MODEL`, `AI_PDF_NORMALIZE_MODEL`, etc.
3) Migrations / DB
```bash
cd sat_platform
flask db upgrade
```
4) Run backend
```bash
cd sat_platform
flask --app app run  # default 5080
```
5) Run frontend
```bash
cd frontend
npm install
npm run dev  # default 3000; set NEXT_PUBLIC_API_BASE_URL to backend
```
6) Smoke tests
```bash
cd sat_platform
pytest
```

## Common APIs
- Health: `GET /api/auth/ping`
- Auth: `POST /api/auth/register` / `login` / `GET /api/auth/me`
- Plan: `GET /api/learning/plan/today`, `POST /api/learning/plan/regenerate`
- Practice: `POST /api/learning/session/start` / `answer` / `end`
- AI explain: `POST /api/ai/explain`
- Admin questions: `/api/admin/questions` CRUD, `/api/admin/questions/upload` (PDF), `/api/admin/questions/parse`

## Question integrity
- Missing stem/choices/answer or fill acceptable is recorded in `question_validation_issues`; invalid questions are filtered when assigning.
- Fill (SPR): answers must be ≤5 chars (dot counts, minus does not); list all scoring-equivalent forms. Applies to PDF ingest and AI generation.

## Config cheat sheet
- Mail (Zoho example):
```
MAIL_SERVER=smtppro.zoho.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=noreply@aisatmentor.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER="SAT AI Tutor <noreply@aisatmentor.com>"
MAIL_IMAP_SERVER=imappro.zoho.com
MAIL_IMAP_PORT=993
MAIL_IMAP_USE_SSL=true
```
- Adaptive/Plan: `ADAPTIVE_*`, `PLAN_*`
- Rate/metrics: `RATE_LIMIT_DEFAULTS`, `/metrics` (Prometheus)

## Structure
```
sat_platform/
  app.py / config.py / requirements.txt
  sat_app/
    blueprints/   # auth, admin, learning, ai, analytics...
    services/     # ai_explainer, ai_paper, pdf_ingest, adaptive_engine, ...
    models/       # user, question, study_session, ...
    schemas/ utils/ tasks/
  migrations/
frontend/
  src/...
```

## Dev tips
- After model changes: `flask db migrate -m "msg" && flask db upgrade`
- Clean tracked ignored files: `git ls-files -i --cached -X .gitignore -z | xargs -0 git rm --cached`
- Ports: backend 5080 / frontend 3000; point frontend API base to backend.

## Scripts
See `scripts/` for step test scripts (e.g., `test_step06.sh`, `test_step07.sh`); ensure venv and deps are ready before running.

