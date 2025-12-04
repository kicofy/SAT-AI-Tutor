# Step 01 – 前端脚手架与主题基线

## Goal
搭建独立的 Next.js（TypeScript）前端项目，统一依赖、工程规范以及基础主题（Edu + AI 仪表盘 + 轻量游戏风）。

## Dependencies
- 已确定的后端 API 基础（现有 Flask 服务）

## Tasks
1. **初始化项目**
   - `npx create-next-app@latest frontend --ts --eslint --tailwind`（或选择 MUI/Chakra 方案）。
   - 在仓库根目录新增 `frontend/`；设置 `.npmrc`/`.yarnrc`（如需国内源）。
2. **环境变量**
   - 新增 `frontend/.env.local`，包含 `NEXT_PUBLIC_API_BASE=http://127.0.0.1:5080`、`NEXT_PUBLIC_APP_NAME=SAT AI Tutor`。
   - 配置 `next.config.js` rewrites：`/api/* -> ${NEXT_PUBLIC_API_BASE}/api/*`，方便本地联调。
3. **工程规范**
   - 引入 `husky + lint-staged`（格式化/TS 检查）；安装 `prettier`、`eslint-config-next`。
   - 目录结构：`src/app/`（App Router）、`src/components/`、`src/hooks/`、`src/lib/`、`src/styles/`。
4. **主题与设计系统**
   - 定义基础色板（Edu 蓝/AI 霓虹 + Gamification 辅色）、字体（Inter + 中文 fallback）、阴影/圆角。
   - 创建全局 Layout（包含侧边栏占位/顶部导航）、Loading、Error 组件。
   - 准备可复用的卡片组件（DashboardCard、BadgeChip、ProgressGlance）以支撑“AI 仪表盘 + 游戏风”调性。
5. **API 客户端框架**
   - 建立 `src/lib/http.ts`，封装 `fetch`/`axios`，自动注入 `Authorization`（占位）与错误处理。
   - 预留 Token 存储 hook（`useAuthStore`），暂时使用 Mock。

## Deliverables
- `frontend/` Next.js 工程 + README（启动、构建、环境变量说明）。
- 统一的 UI 主题文件和基础组件库。
- 可运行的首页占位（含左侧导航、顶部条、几张示例仪表卡）。

## Verification
- `cd frontend && npm run dev` 能成功启动；访问 `http://localhost:3000` 显示示例仪表盘壳。
- `npm run lint`/`npm run type-check` 无错误。

