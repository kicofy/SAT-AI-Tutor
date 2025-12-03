# SAT-AI-Tutor

SAT AI Tutor is a Flask-based learning platform that pairs adaptive practice with AI-generated explanations, following the architecture documented in `项目计划`.

## Step 01 – Bootstrap Checklist

1. **Python runtime**  
   - Install Python 3.11 (see `.python-version` for the recommended version).
   - Optional: `pyenv install 3.11.9 && pyenv local 3.11.9`.

2. **Virtual environment**  
   ```
   python3 -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**  
   ```
   pip install --upgrade pip
   pip install -r sat_platform/requirements.txt
   ```

4. **Environment variables**  
   ```
   cp sat_platform/.env.example sat_platform/.env
   # edit sat_platform/.env with real database credentials, JWT secret, and AI keys
   ```

5. **Project layout (scaffolded)**  
   ```
   sat_platform/
     app.py             # Entry point (factory stubbed until Step 02)
     config.py          # Base/Dev/Prod config classes
     requirements.txt   # Shared runtime + dev dependencies
     .env.example       # Sample environment variables
     sat_app/
       __init__.py      # create_app placeholder
       extensions.py    # db/jwt/cors placeholders
       models/          # User, Question, Learning, ...
       services/        # AI client, adaptive engine, plan service, ...
       blueprints/      # auth, admin, learning, ai, analytics
       schemas/         # marshmallow / pydantic schemas
       utils/           # file parser, security helpers, etc.
       tasks/           # async tasks (Celery/RQ)
     migrations/        # Flask-Migrate metadata (empty until Step 04)
   ```

6. **Next steps**  
   - Proceed to `Plans/Step02-app-factory-and-config.md` to implement the real Flask factory and extension wiring.
   - Use `开发路线概览.md` for a high-level Chinese summary of all phases.

## Step 02 – App Factory & Configuration Quick Start

1. **Environment awareness**  
   - `sat_platform/config.py` defines `DevConfig`, `ProdConfig`, and `TestConfig`.  
   - Select a config via `FLASK_CONFIG` env var (e.g., `export FLASK_CONFIG=dev`). Defaults to Dev.

2. **Run the development server**  
   ```
   cd sat_platform
   flask --app app run  # or python app.py
   ```
   - Default port is `5080` (configurable via `FLASK_RUN_PORT` / `PORT`).
   - Visit `/api/auth/ping` etc. to confirm blueprints are registered.

3. **Run smoke tests**  
   ```
   cd sat_platform
   pytest
   ```
   - Tests assert that each blueprint’s `/ping` endpoint responds with `{"status":"ok"}`.

4. **What’s next**  
   - Start Step 03 to implement real auth models/endpoints and wire up the database.  
   - Update `.env` with actual secrets/DB URLs before touching persistent data.

> The `Plans/` directory contains detailed instructions for each development phase. Work through them sequentially to keep dependencies manageable.

## Step 03 – Auth Foundation Quick Start

1. **Prepare the database**  
   - The app now calls `db.create_all()` automatically on first request (so SQLite works out of the box).  
   - For explicit control or non-default databases, you can still run:  
     ```
     cd sat_platform
     flask shell -c "from sat_app.extensions import db; db.create_all()"
     ```

2. **Register a user**  
   ```
   curl -X POST http://127.0.0.1:5080/api/auth/register \
     -H "Content-Type: application/json" \
     -d '{
       "email": "student@example.com",
       "password": "StrongPass123!",
       "username": "student1",
       "profile": {
         "daily_available_minutes": 90,
         "language_preference": "en"
       }
     }'
   ```
   - Response includes `access_token` and the persisted user/profile payload.

3. **Login & fetch profile**  
   ```
   curl -X POST http://127.0.0.1:5080/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"identifier":"student@example.com","password":"StrongPass123!"}'
   curl http://127.0.0.1:5080/api/auth/me \
     -H "Authorization: Bearer <token>"
   ```

4. **Tests**  
   - `pytest tests/test_auth.py` covers register/login/me flows plus duplicate-email handling.

5. **Root administrator rules**  
   - On first request (after tables exist) the platform auto-creates a **root admin** using the credentials configured via `.env` (defaults: username `ha22y`, password `Kicofy5438`, email `ha22y@example.com`).  
   - `/api/auth/register` always creates `student` accounts; attempting to pass `role` is ignored.  
   - Only the root admin can create additional admin accounts via:  
     ```
     curl -X POST http://127.0.0.1:5080/api/auth/admin/create \
       -H "Authorization: Bearer <root-token>" \
       -H "Content-Type: application/json" \
       -d '{"email":"coach@example.com","username":"coach1","password":"StrongPass123!"}'
     ```  
     Regular admins cannot call this endpoint.

## Step 04 – Database Migrations & Seeding

1. **Initialize Alembic (once per repo)**  
   ```
   cd sat_platform
   FLASK_APP=app.py flask db init        # already done in this repo
   ```

2. **Generate migrations when models change**  
   ```
   FLASK_APP=app.py flask db migrate -m "describe change"
   FLASK_APP=app.py flask db upgrade
   ```
   - Default DB is SQLite (`DATABASE_URL=sqlite:///sat_dev.db`) but you can point to Postgres in `.env`.

