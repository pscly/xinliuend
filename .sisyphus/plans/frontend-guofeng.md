# 国漫中国风前端（青绿山水）+ 协作评论系统：一体化工作计划

## TL;DR

> **目标**：把当前“只有管理后台”的形态升级为真正的用户产品：Web 端笔记 + Todo + 日历 + 搜索 + 标签，并以“青绿山水国漫中国风”做出强辨识度；同时补齐协作评论/批注、站内通知、暗色模式、CN/EN 双语，并将鉴权升级为 httpOnly Cookie。
>
> **核心交付物**：
> - 新的用户端 Web 前端（Next.js/React），路由/页面/设计系统/组件库完整
> - 后端新增/调整：Cookie 会话鉴权、评论/批注/通知、匿名评论治理、用户端 admin gate
> - 自动化验证：后端 `uv run pytest` + 前端 Playwright E2E（覆盖关键路径）
>
> **预计工作量**：XL
> **并行执行**：YES（3 waves）
> **关键路径**：Cookie 鉴权与权限模型 → 评论/批注数据模型 → 前端信息架构与编辑器 → 日历/重复任务 → E2E 全链路

---

## Context

### 原始诉求
- 需要一个“好看、易用、扩展性高”的用户端前端，主题为国漫中国风（青绿山水）。
- 前端不再只是 admin 界面；admin 只在管理员登录时可进入。

### 需求确认（来自访谈）
- 形态：Web（浏览器）。
- 用户模型：多用户账户。
- MVP 模块：笔记、Todo、仪表盘、全局搜索、标签/分类、日历。
- 笔记编辑：Markdown + 富文本 UI，但 **Markdown 是真源**。
- Todo：清单（GTD）为主，混合视图；日历 **必须支持重复任务**。
- 协作：不做共同编辑；要“分享链接（只读）+ 评论/批注”。
- 评论特性：基础评论、强定位批注（随编辑尽量自动迁移）、@提及+站内通知、表情/点赞、附件。
- 评论权限：支持登录用户评论 & 匿名评论（由管理员可切换）；匿名评论治理：限流+验证码+审核开关+举报/折叠。
- 语言：CN/EN 双语从第 1 天开始。
- 主题：青绿山水；需要暗色模式。
- 技术栈：Next.js（React）。
- 鉴权：希望从 Bearer token 迁移到 httpOnly Cookie。
- Admin 入口：放在设置页，仅管理员可见；普通用户直接访问应重定向首页。
- 测试：E2E 为主（Playwright）。

### 现有后端事实（证据化）
- FastAPI 后端，存在 v1 + v2：
  - v1（可配置前缀，默认文档示例为 `/api/v1`）：`src/flow_backend/main.py`, `src/flow_backend/config.py`, `README.md`。
  - v2：`src/flow_backend/v2/app.py`（mounted at `/api/v2`）。
- 目前鉴权是 `Authorization: Bearer <memos_token>`，无 cookie 会话：`src/flow_backend/deps.py`。
- v1 登录注册是 username+password，返回 `{code,data:{token,server_url}}`：
  - `src/flow_backend/routers/auth.py`, `src/flow_backend/schemas.py`, `README.md`。
- Notes（v2）是 markdown 文本 `body_md`，冲突返回 409 + `server_snapshot`：
  - `src/flow_backend/models_notes.py`, `src/flow_backend/v2/routers/notes.py`, `tests/test_api_v2_notes_crud.py`。
- 分享链接是 token-based 且 **公开只读**，支持公开下载附件：
  - `src/flow_backend/v2/routers/shares.py`, `src/flow_backend/v2/routers/public.py`, `tests/test_sharing.py`。
- Todo（v1）包含 occurrences/rrule；后端不展开 RRULE，**由客户端展开**（且 tzid 固定 Asia/Shanghai）：
  - `README.md`（RRULE 约定段落）, `src/flow_backend/routers/todo.py`。
- 管理后台已存在（Jinja2 server-rendered），并使用独立的 cookie session：
  - `src/flow_backend/routers/admin.py`, `src/flow_backend/templates/admin/*`。
