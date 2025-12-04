# Step 04 – 练习流程与题目作答体验

## Goal
实现学生做题全流程（选择题量 → 展示题干 → 提交 → AI 讲解），并与后端 `/api/learning/session/*` 完整对接。

## Dependencies
- Step03 完成（仪表盘）
- 题库与 session API 可用

## Tasks
1. **Session 启动界面**
   - 弹窗或独立页面，配置科目、题量、目标技能。
   - 调 `POST /session/start` 并缓存返回的 `session`。
2. **题目展示组件**
   - 支持单选/多选/填空（视后端 question schema）。
   - 提供计时条、提示/跳题（可选）。
   - Gamification：正确时庆祝动画、XP 加分。
3. **提交答案**
   - `POST /session/answer`，展示即时判定（正确/错误）和 AI 讲解。
   - 讲解面板：以聊天/卡片形式显示 `explanation_blocks`。
4. **Session 总结**
   - 调 `POST /session/end`，展示本次成绩（准确率、掌握度变化、AI 建议）。
   - 提供“回到仪表盘”/“继续练习”按钮。
5. **异常/重试**
   - 网络错误、题目加载异常的兜底 UI。
   - Session 断开后允许恢复（缓存当前进度）。

## Deliverables
- `/practice` 路由（或仪表盘内嵌）提供完整做题体验。
- 作答后可查看 AI 讲解并回写到 UI。

## Verification
- 通过真实 API 走一遍“开始 → 做题 → 讲解 → 结束”流程。
- QA：关闭浏览器再打开，能提示恢复或新建 Session。

