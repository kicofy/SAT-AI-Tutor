## SAT AI Tutor – Frontend

Next.js (App Router + TypeScript + Tailwind) UI，用于呈现 Edu + AI 仪表盘 + Gamification 风格的学习体验。

### 目录结构

```
frontend/
  src/
    app/          # Next App Router routes
    components/   # Layout、UI、Providers
    data/         # Mock 数据（后续接 API）
    lib/          # 主题、HTTP、env
```

### 环境变量

复制 `.env.example` 为 `.env.local`：

```
NEXT_PUBLIC_APP_NAME=SAT AI Tutor
NEXT_PUBLIC_API_BASE=http://192.168.50.235:5080
NEXT_PUBLIC_GAMIFICATION_COPY=Keep your streak alive today!
```

开发环境下，`next.config.ts` 会将 `/api/*` 代理到 `NEXT_PUBLIC_API_BASE`，方便与 Flask 后端联调。

### 常用命令

```bash
npm install          # 安装依赖
npm run dev          # 本地开发 (http://localhost:3000)
npm run lint         # ESLint
npm run build        # 生产构建
npm run start        # 预览生产包
```

### 已完成（Step 01）
- Next.js + TypeScript + Tailwind 初始化并添加 React Query、Axios、Zustand 等基础依赖。
- 全局主题（Edu + AI 仪表盘）及 AppShell（侧边栏、顶部栏、卡片组件）。
- HTTP 客户端封装 (`src/lib/http.ts`) 与环境读取 (`src/lib/env.ts`)。
- 示例仪表盘展示（学习计划、掌握度、AI 提示），后续将替换为真实 API 数据。

### Step 02 – 鉴权与路由壳
- `/auth/login`、`/auth/register` 页面已就绪，表单通过 `/api/auth/*` 调用后端。
- `zustand` 状态 + `useAuth` hook 负责保存用户与 Token（存储在 localStorage + Cookie）。
- `middleware.ts` 守卫所有应用路由，未登录将重定向至 `/auth/login`。
- 顶部栏新增“退出”按钮，清除凭证并返回登录页。

### 多语言（默认英文）
- `LocaleProvider` + `useI18n` 提供英文/中文文案，注册时可选择语言偏好（会同步保存到后端 profile）。
- 登录后会自动根据 profile 的 `language_preference` 更新界面；未来也可在账号设置中修改（写入同一偏好）。
- 所有 UI 文案（仪表盘、侧栏、登录页等）均走翻译字典，方便扩展更多语言。

接下来可按 `Others/FrontEndPlans/` 中的 Step02 开始实现鉴权与路由守卫。
