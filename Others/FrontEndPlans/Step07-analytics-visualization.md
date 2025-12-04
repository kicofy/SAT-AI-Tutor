# Step 07 – 数据可视化与监控面板

## Goal
深化分析层，包括学生端“进步趋势”与 admin 端“平台监控”，展示 AI/请求指标，形成完整仪表盘体验。

## Dependencies
- Step03～Step06 完成
- 后端 `/api/analytics/progress`, `/metrics`（可通过 Prometheus/Gateway 暴露）

## Tasks
1. **学生趋势分析**
   - 在仪表盘新增“长期趋势”页签：题量、准确率、Mastery 变化、预测分。
   - 支持日期范围选择（7/30/90 天）。
2. **Admin 监控面板**
   - 展示请求数、AI 调用成功率、导入作业状态等（可间接读取 `/metrics` 或使用运维提供的数据）。
   - 设置告警/状态标签（如 rate limit 告警、AI key 错误）。
3. **图表组件库**
   - 抽象 `ChartCard`、`SparklineCard`，统一色彩与 hover。
4. **数据导出**
   - 提供 CSV / JSON 导出按钮，便于老师或运营复盘。

## Deliverables
- 学生与管理员都能查看历史数据图表。
- 图表主题与现有 UI 保持一致。

## Verification
- 接口真实数据可在图表中呈现，无控制台警告。
- 导出功能生成的文件包含正确字段。