3. **Seed default accounts**  
   ```
   FLASK_APP=app.py flask seed-users       # creates admin + student sample users
   FLASK_APP=app.py flask seed-users --skip-student
   ```
   - Credentials read from `.env` (`ADMIN_DEFAULT_*`, `SEED_STUDENT_*`).  
   - Root admin (ha22y/Kicofy5438) is still auto-created on first request.

4. **CI/Local sanity**  
   - Keep running `pytest` to ensure migrations reflect models (tests use in-memory SQLite).  
   - For Postgres, create a database (e.g., `createdb sat_dev`) and update `DATABASE_URL`.

> Tip: after every model change run migrate+upgrade, commit the generated file in `migrations/versions/`.

### Email configuration (Zoho sample)

Add the following variables to `.env` (values可按自己的域名/账号调整)：

```
MAIL_SERVER=smtppro.zoho.com
MAIL_PORT=587              # 或 465 若使用 SSL
MAIL_USE_TLS=true
MAIL_USE_SSL=false
MAIL_USERNAME=noreply@aisatmentor.com
MAIL_PASSWORD=your-zoho-app-password
MAIL_DEFAULT_SENDER="SAT AI Tutor <noreply@aisatmentor.com>"
MAIL_DEFAULT_NAME=SAT AI Tutor
MAIL_REPLY_TO=support@aisatmentor.com
MAIL_IMAP_SERVER=imappro.zoho.com
MAIL_IMAP_PORT=993
MAIL_IMAP_USE_SSL=true
```

这些值会在 `config.BaseConfig` 中加载，后续邮件发送服务可以直接读取。

## Step 06 – Student Practice Sessions

1. **Migrations & data**
   ```
   cd sat_platform
   FLASK_APP=app.py flask db upgrade    # ensures study_sessions & user_question_logs tables exist
   ```
   - 使用管理员账号先创建一些题目（Step05 API），以便学生 session 可以抽题。

2. **学生发起 session**
   ```
   # 注册/登录学生账号（见 Step03）
   curl -X POST http://127.0.0.1:5080/api/learning/session/start \
     -H "Authorization: Bearer $STUDENT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"num_questions": 3, "section": "RW"}'
   ```
   - 响应包含 `session.id` 以及 `questions_assigned` 列表（题目不含答案）。

3. **提交答案 / 结束 session**
   ```
   curl -X POST http://127.0.0.1:5080/api/learning/session/answer \
     -H "Authorization: Bearer $STUDENT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
           "session_id": 1,
           "question_id": 12,
           "user_answer": {"value": "A"},
           "time_spent_sec": 45
         }'

   curl -X POST http://127.0.0.1:5080/api/learning/session/end \
     -H "Authorization: Bearer $STUDENT_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"session_id": 1}'
   ```
   - `answer` 接口会比较 `user_answer` 与 `questions.correct_answer` 并返回 `is_correct`。

4. **测试脚本**
   ```
   cd /path/to/repo
   bash scripts/test_step06.sh
   ```
   - 脚本会重置 SQLite、运行 Step05 基线测试，然后执行 `tests/test_learning_sessions.py`。

## Step 07 – AI Explainer Integration

1. **环境变量**
   ```
   OPENAI_API_KEY=sk-...
   AI_API_BASE=https://api.openai.com/v1
   AI_EXPLAINER_MODEL=gpt-4.1
   AI_EXPLAINER_ENABLE=true   # 若设为 false，将返回占位讲解
   ```

2. **AI 讲解接口**
   ```
   curl -X POST http://127.0.0.1:5080/api/ai/explain \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
           "question_id": 12,
           "user_answer": {"value": "B"},
           "user_language": "bilingual",
           "depth": "standard"
         }'
   ```
   - 返回结构化 JSON（`protocol_version`, `answer_correct`, `explanation_blocks` 中含中英双语讲解）。

