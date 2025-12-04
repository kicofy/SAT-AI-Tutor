# Step 06 – Admin 题库与导入控制台

## Goal
为管理员提供题库管理界面（CRUD、审核草稿、AI 导入监控）并确保权限隔离。

## Dependencies
- Step02 完成的角色守卫
- 后端 `/api/admin/questions/*`

## Tasks
1. **Admin 布局**
   - `/admin` 独立导航（题库、导入任务、用户管理/可选）。
   - 显示当前账号信息、快速入口（创建题目、导入 PDF）。
2. **题库列表**
   - 表格支持搜索、过滤（section、技能标签）、分页。
   - 查看/编辑/删除操作，编辑表单重用 Step05 题目 schema。
3. **AI 导入工作流**
   - 上传区域：`classic`/`vision_pdf` 选项，展示上传进度。
   - 导入任务列表（`/imports`）：状态、总 block 数、错误信息。
   - 草稿审核面板：展示 `payload` 细节，一键发布到正式题库（调用普通 create）。
4. **权限/异常**
   - 若非 admin 访问 `/admin`，跳转 + 提示。
   - API 错误（如 429）要有醒目提示。

## Deliverables
- 完整的 `/admin` 控制台 UI。
- 可上传 PDF 并查看 AI 草稿、发布题目。

## Verification
- 使用 admin 账号登录，能完成“上传 → 草稿 → 发布”流程。
- 学生账号访问 `/admin` 被拦截。

