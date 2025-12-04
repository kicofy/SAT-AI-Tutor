# Step 02 – 鉴权框架与路由壳

## Goal
实现登录/注册 UI、全局路由守卫、API 客户端与 Token 管理，让前端能够安全地调用后端 `/api/auth/*`。

## Dependencies
- Step01 完成（项目基础、主题、HTTP 封装）

## Tasks
1. **全局状态与 Auth Hook**
   - 使用 `zustand` 或 `redux-toolkit` 保存 `{ user, accessToken }`。
   - 实现 `useAuth()`：提供 `login`, `logout`, `register`, `loadProfile`。
2. **API 集成**
   - 对接 `/api/auth/register`, `/api/auth/login`, `/api/auth/me`，处理错误提示。
   - 自动刷新用户信息，登录后持久化 Token（localStorage + memory）。
3. **路由守卫**
   - 在 `middleware.ts` 或布局中，根据 `user.role` 控制访问 `/admin/*` 与 `/student/*`。
   - 未登录状态跳转到 `/auth/login`；提供访客入口（如 API 文档页）不受限。
4. **UI 页面**
   - `/auth/login`、`/auth/register`：采用卡片式设计 + Gamification 元素（进度点/成就图标）。
   - 成功后导航到相应仪表盘（学生 → `/dashboard`, 管理员 → `/admin`）。

## Deliverables
- 登录/注册/退出流程串通。
- API 错误处理（Toast/提示），未登录跳转机制。

## Verification
- 连接后端实际接口：可注册学生、登录并刷新页面仍保持会话。
- 手动输入受限路由（如 `/admin`）时，非管理员会被拦截并提示。