- 后端测试已具备：`pytest` + anyio；运行方式：`uv run pytest`：
  - `pyproject.toml`, `README.md`, `tests/*`。

### Metis Review（已吸收的关键提醒）
- Cookie 鉴权引入 CSRF 风险，必须先定 SameSite + CSRF token 策略。
- Markdown 渲染/评论/附件是典型 stored-XSS 面；必须定义 sanitization 策略并做自动化回归。
- v1/v2 能力差异大：Todo recurrence 需要 v1；Notes 建议 v2。
- 强定位批注 + 自动迁移必须定义 fallback 行为，否则用户信任崩溃。

---

## Work Objectives

### Core Objective
交付一个“可长期演进”的用户端产品级前端，并补齐后端协作/鉴权/治理能力，使笔记 + Todo + 日历等功能在同域名部署下可用且可自动化验证。

### Concrete Deliverables
- 新用户端前端（Next.js/React）：路由、页面、组件、设计 tokens、暗色模式、i18n。
- 后端扩展：
  - Cookie session 鉴权（httpOnly）+ CSRF。
  - RBAC：在用户体系内增加 `is_admin`，用于用户端隐藏管理员入口与路由守卫。
  - 评论/批注/通知 API + 数据模型 + 管理端开关。
  - 匿名评论治理（验证码、审核、举报/折叠、限流）。
  - admin gate：供用户端隐藏入口与强制跳转。
- 自动化：
  - 后端：`uv run pytest` 全绿。
  - 前端：Playwright E2E 覆盖关键路径（含 CN/EN 与暗色模式）。

### Definition of Done
- 用户端能完成：注册/登录 → 创建/编辑笔记 → 标签/搜索 → 分享只读链接 → 评论/批注/@提及通知 → Todo GTD → 重复任务 + 日历视图。
- 非管理员无法通过“直接访问 URL”进入用户端 admin 区域；管理员可进入（且不破坏现有 `/admin`）。
- 全部自动化测试可一键跑通：
  - 后端：`uv sync --extra dev && uv run pytest` → PASS。
  - 前端：`npm ci && npx playwright test` → PASS（E2E 关键路径）。

### Must NOT Have（Guardrails / 防止范围膨胀）
- 不做实时协作共同编辑（无 OT/CRDT、无实时光标）。
- 不引入 workspace/成员/ACL 体系（除非后续明确追加）。
- 通知只做站内，不做邮件/推送。
- 评论/批注只覆盖笔记，不覆盖 Todo。
- 不在前端重写一套 RRULE 引擎以替代后端约定；遵循现有 v1 occurrences 协议。

---

## Verification Strategy

### Test Decision
- 后端测试基础设施：已存在（pytest + anyio）
  - 参考：`pyproject.toml`, `README.md`, `tests/*`
- 前端：新增 Playwright（E2E 为主）

### 后端验证命令（现有）
```powershell
uv sync --extra dev
uv run ruff check .
uv run ruff format .
uv run pytest
```

### E2E 环境建议（避免依赖外部 Memos）
- 本仓库 README 提到联调可用 `DEV_BYPASS_MEMOS=true`（用于绕过 Memos 对接）。
- Playwright E2E 建议在本地/CI 使用：SQLite + `DEV_BYPASS_MEMOS=true`，以保证测试稳定与可复现。

### 前端验证命令（将新增）
```powershell
cd web
npm ci
npx playwright install
npx playwright test
```

---

## Execution Strategy

Wave 1（基础设施与协议定稿，可并行）
- 1) UI 设计系统（青绿山水 + 暗色 + i18n tokens）
- 2) 前端工程脚手架（Next.js + Playwright + i18n 基础）
- 3) 部署与本地联调策略（同域名同服务 + Cookie）
- 4) 后端：Cookie session + CSRF + admin gate 的最小闭环

Wave 2（核心业务能力）
- 5) 笔记（v2）+ 编辑器（Markdown 真源 + 富文本 UI）
- 6) Todo（v1）+ RRULE/occurrences + 日历视图
- 7) 搜索（notes v2 q + todo v1 列表合并）+ 标签体系

