# Step 05 – AI 讲解、诊断与学习计划深度整合

## Goal
把 AI 讲解、诊断报告、学习计划/提醒深度融合到前端界面，突出 “AI 学习伙伴” 体验。

## Dependencies
- Step04 完成（练习流程）
- 后端 `/api/ai/explain`, `/api/ai/diagnose`, `/api/learning/plan/*`

## Tasks
1. **AI 讲解中心**
   - 独立页面/抽屉展示最近题目的讲解历史，可按技能过滤。
   - 支持重新请求更深入解释（强制调用 `/api/ai/explain`，不同参数例如 `depth:"deep"`）。
2. **AI 诊断报告**
   - 设计“诊断卡片”：显示预测分、薄弱环节、AI 建议。
   - 调 `POST /api/ai/diagnose`，使用 Loading/缓存，支持“刷新诊断”按钮。
3. **学习计划提醒**
   - 在仪表盘/导航处显示“今天待办”、“AI 推荐下一步”，结合 `plan.blocks`。
   - 增强 Gamification：完成 block 后打勾+奖励动画。
4. **AI 助手机器人**
   - 可选：右下角 AI Bot（聊天 UI），调用与 explain/diagnose 共用接口（先伪装成建议流）。
5. **通知与引导**
   - 若计划或诊断数据过期（如 24h 未更新），显示提示 CTA。

## Deliverables
- AI 讲解历史视图 + 诊断页面。
- 学习计划任务面板（带完成状态、奖励提示）。

## Verification
- 真实账号可拉取诊断报告并在 UI 中查看。
- 学习计划 block 完成操作会影响 UI 状态并与仪表盘同步。