3. **学习会话联动**
   - `POST /api/learning/session/answer` 会自动调用 explainer，并在响应和 `UserQuestionLog.explanation` 中写入同一份讲解，避免重复 LLM 调用。
   - 若 `AI_EXPLAINER_ENABLE=false`，接口依然可用，只是返回默认提示文本。

4. **测试脚本**
   ```
   cd /path/to/repo
   bash scripts/test_step07.sh
   ```
   - 级联执行 Step05 + Step06 测试，然后运行 `tests/test_ai_explainer.py`（通过 monkeypatch 模拟大模型响应，适合 CI）。

## Step 08 – 自适应引擎与掌握度

1. **新配置**
   ```
   ADAPTIVE_DEFAULT_MASTERY=0.5
   ADAPTIVE_CORRECT_INCREMENT=0.05
   ADAPTIVE_INCORRECT_DECREMENT=0.1
   ADAPTIVE_REVIEW_INTERVAL_DAYS=1
   ```
   - 写入 `.env` 后重新启动服务，控制掌握度初值、加减分幅度、复习间隔。

2. **掌握度 & 复习数据**
   - 新表：`skill_masteries`、`question_reviews`（自动迁移：`FLASK_APP=app.py flask db upgrade`）。  
   - 每次 `session/answer` 会调用自适应引擎，更新 `SkillMastery`，并在答错时建立复习队列。

3. **新接口**
   - 会话抽题自动使用自适应引擎，不需要额外参数。  
   - 查看个人掌握度：
     ```
     curl http://127.0.0.1:5080/api/learning/mastery \
       -H "Authorization: Bearer $STUDENT_TOKEN"
     ```
     返回按 mastery_score 升序排列的技能列表。

4. **测试脚本**
   ```
   cd /path/to/repo
   bash scripts/test_step08.sh
   ```
   - 依次执行 Step05~Step07 用例，再运行 `tests/test_adaptive_engine.py` 验证掌握度更新、优先级与复习调度。

## Step 09 – 学习计划服务

1. **新模型与配置**
   - `StudyPlan`（每日计划对象）随迁移 `d64bf7654c9b_add_study_plan_table.py` 自动创建。
   - 建议在 `.env` 中添加可调参数（有默认值）：
     ```
     PLAN_DEFAULT_MINUTES=60
     PLAN_BLOCK_MINUTES=25
     PLAN_REVIEW_MINUTES=10
     ```

2. **生成逻辑**
   - `learning_plan_service.generate_daily_plan(user_id, date)`：
     - 读取 `UserProfile` 的 `daily_available_minutes`、目标分等信息。
     - 引用掌握度快照（Step08 数据）决定重点技能。
     - 输出带 `blocks` 的 JSON（协议 `plan.v1`），并缓存到 `study_plans`。

3. **API**
   ```
   curl http://127.0.0.1:5080/api/learning/plan/today \
     -H "Authorization: Bearer $TOKEN"
   curl -X POST http://127.0.0.1:5080/api/learning/plan/regenerate \
     -H "Authorization: Bearer $TOKEN"
   ```
   - `plan/today` 会懒生成；`regenerate` 用于手动刷新。

4. **测试脚本**
   ```
   cd /path/to/repo
   bash scripts/test_step09.sh
   ```
   - 级联 Step05~Step08 用例，再执行 `tests/test_learning_plan.py`。

## Step 10 – 数据分析与诊断

1. **配置**
   ```
   ANALYTICS_HISTORY_DAYS=30
   AI_DIAGNOSTIC_ENABLE=true
   AI_DIAGNOSTIC_MODEL=gpt-4.1
   ```
   - 若关闭 `AI_DIAGNOSTIC_ENABLE`，接口会返回本地 heuristic 诊断。

2. **数据与服务**
   - 新表：`daily_metrics`（按日聚合练习/预测数据）、`diagnostic_reports`（缓存 AI 输出）。
   - `score_predictor` 根据掌握度估算 RW/Math；`analytics_service` 在每次作答/结束会话时自动更新日指标。

3. **API**
   ```
   curl http://127.0.0.1:5080/api/analytics/progress \
     -H "Authorization: Bearer $TOKEN"

   curl -X POST http://127.0.0.1:5080/api/ai/diagnose \
     -H "Authorization: Bearer $TOKEN"
   ```
   - `progress`：返回时间序列（sessions、questions、accuracy、预测分）。  
   - `diagnose`：生成混合统计 + LLM 叙述（`predictor` + `narrative`）。