Wave 3（协作与治理 + 质量）
- 8) 分享页（public share）+ 评论/批注 + 反垃圾/审核/举报
- 9) 站内通知（@提及、回复、审核事件）
- 10) 全链路 E2E 覆盖 + 安全回归（XSS/CSRF）+ 性能/可用性收尾

---

## TODOs

> 说明：每个任务都包含“参考点（文件/协议）”与“可执行验收”。

- [x] 1. 设计系统与视觉规范（青绿山水 + 暗色 + CN/EN）

  **What to do**:
  - 定义 Design Tokens：色彩（青绿/金箔/朱砂点缀/宣纸底纹）、字号体系（中文衬线 + 英文搭配）、间距、圆角、阴影、动效曲线。
  - 定义组件视觉语言：卡片边框像“描金”，hover 像“墨晕扩散”，列表分隔像“宣纸压痕”。
  - 输出：前端 tokens 文件结构（例如 `web/src/theme/tokens.ts` + CSS variables）与组件规范文档（md）。

  **Must NOT do**:
  - 不做“随便套 Tailwind 默认风格/Inter 字体”的通用模板。

  **Recommended Agent Profile**:
  - Category: `visual-engineering`
    - Reason: 需要高辨识度 UI/UX 与可扩展设计系统。
  - Skills: `frontend-ui-ux`, `ui-ux-pro-max`
    - `frontend-ui-ux`: 负责 UI/UX 与交互层级。
    - `ui-ux-pro-max`: 负责 token 化与可扩展组件状态设计。
  - Skills Evaluated but Omitted:
    - `playwright`: 该任务不做自动化。

  **Parallelization**:
  - Can Run In Parallel: YES
  - Parallel Group: Wave 1
  - Blocks: 5, 6, 7, 8, 9, 10
  - Blocked By: None

  **References**:
  - `README.md` - 明确产品定位与现有端口/路径（对视觉不直接，但影响信息架构入口）。

  **Acceptance Criteria**:
  - [x] 设计 tokens 与组件规范文档已在前端目录中落地（并可被其他任务引用）。


- [x] 2. 新建用户端前端工程（Next.js + Playwright + i18n + 暗色骨架）

  **What to do**:
  - 在仓库内新增 `web/`（Next.js App Router）。
  - 建立基础路由骨架：`/`（dashboard）、`/notes`、`/todos`、`/calendar`、`/search`、`/settings`。
  - i18n：CN/EN 切换（含日期/相对时间 locale）。
  - 暗色模式：跟随系统 + 手动切换（tokens 驱动）。
  - Playwright：E2E 框架与最小 smoke test（能打开首页并截图）。

  **Must NOT do**:
  - 不引入过多状态管理/抽象（先跑通架构，再扩展）。

  **Recommended Agent Profile**:
  - Category: `unspecified-high`
    - Reason: 工程搭建 + 约定落地，涉及多文件与长期维护。
  - Skills: `playwright`, `frontend-ui-ux`
    - `playwright`: E2E 基座与后续验收。
    - `frontend-ui-ux`: 路由骨架与布局。

  **Parallelization**:
  - Can Run In Parallel: YES
  - Parallel Group: Wave 1 (with Task 1)
  - Blocks: 3, 4, 5, 6, 7, 8, 9, 10
  - Blocked By: None

  **References**:
  - `README.md` - 后端默认端口 31031，E2E 环境需对齐。

  **Acceptance Criteria**:
  - [x] `web/` 可 `npm ci` 安装。
  - [x] `npx playwright test` 至少 1 条 smoke 用例 PASS。


