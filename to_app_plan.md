# App 端开发对接文档（to_app_plan.md）

> 目标：把 App 的“手动输入 Memos Server + Token”登录方式升级为“账号密码登录（向 Flow Backend 换钥匙）”，并保留“自定义服务器”入口。
>
> 核心原则：App 只向 Backend 换取 `token + server_url`，拿到后 **直接连接 Memos** 进行同步/写入（不经过 Backend）。

---

## 0. 术语与地址

- **Flow Backend**：你们要对接的中间认证后端（示例：`https://flow-backend.example.com`，以实际配置为准）。
- **Memos Server**：真正存储数据的服务器（示例：`https://memos.example.com`）。
- **Memos Access Token**：Memos API 的 Bearer Token（App 后续请求 Memos 时使用）。

---

## 1. App 端总体改造范围

### 1.1 你们要做的事（必须）

1. 在登录页新增「账号登录」模式：用户名 + 密码 → 调用 Flow Backend 登录 → 获取 `token/server_url` → 写入本地持久化 → 跳转主页。
2. 新增注册页（或登录页内注册）：用户名 + 密码 + 确认密码 → 调用 Flow Backend 注册 → 获取 `token/server_url` → 写入本地持久化 → 跳转主页。
3. 保留旧的「自定义服务器」模式：仍允许用户手动输入 `server_url` + `token`，写入本地持久化后直连 Memos。
4. 所有 Memos API 调用统一从本地持久化读取 `server_url` 与 `token`。

### 1.2 你们不用做的事（明确不做）

- 不需要把笔记/图片通过 Flow Backend 转发。
- 不需要实现 /admin（这是给运维/管理员用的）。

---

## 2. Flow Backend API 规范（App 只用这两个接口）

> 统一响应格式：
>
> ```json
> {"code":200,"data":{...}}
> ```

### 2.1 Base URL

- 建议 App 配置：
  - `FLOW_BACKEND_BASE_URL`（例如 `https://flow-backend.example.com`）
- 生产环境建议固定在配置中（buildConfig / remote config），不要让普通用户随意改。

### 2.2 注册：POST `/api/v1/auth/register`

- **用途**：创建 App 用户 + 在 Memos 创建同名用户 + 为该用户签发 Memos Token。

**请求**

```http
POST {FLOW_BACKEND_BASE_URL}/api/v1/auth/register
Content-Type: application/json

{"username":"abc123","password":"123456"}
```

**字段约束（非常重要）**

- `username`：仅允许 **字母 + 数字**，不支持下划线、短横线、中文（例：`abc123` ✅，`abc_123` ❌）。
- `password`：至少 6 位；建议限制为 **最多 71 字节（UTF-8）**（后端会在与 Memos 交互时自动在尾部追加 `x`，为避免 bcrypt 72 字节截断导致追加无效）。

**成功响应**

```json
{
  "code": 200,
  "data": {
    "token": "<memos_access_token>",
    "server_url": "https://memos.example.com"
  }
}
```

**失败响应（常见）**

- `409`：用户名已存在（Flow Backend 侧已存在该用户名）。
- `400`：参数校验失败（用户名不合法、密码过短/过长等）。
- `502`：后端对接 Memos 失败（Memos 网络/权限/接口变动）。

App 建议提示：
- `409` → “用户名已存在，请直接登录”
- `400` → “请检查用户名/密码格式”
- `502` → “服务暂不可用，请稍后重试”

### 2.3 登录：POST `/api/v1/auth/login`

- **用途**：验证 App 用户密码（Flow Backend 内部 hash 校验）并返回对应的 Memos Token。

**请求**

```http
POST {FLOW_BACKEND_BASE_URL}/api/v1/auth/login
Content-Type: application/json

{"username":"abc123","password":"123456"}
```

**成功响应**

```json
{
  "code": 200,
  "data": {
    "token": "<memos_access_token>",
    "server_url": "https://memos.example.com"
  }
}
```

**失败响应（常见）**

- `401`：用户名或密码错误。
- `403`：账号已被禁用（管理员在 /admin 禁用）。

App 建议提示：
- `401` → “用户名或密码错误”
- `403` → “账号已被禁用，请联系管理员”

---

## 3. App 本地持久化（DataStore/SharedPreferences）

### 3.1 推荐存储键（示例）

- `memos_server_url`：`https://memos.example.com`
- `memos_access_token`：Memos token
- `login_mode`：`backend` / `custom`

> 关键点：无论来自「账号登录」还是「自定义服务器」，最终都要落在同一套 `memos_server_url + memos_access_token` 上，保证后续业务代码不分叉。

### 3.2 旧用户迁移建议

- 如果用户已在旧版本手动配置过 `server_url/token`：
  - 默认仍可直接使用（保持兼容）。
  - 但在登录页明确推荐“账号登录”。

### 3.3 退出登录

- 清空 `memos_access_token`（以及可选清空 `memos_server_url`）。
- 跳转到登录页。

---

## 4. UI/交互方案（建议实现方式）

### 4.1 LoginActivity / LoginPage

使用 Tab 或 SegmentedControl：

