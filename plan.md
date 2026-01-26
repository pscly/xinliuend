# 项目规划文档：心流云服务 (Flow Cloud)

**版本**: v1.0 (Auth Only)
**目标**: 构建 App 专属后端，接管用户注册/登录流程，自动对接 Memos 实例，并提供 Admin 管理面板以供 N8N 自动化集成。

---

## 1. 架构设计 (System Architecture)

我们需要明确三者的关系：

*. **Android App**: 客户端。
*. **Flow Backend (flow-backend.example.com)** : 你的 FastAPI 后端，负责处理注册逻辑、管理用户映射、提供 Admin 面板。
*. **Memos Server (memos.example.com)** : 实际存储数据的服务器。

### 核心交互流程：

- **App 只是去 Backend 拿“钥匙”** ：App 登录时，请求 Backend。Backend 验证通过后，把 Memos 的 Access Token 和 Server URL 给 App。
- **App 直接回家存数据**：App 拿到 Token 后，后续所有的记笔记、传图片、拉取列表，**直接连接 Memos Server**，不经过 Backend。

  - 优点：减轻 Backend 压力，减少延迟，App 原有的同步逻辑几乎不用改。

---

## 2. 后端开发规划 (Flow Backend)

**技术栈**: Python 3.11+, FastAPI, SQLModel (基于 SQLAlchemy), PostgreSQL, Jinja2 (模板), TailwindCSS (CDN, 用于前端美化).

### 2.1 数据库设计 (PostgreSQL)

我们需要一张核心表 users。

>  **⚠️ 安全警告**：作为专业规划，我**绝对禁止**你明文存储用户密码。这在法律和道德上都是巨大的风险。
> **解决方案**：为了满足你“N8N 自动化”的需求，你需要的是 **Memos 的 Token**，而不是用户的登录密码。我们将明文存储 Token（或可逆加密），密码必须 Hash 处理。

**Table: users**

| 字段名            | 类型            | 说明                                    |
| ------------------- | ----------------- | ----------------------------------------- |
| id                | Integer (PK)    | 后端自增 ID                             |
| username          | String (Unique) | 用户名                                  |
| password\_hash | String          | 经过 bcrypt 后的密码 (App登录Backend用) |
| memos\_id      | Integer         | 对应 Memos 里的用户 ID                  |
| memos\_token   | String          | **关键数据**：Memos 的 API Token (供 N8N 使用)      |
| is\_active     | Boolean         | 封号开关                                |
| created\_at    | DateTime        | 注册时间                                |

### 2.2 环境变量配置 (.env)

Backend 需要拥有 Memos 的管理员权限才能帮别人注册。

### 2.3 API 接口规划

App 只需要两个接口。

#### A. 注册接口 POST /api/v1/auth/register

- **输入**: { "username": "abc", "password": "123" }
- **后端逻辑**:

  *. 检查 users 表是否已存在该用户名。
  *. **调用 Memos Admin API**: 使用 MEMOS\_ADMIN\_TOKEN 向 https://memos.example.com/api/v1/user 发起请求，创建一个同名用户（密码随机生成或与原密码一致，建议后端随机生成一个高强度密码，因为用户不需要知道他在 Memos 的密码，他只用 Token）。
  *. **获取 Token**: 拿到新创建的 Memos 用户 ID，生成该用户的 Access Token (永不过期)。
  *. **入库**: 将 username、password\_hash、memos\_id、memos\_token 存入 PG 数据库。
  *. **返回**: { "code": 200, "data": { "token": "ey...", "server\_url": "https://memos.example.com" } }

#### B. 登录接口 POST /api/v1/auth/login

- **输入**: { "username": "abc", "password": "123" }
- **后端逻辑**:

  *. 查库，校验密码 Hash。
  *. 如果通过，取出数据库里的 memos\_token。
  *. **返回**: { "code": 200, "data": { "token": "ey...", "server\_url": "https://memos.example.com" } }

---

## 3. Admin 管理后台规划 (Web Dashboard)

既然前后端不分离，使用 FastAPI + Jinja2 模板渲染。

