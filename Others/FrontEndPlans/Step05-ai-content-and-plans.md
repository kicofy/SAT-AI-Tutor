# Step 05 – AI 学习教练面板（计划 + 诊断 + 讲解）

## Goal
在已完成的练习体验基础上，把 AI 讲解缓存、学习计划、诊断建议集中到一个“AI Tutor”区域，让学生无需离开 `/practice` 与仪表盘就能看到下一步动作。

## Dependencies
- 当前练习流程（Step04）及说明播放器
- 后端 `/api/learning/plan/today`, `/api/learning/mastery`, `/api/ai/diagnose`, `/api/ai/explain`
- Session resume/summary 数据（`StudySession.summary`）

## Tasks
1. **AI Tutor 面板骨架**
   - 在 `/` 仪表盘新增 “AI Tutor” 折叠卡，展示今日计划摘要、上一次 session summary、诊断建议入口。
   - 提供 `Resume`、`Refresh diagnosis` CTA，接入 React Query 缓存和 loading skeleton。
2. **学习计划交互**
   - 对 `plan.blocks` 增加完成状态，本地缓存完成时间并调用（若后端提供）完成接口；未完成 block 在导航中提醒。
   - 当计划目标与练习中实际完成量差距大时，显示 nudges（e.g. “还差 5 题”）。
3. **诊断/建议卡片**
   - 设计 `Score forecast`、`Weak skills`、`Recommendations` 三张卡；点击“刷新”调用 `/api/ai/diagnose`。
   - 支持多语言文案（English 默认，Chinese 包含关键英文术语）。
4. **讲解历史抽屉**
   - 新增 “Recent Explanations” 列表，拉取最近 session 的 `explanation_cache` 元数据。
   - 点击列表项在右侧抽屉中重放动画（无需再次发起 OpenAI 调用）。
5. **状态同步 & 通知**
   - 当 AI 诊断超过 24h 未更新或计划未完成时，顶栏显示轻量提示。
   - 通过 Zustand/Context 共享 Tutor 面板状态，确保 `/practice` 与 `/` 展示一致。

## Deliverables
- `/` 仪表盘上的 AI Tutor 卡片 + 讲解历史抽屉。
- 计划进度状态与提醒逻辑。
- 诊断卡片 + 刷新流程 + 多语言文案。

## Verification
- 登录学生在 Dashboard 能看到 AI Tutor 数据，触发刷新后 5s 内收到新诊断。
- 完成计划 block 或 session 后刷新页面，进度/提醒同步更新。
- Recent explanations 抽屉可重放任意一次讲解且不触发新的 API 请求。

