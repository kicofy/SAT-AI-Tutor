# Step 03 – 学生仪表盘与学习计划视图

## Goal
打造学生首页（Fashboard/Edu + AI 仪表风），展示学习计划、掌握度、AI 建议等关键信息。

## Dependencies
- 完成 Step02（鉴权/路由）
- 后端 `/api/learning/mastery`, `/api/learning/plan/today`, `/api/analytics/progress`

## Tasks
1. **仪表盘布局**
   - 顶部 Hero：欢迎语 + 当日勋章/连胜。
   - 三列卡片：今日计划、掌握度雷达、AI 建议/诊断预览。
2. **学习计划组件**
   - 调 `GET /api/learning/plan/today`，渲染 blocks（时间、技能、题量）。
   - 提供“重新生成”按钮（`POST /plan/regenerate`），带 Loading/成功提示。
3. **掌握度可视化**
   - 调 `GET /api/learning/mastery`，使用雷达图/条形图呈现。
   - 低掌握技能突出显示，并附“去练习” CTA。
4. **进度历史**
   - 调 `GET /api/analytics/progress`，绘制折线 / 面积图（题量、正确率）。
5. **Gamification 元素**
   - 增加 XP、连胜、徽章卡槽；可先用静态数据，后续绑定真实指标。

## Deliverables
- `/dashboard` 页面可实时展示学生个人数据。
- 主题与交互延续“AI 仪表盘 + 游戏化”风格。

## Verification
- 登录学生账号后可看到真实数据（含 Skeleton 状态）。
- 触发“重新生成计划”后页面实时刷新；错误提示清晰。

