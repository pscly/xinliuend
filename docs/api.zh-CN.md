# Flow Backend API 文档（v1 + v2）

最后更新：2026-02-01

本文件面向 APK / Web 客户端开发团队，覆盖：鉴权、请求头约定、错误格式、同步协议、以及所有已实现的 v1/v2 接口。

## 1. 基本信息

- 服务默认监听：`http://localhost:31031`
- v1 Base Path：`/api/v1`（由 `API_PREFIX` 控制；默认值见 `src/flow_backend/config.py`）
- v2 Base Path：`/api/v2`（作为子应用 mount 到主应用，拥有独立 OpenAPI）

OpenAPI / Swagger UI：

- v1（主应用）：
  - `GET /openapi.json`
  - `GET /docs`
  - `GET /redoc`
- v2（子应用）：
  - `GET /api/v2/openapi.json`
  - `GET /api/v2/docs`
  - `GET /api/v2/redoc`

健康检查：

- `GET /health`（主应用）
- `GET /api/v2/health`（v2 子应用）

## 2. 鉴权与通用请求头

### 2.1 Bearer Token

除注册/登录及公开分享接口外，均需要 Bearer Token：

```
Authorization: Bearer <memos_token>
```

Token 来自：

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`

### 2.2 Request ID

服务端支持并返回 `X-Request-Id`：

- 客户端可传入：`X-Request-Id: <any non-empty string>`
- 若未传入，服务端会生成 UUID
- 服务端总会在响应头返回：`X-Request-Id: ...`

v2 的错误响应会尽量带上 `request_id` 字段（来自 `request.state.request_id`）。

### 2.3 设备信息（可选，但建议客户端都带上）

用于设备/IP 活跃度跟踪（管理后台用途）。对业务无强依赖。

设备 ID/名称（服务端会接受多种 header 名称以减少对接摩擦）：

- 设备 ID：`X-Flow-Device-Id` 或 `X-Device-Id`
- 设备名称：`X-Flow-Device-Name` 或 `X-Device-Name`

客户端 IP：

- 默认使用直连 IP（`request.client.host`）
- 若启用 `TRUST_X_FORWARDED_FOR=true`，则使用 `X-Forwarded-For` 的第一个地址作为 client IP（仅建议在可信反代后启用）

### 2.4 Content-Type

- JSON 请求体：`Content-Type: application/json`
- 文件上传：`multipart/form-data`（见 v2 attachments）

## 3. 时间与并发冲突（非常重要）

### 3.1 `client_updated_at_ms`

大部分写入接口都使用 `client_updated_at_ms` 进行 LWW（Last-Write-Wins）并发控制：

- 数值越大，越“新”
- 若客户端时间明显超前，服务端会做一定钳制（见 `src/flow_backend/sync_utils.py`）

### 3.2 v1 的本地时间字符串（TODO / RRULE）

v1 TODO 相关字段使用“本地时间字符串”格式：

- 格式固定：`YYYY-MM-DDTHH:mm:ss`（长度 19，无时区 offset）
- 字段示例：`2026-02-01T10:00:00`

该格式校验实现见：`src/flow_backend/validators.py`

### 3.3 tzid 约定

- v1 TODO：服务端强制 `tzid = "Asia/Shanghai"`（无论请求传什么）
- v2 TODO：支持传 `tzid`，若为空则使用 `DEFAULT_TZID`（默认 `Asia/Shanghai`）

### 3.4 冲突的表现形式

v1：

- 大多数错误遵循 FastAPI 默认：
  - `{"detail": "..."}` 或 `{"detail": {...}}`
- 部分冲突会返回 `detail` 为对象，并包含 `server_snapshot`（例如 v2 的同款结构在 v1 services 中也会出现）

v2：

- 统一错误格式（见 4.2）：
  - `ErrorResponse { error, message, request_id?, details? }`
- 冲突（HTTP 409）通常表现为：
  - `error = "conflict"`
  - `details.server_snapshot` 带服务端快照

v2 同步（/api/v2/sync/push）额外注意：

- 若服务端记录已被软删除（tombstone），sync upsert 会被拒绝为 conflict
- 需要显式调用 restore 接口恢复：
  - `POST /api/v2/notes/{note_id}/restore`
  - `POST /api/v2/todo/items/{item_id}/restore`

## 4. 响应格式

### 4.1 v1 成功响应（统一 envelope）

v1 成功返回：

```json
{"code":200,"data":{}}
```

v1 的 data 具体结构随接口而变。

### 4.2 v2 错误响应（Pinned Contract）

v2 对 `HTTPException` / 参数校验 / 未处理异常使用统一错误结构：

```json
{
  "error": "conflict",
  "message": "conflict",
  "request_id": "...",
  "details": {
    "server_snapshot": {
      "id": "..."
    }
  }
}
```

- `error`：基于 HTTP status 映射（400/401/403/404/409/410/429/502 等；其它为 `http_<code>`）
- `message`：人类可读提示
- `details`：可选；常用于 422 校验错误或 409 冲突快照

定义见：`src/flow_backend/v2/schemas/errors.py`

## 5. v1 接口（/api/v1）

### 5.1 Auth

#### POST /api/v1/auth/register

请求体：`RegisterRequest`（`src/flow_backend/schemas.py`）

```json
{"username":"alice","password":"secret123"}
```

成功：

```json
{"code":200,"data":{"token":"...","server_url":"https://memos.example.com"}}
```

常见错误：

- 409 `{"detail":"username already exists"}`
- 400 `{"detail":"..."}`（密码过长等）
- 502 `{"detail":"..."}`（对接 Memos 失败）

说明：注册/登录阶段也会 best-effort 记录设备/IP（不会影响返回）。

#### POST /api/v1/auth/login

请求体：`LoginRequest`

```json
{"username":"alice","password":"secret123"}
```

成功：同 register。

常见错误：

- 401 `{"detail":"invalid credentials"}`
- 403 `{"detail":"user disabled"}`
- 409 `{"detail":"memos token not set; contact admin"}`

### 5.2 Settings

鉴权：需要 Bearer Token。

#### GET /api/v1/settings

成功：

```json
{
  "code": 200,
  "data": {
    "items": [
      {
        "key": "ui.theme",
        "value_json": {"mode": "dark"},
        "client_updated_at_ms": 1700000000000,
        "updated_at": "2026-02-01T00:00:00Z"
      }
    ]
  }
}
```

#### PUT /api/v1/settings/{key}

请求体：`SettingUpsertRequest`（`src/flow_backend/schemas_settings.py`）

```json
{"value_json": {"mode": "dark"}, "client_updated_at_ms": 1700000000000}
```

冲突：409 `{"detail":"conflict (stale update)"}`

#### DELETE /api/v1/settings/{key}

请求体：`SettingDeleteRequest`

```json
{"client_updated_at_ms": 1700000000000}
```

冲突：409 `{"detail":"conflict (stale delete)"}`

### 5.3 TODO Lists

鉴权：需要 Bearer Token。

#### GET /api/v1/todo/lists

Query：

- `include_archived`（bool，默认 false）

返回：`items[]`（每项包含 id/name/color/sort_order/archived/client_updated_at_ms/updated_at）

#### POST /api/v1/todo/lists

请求体：`TodoListUpsertRequest`（`src/flow_backend/schemas_todo.py`）

- `id` 为空则服务端生成
- 冲突：409 `{"detail":"conflict (stale update)"}`

成功：

```json
{"code":200,"data":{"id":"..."}}
```

#### PATCH /api/v1/todo/lists/{list_id}

请求体：`TodoListPatchRequest`

成功：`{"code":200,"data":{"ok":true}}`

#### DELETE /api/v1/todo/lists/{list_id}

Query：

- `client_updated_at_ms`（int，默认 0）

说明：若 list 不存在，仍返回 ok。

#### POST /api/v1/todo/lists/reorder

请求体：`TodoListReorderItem[]`

```json
[
  {"id":"...","sort_order":10,"client_updated_at_ms":1700000000000}
]
```

### 5.4 TODO Items

鉴权：需要 Bearer Token。

#### GET /api/v1/todo/items

Query：

- `list_id`（可选）
- `status`（可选；实际参数名为 `status`，代码里 alias 到 `status_value`）
- `tag`（可选；在 SQLite 下使用 `json_each(todo_items.tags_json)` 过滤）
- `include_archived_lists`（bool，默认 false；默认只返回未归档 list 下的 item）
- `include_deleted`（bool，默认 false）
- `limit`（默认 200）
- `offset`（默认 0）

返回字段（每项）：

- `id`, `list_id`, `parent_id`
- `title`, `note`
- `status`, `priority`
- `due_at_local`, `completed_at_local`
- `sort_order`, `tags`
- `is_recurring`, `rrule`, `dtstart_local`, `tzid`
- `reminders`
- `client_updated_at_ms`, `updated_at`, `deleted_at`

#### POST /api/v1/todo/items

请求体：`TodoItemUpsertRequest`

重要：v1 服务端会强制 `tzid = "Asia/Shanghai"`。

成功：`{"code":200,"data":{"id":"..."}}`

#### POST /api/v1/todo/items/bulk

请求体：`TodoItemUpsertRequest[]`

成功：`{"code":200,"data":{"ids":["...","..."]}}`

#### PATCH /api/v1/todo/items/{item_id}

请求体：`TodoItemPatchRequest`

重要：即使传 `tzid`，服务端也会强制 `Asia/Shanghai`。

#### DELETE /api/v1/todo/items/{item_id}

Query：`client_updated_at_ms`（默认 0）

说明：若 item 不存在，仍返回 ok。

### 5.5 RRULE Occurrences

鉴权：需要 Bearer Token。

#### GET /api/v1/todo/occurrences

Query：

- `item_id`（必填）
- `from`（可选，本地时间字符串）
- `to`（可选，本地时间字符串）

#### POST /api/v1/todo/occurrences

请求体：`TodoItemOccurrenceUpsertRequest`

说明：若 payload 不带 `id`，服务端会按唯一键（item_id + tzid + recurrence_id_local）尝试去重。

#### POST /api/v1/todo/occurrences/bulk

请求体：`TodoItemOccurrenceUpsertRequest[]`

#### DELETE /api/v1/todo/occurrences/{occurrence_id}

Query：`client_updated_at_ms`（默认 0）

说明：occurrence 不存在会返回 404。

### 5.6 Sync（v1）

鉴权：需要 Bearer Token。

#### GET /api/v1/sync/pull

Query：

- `cursor`（默认 0）
- `limit`（默认 `SYNC_PULL_LIMIT`，上限 1000）

响应：

```json
{
  "code": 200,
  "data": {
    "cursor": 0,
    "next_cursor": 123,
    "has_more": false,
    "changes": {
      "user_settings": [],
      "todo_lists": [],
      "todo_items": [],
      "todo_occurrences": []
    }
  }
}
```

说明：changes 中包含软删除对象（通过 `deleted_at` 判断）。

#### POST /api/v1/sync/push

请求体：`SyncPushRequest`（`src/flow_backend/schemas_sync.py`）

```json
{
  "mutations": [
    {
      "resource": "todo_item",
      "op": "upsert",
      "entity_id": "...",
      "client_updated_at_ms": 1700000000000,
      "data": {"list_id":"...","title":"...","tags":[]}
    }
  ]
}
```

资源类型（固定）：

- `user_setting`
- `todo_list`
- `todo_item`
- `todo_occurrence`

op（固定）：

- `upsert`
- `delete`

返回：

```json
{
  "code": 200,
  "data": {
    "cursor": 123,
    "applied": [{"resource":"todo_item","entity_id":"..."}],
    "rejected": [
      {
        "resource": "todo_item",
        "entity_id": "...",
        "reason": "conflict",
        "server": {"id":"...","client_updated_at_ms":1700000000001}
      }
    ]
  }
}
```

注意：

- v1 sync 里的 todo_item / todo_occurrence 同样会强制 `tzid = "Asia/Shanghai"`
- delete 在服务端不存在时是幂等成功（会出现在 applied 中）

v1 sync `data` 字段约定（按服务端实际读取的 key）：

- `resource=user_setting, op=upsert`
  - `data.value_json`：对象（缺省视为 `{}`）
- `resource=todo_list, op=upsert`
  - `data.name`：字符串（缺省可能被服务端补为旧值/"tmp"）
  - `data.color`：字符串或 null
  - `data.sort_order`：整数（缺省视为 0）
  - `data.archived`：布尔（缺省视为 false）
- `resource=todo_item, op=upsert`
  - 必须：`data.list_id`
  - 建议总是带齐（服务端会覆盖）：
    - `parent_id`, `title`, `note`, `status`, `priority`
    - `due_at_local`, `completed_at_local`, `sort_order`
    - `tags`（数组）
    - `is_recurring`, `rrule`, `dtstart_local`
    - `reminders`（数组；元素结构由客户端自定义）
- `resource=todo_occurrence, op=upsert`
  - 必须：`data.item_id`, `data.recurrence_id_local`
  - 可选：`status_override`, `title_override`, `note_override`, `due_at_override_local`, `completed_at_local`

删除（op=delete）时，服务端不会读取 data。

### 5.7 Admin（内部管理后台，HTML）

这些接口是管理后台页面/表单提交使用，通常不需要在 App/Web 客户端对接（除非你要做运维工具）。

- `GET /admin`：后台首页（未登录会 303 跳转到 `/admin/login`）
- `GET /admin/login`：登录页
- `POST /admin/login`：提交登录（form fields: `username`, `password`, `next`）
- `POST /admin/logout`：登出

登录态通过 Cookie（`ADMIN_SESSION_COOKIE_NAME`，默认 `flow_admin_session`）维持，且仅作用于 `/admin` path。

## 6. v2 接口（/api/v2）

### 6.1 Health

#### GET /api/v2/health

```json
{"ok":true}
```

### 6.2 Notes

鉴权：需要 Bearer Token。

#### POST /api/v2/notes

请求体：`NoteCreateRequest`（`src/flow_backend/v2/schemas/notes.py`）

```json
{"id":null,"title":null,"body_md":"# Hello","tags":["work"],"client_updated_at_ms":1700000000000}
```

成功：201，返回 `Note`。

#### GET /api/v2/notes

Query：

- `limit`（1..500，默认 200）
- `offset`（>=0，默认 0）
- `tag`（可选；按标签过滤，大小写不敏感）
- `q`（可选；全文检索/模糊检索）
- `include_deleted`（bool，默认 false）

搜索语义：

- SQLite：使用 FTS5（`notes_fts MATCH :q`），并且**索引层面排除 deleted notes**（即使 `include_deleted=true`，带 q 的搜索也只会返回未删除笔记）
- 非 SQLite：退化为 title/body 的 ILIKE 子串匹配

#### GET /api/v2/notes/{note_id}

Query：

- `include_deleted`（bool，默认 false）

#### PATCH /api/v2/notes/{note_id}

请求体：`NotePatchRequest`

- 必须提供 `client_updated_at_ms`
- `title/body_md/tags` 至少提供一个

冲突：409（`details.server_snapshot` 包含服务端快照）

#### DELETE /api/v2/notes/{note_id}

Query：

- `client_updated_at_ms`（>=0）

成功：204（无 body）

#### POST /api/v2/notes/{note_id}/restore

请求体：`NoteRestoreRequest`：

```json
{"client_updated_at_ms":1700000000000}
```

### 6.3 Note Revisions

鉴权：需要 Bearer Token。

#### GET /api/v2/notes/{note_id}/revisions

Query：

- `limit`（1..500，默认 100）

返回：`NoteRevisionList`（每项包含 `kind`/`reason`/`snapshot`）

#### POST /api/v2/notes/{note_id}/revisions/{revision_id}/restore

请求体：`NoteRevisionRestoreRequest`：

```json
{"client_updated_at_ms":1700000000000}
```

### 6.4 Attachments

鉴权：需要 Bearer Token。

#### POST /api/v2/notes/{note_id}/attachments

请求体：`multipart/form-data`

- form field: `file`（必须）

成功：201，返回 `Attachment`：

```json
{
  "id": "...",
  "note_id": "...",
  "filename": "a.png",
  "content_type": "image/png",
  "size_bytes": 123,
  "storage_key": "...",
  "created_at": "..."
}
```

#### GET /api/v2/attachments/{attachment_id}

返回文件 bytes（Content-Disposition 为 attachment；LocalStorage 会直接走文件响应）。

### 6.5 Shares（鉴权）

#### POST /api/v2/notes/{note_id}/shares

请求体：`ShareCreateRequest`

```json
{"expires_in_seconds": 3600}
```

成功：201，返回：

```json
{"share_id":"...","share_url":"http://.../api/v2/public/shares/<token>","share_token":"<token>"}
```

#### DELETE /api/v2/shares/{share_id}

成功：204。

### 6.6 Public Shares（匿名）

这些接口无需 Bearer Token。

#### GET /api/v2/public/shares/{share_token}

返回：

```json
{
  "note": {"id":"...","title":"...","body_md":"...","tags":[],"client_updated_at_ms":1,"created_at":"...","updated_at":"...","deleted_at":null},
  "attachments": [{"id":"...","filename":"a.png","content_type":"image/png","size_bytes":123}]
}
```

注意：

- share 被撤销时会返回 404（不泄露存在性）
- share 过期返回 410

#### GET /api/v2/public/shares/{share_token}/attachments/{attachment_id}

返回附件 bytes。

### 6.7 TODO Items（v2，lite）

鉴权：需要 Bearer Token。

#### GET /api/v2/todo/items

Query：

- `limit`（1..500，默认 200）
- `offset`（>=0，默认 0）
- `list_id`（可选）
- `status`（可选）
- `tag`（可选；SQLite 使用 json_each 过滤；Postgres JSONB contains best-effort）
- `include_archived_lists`（bool，默认 false）
- `include_deleted`（bool，默认 false）

返回：`TodoItemList { items, total, limit, offset }`

备注：v2 的 TodoItem 响应模型是 lite 版本（不返回 `status/priority/due_at_local/...` 等 v1 字段），
但 list 接口仍保留了 `status` 过滤参数（服务端会按 DB 字段过滤）。

#### POST /api/v2/todo/items

请求体：`TodoItemCreateRequest`

```json
{"id":null,"list_id":"...","title":"Buy milk","tags":["errand"],"tzid":"Asia/Shanghai","client_updated_at_ms":1700000000000}
```

成功：201，返回 `TodoItem`。

#### PATCH /api/v2/todo/items/{item_id}

请求体：`TodoItemPatchRequest`

- 至少提供一个字段（list_id/title/tags/tzid）
- 冲突：409（`details.server_snapshot`）

#### DELETE /api/v2/todo/items/{item_id}

Query：

- `client_updated_at_ms`（>=0）

成功：204。

#### POST /api/v2/todo/items/{item_id}/restore

请求体：`TodoItemRestoreRequest`

```json
{"client_updated_at_ms":1700000000000}
```

### 6.8 Sync（v2）

鉴权：需要 Bearer Token。

#### GET /api/v2/sync/pull

Query：

- `cursor`（>=0，默认 0）
- `limit`（1..500，默认 200）

返回：`SyncPullResponse { cursor, next_cursor, has_more, changes: { notes, todo_items } }`

#### POST /api/v2/sync/push

请求体：`SyncPushRequest`（`src/flow_backend/v2/schemas/sync.py`）

```json
{
  "mutations": [
    {
      "resource": "note",
      "entity_id": "...",
      "op": "upsert",
      "client_updated_at_ms": 1700000000000,
      "data": {"body_md":"...","title":"...","tags":["a","b"]}
    }
  ]
}
```

支持的 resource/op：

- resource：`note` | `todo_item`
- op：`upsert` | `delete`

重要约定（按当前实现）：

- `client_updated_at_ms` 必须 > 0，否则 rejected: `invalid client_updated_at_ms`
- `note` 创建必须带 `body_md`
- `todo_item` 创建必须带 `list_id`
- 若服务端实体已被软删除，sync upsert 会 conflict（需要显式 restore）
- note sync upsert 时，服务端会调用 `set_note_tags(...)`，因此建议客户端每次 upsert 都传完整 tags 列表

v2 sync `data` 字段约定（按服务端实际行为）：

- `resource=note, op=upsert`
  - 创建必须：`data.body_md`
  - 更新可选：`data.title`, `data.body_md`
  - tags：建议总是传 `data.tags`（数组）。在当前实现中，如果 data 未包含 tags，服务端会将 tags 视为 `[]` 并覆盖。
- `resource=todo_item, op=upsert`
  - 创建必须：`data.list_id`
  - 可选：`data.title`, `data.tags`（数组）, `data.tzid`
  - `tzid` 为空/缺省时，服务端会使用 `DEFAULT_TZID`

删除（op=delete）时，服务端不会读取 data。

返回：

```json
{
  "cursor": 123,
  "applied": [{"resource":"note","entity_id":"..."}],
  "rejected": [{"resource":"note","entity_id":"...","reason":"conflict","server":{...}}]
}
```

### 6.9 Debug（仅非生产环境）

#### POST /api/v2/debug/tx-fail

用途：验证事务回滚；不要在客户端正式使用。

## 7. 客户端对接工作流建议

### 7.1 登录与 Token 管理

1) 首次启动（无 token）：

- 调用 `POST /api/v1/auth/register` 或 `POST /api/v1/auth/login`
- 保存返回的 `token`（建议安全存储）

2) 后续请求：

- 统一加 `Authorization: Bearer <token>`
- 建议每个请求都加 `X-Request-Id`（客户端生成 UUID），便于排障
- 建议每个请求都加设备头：`X-Flow-Device-Id` + `X-Flow-Device-Name`

### 7.2 v1 Sync（适用于 Settings + 完整 TODO）

推荐的增量同步循环：

1) 初次拉取：`GET /api/v1/sync/pull?cursor=0&limit=200`
2) 应用 `changes`：

- 对每个资源按 `entity_id` upsert 本地记录
- 若 `deleted_at != null`，将本地标记为删除（tombstone）

3) 本地有改动时：

- 组装 mutations（包含 `resource/op/entity_id/client_updated_at_ms/data`）
- `POST /api/v1/sync/push`
- 对 `rejected`：若 `reason=conflict` 且带 `server`，客户端应提示用户或做自动合并，再以更大的 `client_updated_at_ms` 重试

4) 继续拉取：用上次的 `next_cursor` 作为新 cursor。

### 7.3 v2 Sync（适用于 Notes + v2 lite TODO）

v2 sync 的差异点：

- 资源只有 `note` 与 `todo_item`
- tombstone 恢复必须走 restore 接口（sync upsert 会 conflict）
- note sync upsert 建议总是带完整 tags

### 7.4 分享与附件

- 创建分享：`POST /api/v2/notes/{note_id}/shares` -> 保存 `share_url`（可直接对外）
- 匿名读取：客户端打开 `share_url` 调 `GET /api/v2/public/shares/{share_token}` 获取 note + attachments 列表
- 匿名下载附件：`GET /api/v2/public/shares/{share_token}/attachments/{attachment_id}`
- 私有下载附件：`GET /api/v2/attachments/{attachment_id}`（需要 Bearer Token）

## 8. 导入到 Apifox / Postman / Swagger

- 推荐直接导入 OpenAPI JSON：
  - v1：`GET /openapi.json`
  - v2：`GET /api/v2/openapi.json`

如果你需要把文档交付给外部团队（离线），可让运维在目标环境执行：

```bash
curl -sS http://<host>:31031/openapi.json > openapi-v1.json
curl -sS http://<host>:31031/api/v2/openapi.json > openapi-v2.json
```
