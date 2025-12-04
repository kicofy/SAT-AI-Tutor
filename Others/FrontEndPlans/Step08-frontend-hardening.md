# Step 08 – 前端硬化、测试与部署

## Goal
完成前端质量保障（测试、Lint、性能优化）与部署流水线，确保与后端同步上线。

## Dependencies
- 前述 Step01–07 功能完成
- CI 环境（GitHub Actions 等）

## Tasks
1. **测试覆盖**
   - 单元测试：关键组件/Hook（Auth、Plan、Practice）使用 `jest`/`react-testing-library`。
   - E2E：`playwright` 或 `cypress`，脚本覆盖登录、做题、AI 讲解、PDF 导入流程。
2. **质量工具**
   - `npm run lint`（ESLint + Prettier）、`npm run type-check`、`npm run test`.
   - Lighthouse/Next.js 分析性能，优化图片懒加载、脚本分包。
3. **CI/CD 集成**
   - GitHub Actions：安装依赖 → lint → test → build。
   - 构建产物上传（Vercel、Netlify 或自托管）；记录环境变量（API Base、Sentry DSN 等）。
4. **生产配置**
   - 启用 `Next.js` Image Optimization、`headers`（安全头/CSP）、`compression`。
   - 配合 Nginx/Ingress，将 `/api/*` 代理到 Flask 服务，其他路径由 Next.js 处理。
5. **文档与交接**
   - 更新 `frontend/README.md`：开发命令、环境变量、联调说明、部署步骤。
   - 记录常见问题/排查指南。

## Deliverables
- 稳定可部署的前端产物 + CI 流水线。
- 自动化测试报告。

## Verification
- CI 成功运行：Lint/Test/Build 全部通过。
- 生产环境可访问（与后端联通），Lighthouse 得分达标（性能>80，PWA/可访问性按需）。

