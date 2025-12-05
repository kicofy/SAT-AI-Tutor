# Step 06 – Admin 题库运营 & 导入监控 2.0

## Goal
在现有临时导入页的基础上，打造一个更稳定的运营控制台：实时监控 AI 导入、手动审校/裁剪图表、审阅 OpenAI 日志，并对已发布题库提供快速查询与批量操作。

## Dependencies
- 现有 `temp-import` 页面与 SSE 事件流
- 后端 `/api/admin/questions/*`, `/api/admin/questions/imports/events`, `/api/admin/logs/openai`
- Question figure 手工裁剪接口

## Tasks
1. **导航与信息架构**
   - 将当前 `/admin/temp-import` 拆分为 Tab：`Imports`, `Draft Review`, `Question Bank`, `AI Logs`.
   - 统一使用 App Shell + sticky sub-nav，保留暗色主题。
2. **导入任务看板**
   - SSE 数据建立本地 store，支持暂停/恢复订阅、断线重连提示。
   - 展示更细粒度信息：当前阶段、剩余页数、自动重试次数、超时警告。
   - 支持按状态过滤、关键字搜索（job id / 文件名）。
3. **草稿审校 & 图表裁剪**
   - 重构草稿卡片：展示 PDF question number、skill tags、AI solution 摘要。
   - Figure cropper 支持键盘微调、缩放预设、坐标预览；保存后实时更新草稿状态。
   - 批量操作：多选草稿后一次性发布/删除（仍需确认弹窗）。
4. **题库运营工具**
   - Question Bank 列表加入搜索、section/skill/has_figure 过滤、分页。
   - 快捷操作：查看题干、打开 figure、清理缓存讲解。
   - 支持导出当前过滤结果为 CSV（前端生成）。
5. **OpenAI 日志中心**
   - 日志区域支持时间轴视图、关键字段筛选（job id、stage、error）。
   - 允许管理员标记“已处理”以隐藏噪音。
6. **权限与审计**
   - 所有敏感操作（删除题目/任务/草稿）弹出自定义确认框并记录本地操作日志（console + UI badge）。
   - 若 token 过期或角色非 admin，自动跳转登录并提示。

## Deliverables
- `/admin/temp-import` 重构为多 Tab 控制台，含任务看板、草稿工具、题库表格、AI 日志。
- 新的搜索/过滤/批量操作功能 + 强化的图表裁剪体验。

## Verification
- 管理员可在同一页面完成：上传 → 监控 → 裁剪/审核 → 发布 → 查看题库。
- SSE 断开后 5 秒内自动重连并在 UI 中提示。
- 搜索/过滤/导出均能反映题库真实数据；非 admin 登录访问立即被拦截。