- Tab A：**账号登录（默认）**
  - 输入：用户名、密码
  - 按钮：登录、去注册
  - 点击登录：
    1) 参数校验
    2) 调用 `POST /api/v1/auth/login`
    3) 成功写入 `memos_server_url/memos_access_token`
    4) 进入主页并触发同步

- Tab B：**自定义服务器（保留）**
  - 输入：server_url、token
  - 点击保存：写入 `memos_server_url/memos_access_token` → 进入主页

交互细节：
- 登录/注册请求期间按钮置灰，显示加载。
- 防止重复点击（至少 1~2 秒节流）。
- 错误提示以用户可理解语言展示（不要直接弹出后端 detail 原文）。

### 4.2 RegisterActivity / RegisterPage

- 输入：用户名、密码、确认密码
- 校验：
  - 用户名仅字母数字
  - 密码 >= 6
  - 密码与确认密码一致
  - 建议：密码 UTF-8 字节数 <= 71（后端会在与 Memos 交互时自动追加 `x`）
- 点击注册：
  - 调用 `POST /api/v1/auth/register`
  - 成功后与登录一致：写入本地持久化 → 进入主页

---

## 5. 网络层实现建议（Android）

### 5.1 Flow Backend Client

- 使用 Retrofit/OkHttp（或你们现有网络栈）。
- 两个接口定义：
  - `register(username, password)`
  - `login(username, password)`
- 统一处理非 2xx：
  - 读取 `HTTP status code`
  - 尝试解析 JSON（可能是 `{detail:...}`）
  - 映射成 UI 友好文案

### 5.2 Memos Client（复用原有逻辑）

- 你们原先调用 Memos 的方式大概率是：
  - Base URL = 用户输入
  - Authorization = Bearer token

现在只要把“来源”改为 DataStore：

- Base URL：读 `memos_server_url`
- Token：读 `memos_access_token`

并确保：
- 当 token 变更（登录/注册/重置后）能刷新 OkHttp Interceptor 或重建 Retrofit 实例。

---

## 6. 常见问题与处理策略

### 6.1 为什么 Memos 后台能看到账号，但 App 拿不到 token？

- 已在后端修复：当前 Memos（`memos.example.com`）管理员无权为其他用户直接创建 token，后端会改为“以用户身份创建 token”。
- 如果你们仍遇到 502：优先让后端同学查看服务日志，并确认 `.env` 配置正确。

### 6.2 token 失效/被重置怎么办？

- Memos API 若返回 401/403：
  - 提示用户重新登录（账号密码）
  - 或让用户重新走自定义服务器

### 6.3 用户名格式问题

- 若用户输入 `abc_123` 这类带下划线：直接在 App 侧提示不支持。

---

## 7. 联调与验收清单（给 QA/自测）

1. 新用户注册：注册成功 → 自动进入主页 → 能拉取/创建 memo。
2. 老用户登录：登录成功 → 能同步。
3. 禁用用户：后台禁用后，App 登录应返回 403 并提示“账号已禁用”。
4. 自定义服务器：输入 server_url+token 能正常使用。
5. 退出登录：清空 token 后进入登录页；再次登录正常。
6. 异常网络：断网/超时能给出可理解提示；不会卡死。

---

## 8. 开发注意事项（强烈建议）

- 不要在日志里打印 token。
- 确保所有请求走 HTTPS。
- 注册/登录按钮加防抖；后端创建用户+token会有一定耗时。
- 统一在一处封装“写入 DataStore + 刷新 Memos Client + 跳转主页”的逻辑，避免多处复制。

---

## 9. 给后端同学的对接信息（App 端可转述）

- 账号/密码登录只走 Flow Backend。
- App 真正访问数据走 Memos：Header `Authorization: Bearer <token>`。
- 用户名：只允许字母数字。

---

## 10. 后端结构化数据（设置/TODO）对接（新增）

说明：
- 这部分数据存储在 Flow Backend（不在 Memos）。
- 鉴权继续复用后端登录返回的 token（即 memos_token）。
- Header：Authorization: Bearer <token>

10.1 Settings
- GET    /api/v1/settings
- PUT    /api/v1/settings/{key}
- DELETE /api/v1/settings/{key}

10.2 TODO（列表/条目/单次例外）
- Lists: GET/POST/PATCH/DELETE /api/v1/todo/lists ...
- Items: GET/POST/PATCH/DELETE /api/v1/todo/items ...
- Occurrence: 用于重复任务的单次完成/跳过/延期：/api/v1/todo/occurrences

10.3 离线/多端同步（推荐使用 sync 接口）
- GET  /api/v1/sync/pull?cursor=0&limit=200
- POST /api/v1/sync/push

同步约定：
- 客户端维护 cursor（首次为 0），pull 返回 next_cursor；后续继续用 next_cursor 增量拉取。
- push 以批量 mutations 提交变更；每条 mutation 带 client_updated_at_ms（设备当前时间毫秒）。
- 冲突策略 LWW：client_updated_at_ms 更大的写入获胜；服务端会对过于超前的时间做钳制。

10.4 RRULE（重复任务）
- tzid 固定 Asia/Shanghai
- dtstart_local / recurrence_id_local 固定格式 YYYY-MM-DDTHH:mm:ss（无 offset）
- 客户端负责展开 RRULE；后端不展开。单次例外通过 occurrences 表达并同步。