4. **测试脚本**
   ```
   cd /path/to/repo
   bash scripts/test_step10.sh
   ```
   - 串行运行 Step05~Step09 测试，再执行 `tests/test_analytics.py`。

## Step 11 – AI 题目解析管线

1. **依赖与配置**
   ```
   AI_PARSER_ENABLE=true
   AI_PARSER_MODEL=gpt-4.1
   ```
   - 上传目录默认写在 `instance/uploads/`，请确保可写；若禁用 AI，系统会用 fallback 规则生成草稿。

2. **上传 & 解析**
   - `POST /api/admin/questions/upload`（multipart/form-data 的 `file` 字段）：保存文件并触发解析任务。
   - `POST /api/admin/questions/parse`（接受 `blocks` JSON）可用于手动提交文本/图片块。
   - `GET /api/admin/questions/imports`：查看最近的导入任务及生成的 `question_drafts`，供审核/发布。

3. **内部流程**
   - `file_parser` 将 PDF/Word/文本拆成标准化 block；`ai_question_parser` 统一调用 GPT 多模态模型并输出 `Question` schema。
   - 每个任务都会把结果存进 `question_drafts`，`is_verified=False`，管理员可二次编辑后调用 Step05 的 CRUD 接口正式入库。

4. **测试脚本**
   ```
   cd /path/to/repo
   bash scripts/test_step11.sh
   ```
   - 会先跑 Step05~Step10 回归，再执行 `tests/test_question_imports.py`，覆盖上传与手动解析流程（AI 调用通过 monkeypatch 模拟）。

## Step 12 – 硬化与上线准备

1. **日志 & 监控**
   - 结构化 JSON 日志 + `X-Request-ID` 贯穿请求；Prometheus `/metrics` 提供 `sat_requests_total`、`sat_request_latency_seconds` 等指标。
   - Rate limit 可通过 `RATE_LIMIT_DEFAULTS` 配置（默认 `200 per minute;1000 per day`）。

2. **安全 & 运行**
   - 全局默认限流（Flask-Limiter），响应头自动附带 `X-Request-ID` 便于追踪。
   - `/metrics` 无需身份验证，适合交给 Prometheus/Scrape job。

3. **部署工具链**
   - `Dockerfile` + `docker-compose.yml`（含 Redis）实现本地/生产一致部署。
   - `.github/workflows/ci.yml` 在 push/PR 上运行 lint + `scripts/test_step11.sh`。

4. **测试脚本**
   ```
   cd /path/to/repo
   bash scripts/test_step12.sh
   ```
   - 先执行 Step11 回归，再跑 `ruff/black/isort` 检查以及 `tests/test_metrics.py`。

## Step 05 – Admin Question CRUD

1. **Models & migrations**  
   - New tables: `passages`, `question_sets`, `questions` (`migrations/versions/dc87f0d73d19_add_question_tables.py`).  
   - Run `FLASK_APP=app.py flask db migrate -m "your message"` when models change, then `flask db upgrade`. SQLite dev DB lives at `sat_platform/sat_dev.db`.

2. **Admin authentication**  
   - Use root admin (`ha22y` / `Kicofy5438`) or a seeded admin (`flask seed-users`) to obtain a bearer token via `/api/auth/login`.  
   - All endpoints below require `Authorization: Bearer <admin-token>`; students receive `403`.

3. **Create a question**  
   ```
   curl -X POST http://127.0.0.1:5080/api/admin/questions \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "section": "RW",
       "sub_section": "Grammar",
       "stem_text": "Which choice corrects the sentence?",
       "choices": {"A":"choice A","B":"choice B","C":"choice C","D":"choice D"},
       "correct_answer": {"value":"A"},
       "difficulty_level": 3,
       "skill_tags": ["grammar","structure"],
       "passage": {"content_text": "Passage text", "metadata": {"source":"demo"}}
     }'
   ```

4. **List / filter / inspect**  
   ```
   curl http://127.0.0.1:5080/api/admin/questions?page=1&per_page=20 \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   curl http://127.0.0.1:5080/api/admin/questions/1 \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```

5. **Update / delete**  
   ```
   curl -X PUT http://127.0.0.1:5080/api/admin/questions/1 \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{...full payload with edits...}'
   curl -X DELETE http://127.0.0.1:5080/api/admin/questions/1 \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```

6. **Tests**  
   - `pytest tests/test_admin_questions.py` validates admin-only access and CRUD lifecycle end-to-end.

