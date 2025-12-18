# SAT AI Tutor

Flask + Next.js 平台，支持自适应练习、AI 讲解、PDF 解析与题目生成。

## 快速开始
1. Python/依赖
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r sat_platform/requirements.txt
   ```
2. 环境变量  
   - 在 `sat_platform/.env` 填写 DB、JWT、AI Key（参考原 `.env.example` 字段）。
   - 常用：`DATABASE_URL`、`CORS_ORIGINS`、`OPENAI_API_KEY`、`AI_EXPLAINER_MODEL`、`AI_PARSER_MODEL`、`AI_PDF_NORMALIZE_MODEL`。
3. 迁移 / DB
   ```bash
   cd sat_platform
   flask db upgrade
   ```
4. 启动后端
   ```bash
   cd sat_platform
   flask --app app run  # 默认 5080
   ```
5. 启动前端
   ```bash
   cd frontend
   npm install
   npm run dev  # 默认 3000，设置 NEXT_PUBLIC_API_BASE_URL 指向后端
   ```
6. 基础测试
   ```bash
   cd sat_platform
   pytest
   ```

## 常用 API
- 健康检查：`GET /api/auth/ping`
- 注册/登录/我：`POST /api/auth/register` / `login` / `GET /api/auth/me`
- 计划：`GET /api/learning/plan/today`，`POST /api/learning/plan/regenerate`
- 练习：`POST /api/learning/session/start` / `answer` / `end`
- AI 讲解：`POST /api/ai/explain`
- 管理员题库：`/api/admin/questions` CRUD，`/api/admin/questions/upload` (PDF)，`/api/admin/questions/parse`

## 题目与校验
- 题目完整性：缺题干/选项/答案/填空 acceptable 会被校验并记录到 `question_validation_issues`，分配时过滤 invalid。
- 填空（SPR）：答案需 ≤5 字符（小数点计入，负号不计），列出所有等价得分形式；PDF 解析与 AI 生成均受此规则约束。

## 配置速查
- 邮件（Zoho 示例）：
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
- 自适应/计划：`ADAPTIVE_*`、`PLAN_*`
- 限流与监控：`RATE_LIMIT_DEFAULTS`，`/metrics` (Prometheus)

## 目录结构
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

## 开发提示
- 修改模型后：`flask db migrate -m "msg" && flask db upgrade`
- 清理已跟踪的忽略文件：`git ls-files -i --cached -X .gitignore -z | xargs -0 git rm --cached`
- 前后端端口：后端 5080 / 前端 3000；确保前端 API 基址指向后端。

## 脚本
`scripts/` 目录下有阶段测试脚本（如 `test_step06.sh`、`test_step07.sh`…），用于回归。运行前确保虚拟环境与依赖已就绪。