- [x] 3. 部署与本地联调策略（同域名同服务 + Cookie）

  **What to do**:
  - 定稿生产部署形态：
    - 推荐：Next.js 静态导出（`output: 'export'`）产物由 FastAPI 托管（同进程同域名）。
    - 确保 `/admin` 仍由后端模板渲染，不被前端路由覆盖。
  - 定稿本地联调策略（为 Playwright 与开发体验服务）：
    - 允许前端 dev server 与后端不同端口（同 host），Cookie 仍可跨端口复用；
    - 后端需允许 `allow_credentials=True` + 精确 `CORS_ALLOW_ORIGINS`（不能用 `*`）。
  - 产出一份文档：如何启动 backend + web（dev）与如何 build/export 并由 backend 托管（prod-like）。

  **Recommended Agent Profile**:
  - Category: `unspecified-high`
  - Skills: `frontend-ui-ux`

  **Parallelization**:
  - Can Run In Parallel: YES
  - Parallel Group: Wave 1
  - Blocks: 10
  - Blocked By: 2, 4

  **References**:
  - `src/flow_backend/main.py` - FastAPI app 挂载点（用于静态托管与路由优先级）。
  - `src/flow_backend/config.py` - CORS 配置来源。
  - `README.md` - 现有端口与启动方式。

  **Acceptance Criteria**:
  - [x] 文档落地并可被 E2E 按文档方式启动环境（无人工摸索）。


- [x] 4. 后端：Cookie Session 鉴权 + CSRF + 用户端 admin gate（最小闭环）

  **What to do**:
  - 在保留现有 Bearer token 机制的同时，新增 Cookie-based session：
    - 登录成功后设置 httpOnly cookie（同域名）。
    - API 支持从 cookie 识别用户（替代前端存 token）。
  - CSRF 策略：SameSite + CSRF token（双提交或 header token）。
  - CORS 调整（为 dev 端口联调服务）：
    - `allow_credentials=True`
    - origins 使用显式 allowlist（例如 `http://localhost:3000`、`http://localhost:31031` 等）
    - 生产同域名部署下不依赖跨域，但测试环境必须可跑通
- 新增 admin gate：
    - 新增 `GET /api/v1/me`（或同等）返回当前登录用户的 `username` + `is_admin`。
    - 普通用户访问用户端 admin route 时应返回 403/401，前端据此跳首页。
  - RBAC 最小化落地：
    - `User` 增加 `is_admin: bool`（默认 false）。
    - 管理员可在现有 `/admin` 管理后台中切换用户的 `is_admin`。
  - 对应单元测试补齐。

  **Must NOT do**:
  - 不删除/破坏现有 `Authorization: Bearer`（兼容已有客户端与现有测试）。

  **Recommended Agent Profile**:
  - Category: `unspecified-high`
    - Reason: 鉴权变更涉及安全与全局行为。
  - Skills: `git-master`
    - `git-master`: 需要安全地拆分提交与追踪变更。

  **Parallelization**:
  - Can Run In Parallel: YES
  - Parallel Group: Wave 1 (with Task 1, 2)
  - Blocks: 5, 6, 7, 8, 9, 10
  - Blocked By: None

  **References**:
  - `src/flow_backend/deps.py` - 现有 Bearer token 鉴权入口。
  - `src/flow_backend/routers/auth.py` - v1 登录/注册入口（需要扩展 set-cookie）。
  - `src/flow_backend/routers/admin.py` - 现有 admin cookie 会话（可复用思想/实现）。
  - `src/flow_backend/models.py` - `User` 表（新增 `is_admin` 字段的落点）。
  - `tests/test_admin_security.py` - admin 会话安全测试模式。
  - `tests/test_auth_login_requires_token.py` - 现有 login 行为约束（兼容性风险点）。

  **Acceptance Criteria**:
  - [x] `uv sync --extra dev && uv run pytest` → PASS。
  - [x] 新增测试覆盖：无 CSRF token 的跨站请求被拒绝（至少 1 条用例）。