**风格**: 极简深色模式 (Dark Mode)，保持“极客+国风”的调性。

### 3.1 页面设计

- **URL**: /admin (需要 HTTP Basic Auth，账号/密码通过环境变量 ADMIN_BASIC_USER/ADMIN_BASIC_PASSWORD 配置)
- **布局**:

  - 左上角：Logo “心流控制台”。
  - 主体：一个漂亮的卡片式表格。
- **表格列**:

  - **ID**: 用户ID
  - **用户名**: Username
  - **Memos关联**: Memos UserID
  - **Token (核心)** : 显示部分 Token，点击按钮  **[复制完整 Token]**  (方便你粘贴到 N8N)。
  - **注册时间**: YYYY-MM-DD
  - **操作**: [禁用] [重置Token]

### 3.2 模板技术建议

使用 **Tailwind CSS** (CDN引入即可，不用 npm build)。

---

## 4. Android 端改造计划

App 端需要做的是“无感切换”。

### 4.1 登录页改造 (LoginActivity)

目前你可能有“输入 URL”和“输入 Token”的框。现在改为两个 Tab：

- **Tab A: 账号登录 (默认)**

  - UI: 只有“账号”和“密码”两个输入框。底部有一个“注册”按钮。
  - 逻辑:

    - 点击登录 -\> 请求 https://flow-backend.example.com/api/v1/auth/login。
    - 成功 -\> 解析返回的 JSON，拿到 token 和 server\_url。
    - **关键动作**: 将这两个值写入 App 的 DataStore (就像用户以前手动输入的一样)。
    - 跳转主页。
- **Tab B: 自定义服务器 (保留功能)**

  - UI: 输入 URL + Token。
  - 逻辑: 保持现状。

### 4.2 注册页开发 (RegisterActivity)

- UI: 账号、密码、确认密码。
- 逻辑: 请求 https://flow-backend.example.com/api/v1/auth/register -\> 成功后自动执行登录逻辑。

---

## 5. N8N 自动化集成思路

你在需求中提到是为了 N8N 自动化标签。

*. **场景**: 用户在 App 发了一条笔记。
*. **N8N Trigger**: N8N 可以通过 Webhook (Memos支持) 或者 定时轮询 (Polling) 监听 Memos 的数据库/API。
*. **Token 的作用**:

- 当你登录 /admin 后台时，复制用户的 **Token**。
- 在 N8N 中，配置 HTTP Request 节点，Header 设置 Authorization: Bearer \<用户Token\>。
- **AI 自动打标**: N8N 读取笔记内容 -\> 发送给 OpenAI/Claude -\> 返回 Tag -\> N8N 调用 Memos API (PATCH /api/v1/memos/{id}) 更新笔记加上 Tag。

---

## 6. 开发注意事项 (给开发人员的 Memo)

请将以下几点转达给后端开发：

*. **Memos 版本兼容性**: Memos 的 API 变动很频繁（v0.18 -\> v0.22 变化很大）。后端在调用 Memos Admin API 创建用户时，务必先在本地用 Postman 调通，确认好当前 memos.example.com 版本对应的创建用户 Payload 格式。
*. **错误处理**: 如果 Memos 创建用户失败（比如 Memos 挂了），后端注册接口必须回滚，不能在 PG 里存了用户结果 Memos 里没号。
*. **Token 有效期**: 确保生成的 Memos Token 是**永久有效**的（Permanent），否则用户过段时间 App 就掉线了。
*. **CORS**: FastAPI 记得配置 CORS，允许你的 App 包名或 \* 访问。
*. **并发锁**: 注册接口建议加一点防抖，防止用户疯狂点击注册按钮导致创建了重复账号。

---

## 7. 总结

**可行性**: 高。
**成本**: 需要额外维护一个轻量级 FastAPI 服务。
**体验**:

- **对用户**: 只需要记一个账号密码，不用管什么 Token、API URL，体验达到商业软件标准。
- **对你 (Admin)** : 拥有所有用户的 Memos Token，可以随心所欲地在后台为他们部署 N8N 自动化流。


