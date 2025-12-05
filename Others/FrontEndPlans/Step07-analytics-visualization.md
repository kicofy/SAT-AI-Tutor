# Step 07 – 学习 & 运营分析可视化

## Goal
提供“数据驱动”的反馈：学生端看到长期进步趋势与技能分布，管理员端了解系统健康度（AI 调用、导入成功率、活跃度），并能导出数据做复盘。

## Dependencies
- Dashboard/Practice 已上线
- 后端 `/api/analytics/progress`, `/api/analytics/mastery-history`, `/metrics`, `/api/admin/questions/imports`
- Charting 库（Recharts / Tremor / VisX）

## Tasks
1. **学生成长趋势**
   - 仪表盘新增 “Insights” 分区：题量累计、准确率、预测分、技能雷达。
   - 支持 7/30/90 天切换；空数据展示引导文案。
   - 每个图表可点击 drill-down → 打开详细 modal（列出具体 session）。
2. **Session & Skill 分析**
   - 列表展示最近 session，总结正确率、耗时、技能影响；支持导出 CSV。
   - 利用 `StudySession.summary` 可视化“策略建议”。
3. **运营监控板（Admin）**
   - `/admin/analytics` 显示 OpenAI 成功率、平均响应时间、导入成功率、活跃学生数。
   - 接入 `/metrics` 或内部 API，加入健康状态徽章（OK / Warning / Down）。
   - 当检测到 401、429 激增时，触发 UI 告警条与链接到日志页面。
4. **可复用图表系统**
   - 抽象 `ChartCard`, `TrendBadge`, `Heatmap` 组件，统一深色主题下的 tooltip/legend。
   - 处理 SSR + CSR 兼容，避免 hydration 警告。
5. **导出 & 分享**
   - 所有分析图表提供 CSV/PNG 导出（使用 `html-to-image` 或 canvas），方便家长/老师。
   - 在学生端支持“分享给家长”按钮（复制链接或生成图像）。

## Deliverables
- 仪表盘 Insights 图表区 + session 列表 + 导出能力。
- `/admin/analytics` 健康监控页（实时状态 + 告警）。
- 可复用的 Chart 组件库。

## Verification
- 切换日期区间时 Recharts/VisX 没有报错，数据正确。
- Metrics 接口异常时，Admin 页显示告警而非崩溃。
- 导出的 CSV/PNG 包含选择范围内的数据，文件名自动带日期。