- [x] 5. 前端：登录/会话/路由守卫 + 笔记（v2）CRUD + 编辑器（Markdown 真源 + 富文本 UI）

  **What to do**:
  - 登录页：username+password（匹配后端校验：仅字母数字，长度 1..64）。
  - 会话：使用 cookie session；前端不保存 memos_token。
  - 笔记：对接 v2 API（创建/列表/筛选 tag/搜索 q/编辑/删除/恢复/版本历史）。
  - 编辑器：富文本 UI，但保存为 markdown 字符串 `body_md`；提供模式切换/预览。
  - 冲突处理：遇到 409 conflict，展示 server_snapshot 对照与解决选项（至少支持“用服务器版本覆盖/用本地覆盖/复制为新笔记”中的一种 MVP 路径）。

  **Must NOT do**:
  - 不把 HTML 作为持久化真源。

  **Recommended Agent Profile**:
  - Category: `visual-engineering`
  - Skills: `frontend-ui-ux`, `playwright`

  **Parallelization**:
  - Can Run In Parallel: YES
  - Parallel Group: Wave 2
  - Blocks: 8, 9, 10
  - Blocked By: 2, 4

  **References**:
  - `src/flow_backend/v2/routers/notes.py` - notes v2 endpoints。
  - `tests/test_api_v2_notes_crud.py` - notes CRUD、tag filter、conflict 409、revisions、restore 的可依赖行为。
  - `src/flow_backend/models_notes.py` - `Note.body_md` + revisions snapshot 结构。
  - `docs/api.zh-CN.md` - 客户端 header 约定与同步/冲突说明。

  **Acceptance Criteria**:
  - [x] Playwright E2E：
    - 登录成功后进入 dashboard。
    - 创建笔记 → 列表可见。
    - 切换到富文本编辑后保存，重新打开笔记，markdown 内容一致。
    - 构造 conflict（用 API 先更新 client_updated_at_ms），前端能看到冲突提示页并可选择一种解决路径。
  - [x] 生成截图：`.sisyphus/evidence/notes-editor-light.png` 与 `.sisyphus/evidence/notes-editor-dark.png`。


- [x] 6. 前端：Todo（v1）GTD + RRULE/occurrences + 日历视图（必须支持重复任务）

  **What to do**:
  - 对接 v1 todo lists/items/occurrences API：
    - 列表（lists）+ 任务（items）+ occurrences。
  - RRULE 处理遵循 README 约定：
    - tzid 固定 `Asia/Shanghai`；后端不展开 RRULE；客户端负责展开并通过 occurrences 记录例外。
  - 日历视图：月/周视图至少一个；支持从/to 区间拉取 occurrences。
  - 完成/跳过某次 occurrence：通过 v1 occurrences endpoint 写入例外。

  **Must NOT do**:
  - 不自行推导一个与后端不一致的 recurrence 语义。

  **Recommended Agent Profile**:
  - Category: `unspecified-high`
    - Reason: recurrence 与日历属于复杂业务逻辑。
  - Skills: `playwright`

  **Parallelization**:
  - Can Run In Parallel: YES
  - Parallel Group: Wave 2 (with Task 5, 7)
  - Blocks: 10
  - Blocked By: 2, 4

  **References**:
  - `README.md` - RRULE 协议约定（tzid、dtstart_local 格式、客户端展开）。
  - `src/flow_backend/routers/todo.py` - v1 todo + occurrences 行为。
  - `docs/api.zh-CN.md` - v1 todo 字段与同步说明。

  **Acceptance Criteria**:
  - [x] Playwright E2E：
    - 新建重复任务（例如每日重复）。
    - 在日历上看到 7 天内 occurrences。
    - 完成某一天 occurrence 后，该天在日历上状态变化，并且下次打开仍保持。


