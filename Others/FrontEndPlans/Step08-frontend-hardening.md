# Step 08 – 前端硬化、监控与上线准备

## Goal
让前端在真实使用场景下更加稳定、安全、可观测：补齐自动化测试、性能预算、国际化覆盖、CI/CD 流程与上线文档，确保可随时部署。

## Dependencies
- Step01–07 功能完成
- GitHub Actions（或等效 CI）、部署目标（Vercel/自托管）

## Tasks
1. **自动化测试矩阵**
   - Component/Hook 单测：`practice-view`, `ai tutor`, `admin figure cropper`, `auth-store`.
   - E2E（Playwright）：登录→选择语言→开始/恢复练习→生成讲解→取消任务→查看日志。
   - 将 SSE 行为 mock 进测试，验证实时进度 UI。
2. **质量栈与代码扫描**
   - 固化命令：`lint`, `type-check`, `test`, `test:e2e`.
   - 引入 Bundle Analyzer，设置性能预算（`<300KB` 初始 JS）。
   - Sentry/LogRocket 集成前端错误上报。
3. **CI/CD 流程**
   - GitHub Actions Workflow：缓存依赖、运行全套检查、上传构建产物。
   - 构建完成后自动触发 deploy（Vercel CLI 或自托管 rsync）；部署前注入环境变量（API base、SSE endpoints、Zoho mail flag）。
4. **运行时硬化**
   - Next.js 自定义 `headers`：CSP、X-Frame-Options、Referrer-Policy。
   - 懒加载重型模块（admin 图像裁剪、AI 诊断图表）。
   - PWA Manifest + `next-pwa`（离线兜底 + icons）。
5. **国际化检查**
   - 扫描 `t("...")` 缺失情况，确保所有文案中英文都有。
   - 提供语言切换落地页 & QA checklist。
6. **可观测性与文档**
   - 前端埋点（Segment/PostHog 可选）记录关键事件：start session、publish draft 等。
   - 更新 README/Runbook（环境变量、SSE 要求、常见错误）。
   - 编写“发布 checklist”（缓存刷新、数据库联调、回滚步骤）。

## Deliverables
- 通过 CI 的稳定构建、Playwright 报告、Bundle 分析。
- 安全头/监控/错误上报生效的生产配置。
- 最新 README + Runbook + 发布 checklist。

## Verification
- CI 在 PR 上自动运行并阻止未通过的变更。
- 部署到预发后，Lighthouse ≥ 85，Bundle 报告符合预算，SSE/多语言在移动端测试通过。
- 演练一次回滚流程，能在 10 分钟内恢复上一版本。