- [x] 7. 前端：Dashboard + 全局搜索（notes+todo）+ 标签/分类体验

  **What to do**:
  - Dashboard：今日待办、最近笔记、快捷入口（符合国风视觉）。
  - 全局搜索：
    - notes：调用 v2 `/api/v2/notes?q=...`。
    - todos：调用 v1 items 列表（按 title/内容过滤，或服务端若支持则用其参数）。
    - 合并展示结果（按类型分组）。
  - 标签：
    - notes tag（v2，case-insensitive exact match）
    - todo tags（v1 tags_json / filter）
  - 统一的“标签页”体验：能看到各标签下的笔记与任务。

  **Recommended Agent Profile**:
  - Category: `visual-engineering`
  - Skills: `frontend-ui-ux`, `playwright`

  **Parallelization**:
  - Can Run In Parallel: YES
  - Parallel Group: Wave 2
  - Blocks: 10
  - Blocked By: 2, 4, 5, 6

  **References**:
  - `tests/test_api_v2_notes_crud.py` - v2 notes 的 tag filter 与 list 行为。
  - `README.md` - v1 todo endpoints 列表。

  **Acceptance Criteria**:
  - [x] Playwright E2E：
    - 新建笔记 tag=Work；新建 todo tag=Work。
    - 搜索 "Work"：能看到 notes + todos 两类结果。
    - 标签页点击 Work：能看到对应笔记与任务。


- [x] 8. 后端 + 前端：分享页（public share）+ 评论/批注/附件 + 匿名治理 + 管理开关

  **What to do**:
  - 复用现有 share link（只读）作为分享入口：`/api/v2/public/shares/{token}`。
  - 新增“评论/批注”数据模型与 API：
    - 评论线程（按 note_id / share_token 关联）
    - 批注（包含 anchor 数据：强定位 + 迁移信息 + fallback 状态）
    - 反应（reaction）
    - @提及解析
    - 评论附件：复用现有 object storage 能力（参考 attachments 机制）。
  - 权限矩阵：
    - login-only vs anonymous allowed（可被管理员全局切换，必要时允许 per-share 覆盖）。
    - 匿名：验证码 + 限流 + 审核开关 + 举报/折叠。
  - 前端：
    - 分享页（公开只读）渲染国风主题；评论区、批注浮层、附件预览。
    - 当匿名被禁用时，提示登录。

  **Must NOT do**:
  - 不把评论/批注扩展到 todo。
  - 不引入共同编辑。

  **Recommended Agent Profile**:
  - Category: `unspecified-high`
  - Skills: `playwright`, `git-master`
    - `playwright`: 公开分享页 + 评论区必须自动化验证。
    - `git-master`: 涉及数据库迁移与多模块变更，需拆分提交。

  **Parallelization**:
  - Can Run In Parallel: NO
  - Parallel Group: Wave 3
  - Blocks: 9, 10
  - Blocked By: 4, 5

  **References**:
  - `src/flow_backend/v2/routers/public.py` - public share fetch。
  - `src/flow_backend/v2/routers/shares.py` - share create/revoke。
  - `tests/test_sharing.py` - share token 安全、过期 410、撤销 404。
  - `src/flow_backend/v2/routers/attachments.py` + `tests/test_attachments.py` - 附件上传/下载/大小限制测试模式。
  - `tests/test_rate_limiting.py` - 现有 rate limit 测试模式。

  **Acceptance Criteria**:
  - [x] 后端：新增 pytest 覆盖以下行为：
    - anonymous disabled 时匿名 POST 评论返回 401/403。
    - anonymous enabled + 无验证码时返回 400（或挑战要求）。
    - 举报后评论在公开页被折叠（状态可见）。
  - [x] Playwright E2E：
    - 创建 share link → 打开 public share page（无需登录）。
    - 切换到“匿名可评论”后：完成验证码流程（可用测试 bypass）并成功发布评论。
    - 发布带附件评论，分享页可下载附件。


- [x] 9. 站内通知中心（@提及/回复/审核事件）

  **What to do**:
  - 后端新增通知模型与 API（按 user_id 存储，未读数、已读标记）。
  - 触发源：
    - @提及
    - 回复某条评论
    - 审核通过/驳回（当审核开关启用）
  - 前端：顶部通知入口 + 未读数 + 通知列表；点击跳转到对应笔记/批注。

  **Recommended Agent Profile**:
  - Category: `unspecified-high`
  - Skills: `playwright`

  **Parallelization**:
  - Can Run In Parallel: NO
  - Parallel Group: Wave 3
  - Blocks: 10
  - Blocked By: 8

  **References**:
  - `src/flow_backend/models.py` - 用户模型与 tenant 约定（通知按 user_id）。
  - `tests/*` - 现有 anyio + httpx ASGITransport 测试风格。

  **Acceptance Criteria**:
  - [x] `uv run pytest` 覆盖：@提及会创建通知、标记已读生效。
  - [x] Playwright：A 用户分享后，B 用户评论并 @A，A 的通知中心出现未读并可跳转。


- [x] 10. 端到端质量收尾：E2E 全覆盖 + XSS/CSRF 回归 + 视觉回归（青绿/暗色 + CN/EN）

  **What to do**:
  - Playwright 用例覆盖（最小集合）：
    - 登录/退出
    - 笔记 CRUD + 编辑器模式切换 + conflict 提示
    - Todo 重复任务 + 日历 occurrences
    - 搜索 + 标签
    - 分享页打开 + 评论/批注 + 举报/折叠 + 附件
    - CN/EN 切换（含日期显示）
    - 暗色模式
    - 非 admin 访问用户端 admin route → 自动跳首页；admin 可进入
  - 安全回归：
    - 评论与 markdown 渲染的 stored-XSS（注入 `javascript:`、`<img onerror>` 等）应被清洗/拦截。
    - Cookie auth + CSRF 验证覆盖。
  - 视觉回归：关键页截图对比（light/dark + CN/EN）。

  **Recommended Agent Profile**:
  - Category: `unspecified-high`
  - Skills: `playwright`

  **Parallelization**:
  - Can Run In Parallel: NO
  - Parallel Group: Wave 3 (final)
  - Blocks: None
  - Blocked By: 5, 6, 7, 8, 9

  **References**:
  - `tests/test_api_v2_notes_crud.py` - conflict 行为与 server_snapshot。
  - `tests/test_sharing.py` - public share 行为边界。
  - `README.md` - todo occurrences 协议与 tzid 约定。

  **Acceptance Criteria**:
  - [x] `uv sync --extra dev && uv run pytest` → PASS。
  - [x] `npx playwright test` → PASS。
  - [x] 生成证据截图目录：`.sisyphus/evidence/`（至少 10 张关键页截图，含 light/dark + CN/EN）。

---

## Commit Strategy

> 执行阶段由 Sisyphus 负责实际提交；这里定义推荐拆分点，避免一次提交过大。

| After Task | Message (Conventional Commits, 中文优先) | Verification |
|---|---|---|
| 2 | `feat(web): 初始化用户端前端骨架与E2E基座` | `npx playwright test` |
| 4 | `feat(auth): 增加cookie会话鉴权与CSRF防护` | `uv run pytest` |
| 5 | `feat(notes): 增加笔记前端与编辑器(Markdown真源)` | `npx playwright test` |
| 6 | `feat(todo): GTD+重复任务occurrences+日历视图` | `npx playwright test` |
| 8 | `feat(collab): 分享页评论/批注/治理能力` | `uv run pytest && npx playwright test` |
| 9 | `feat(notify): 站内通知中心` | `uv run pytest && npx playwright test` |
| 10 | `test(e2e): 补齐端到端与安全回归用例` | `uv run pytest && npx playwright test` |

---

## Defaults Applied（可随时改，但先按此落地）

- Captcha Provider：先做“可插拔”，先不绑定具体厂商；以“限流+审核+举报/折叠”先跑通闭环，并保留验证码接口（未来可接腾讯/极验等）。
- 时区与周起始：
  - Todo recurrence 按后端约定 `tzid=Asia/Shanghai` 处理。
  - UI 展示按当前 locale 选择周起始（CN: Monday, EN-US: Sunday）。
- 匿名评论身份：默认要求 `display_name`（可选），并用 cookie 保存匿名会话标识。
- 附件策略（评论/笔记）：默认限制图片/文本/pdf，大小上限沿用后端现有 attachments 限制（参考 `tests/test_attachments.py`）。
- 搜索范围：默认只搜 notes + todos，不搜 comments。

---

## Decisions Needed

- 无（已确认：验证码先做可插拔；admin 权威来源为 `User.is_admin`）。
