# 锦囊/Collections 接口文档（APK 对接版）

最后更新：2026-02-13

> 本文聚焦“锦囊/Collections（结构层）”新能力：**可嵌套文件夹 + 笔记引用（note_ref）**。
>
> 适用人群：APK（Android）开发同学。
> - 如果你们是**离线优先**（多端同步），优先看第 4 章（Sync）。
> - 如果你们是**在线直连**，看第 3 章（管理接口）。

---

## 0. 背景与定位

Collections 只存“结构与引用元数据”，不存笔记正文。

- ✅ 支持：无限层级（parent_id）、混排（folder + note_ref）、排序（sort_order）、配色（color）、软删除（deleted_at tombstone）、LWW 冲突（client_updated_at_ms）。
- ❌ 不做：全文搜索、分享/公开、协作 ACL、笔记内容镜像。

---

## 1. 统一约定（强烈建议先读）

### 1.1 Base URL

对外仅保留 `/api/v1/*`：

- Base: `{ORIGIN}/api/v1`
- 本地示例：`http://localhost:31031/api/v1`

### 1.2 鉴权方式

服务端支持两种鉴权（APK 一般使用 Bearer）：

1) **Bearer Token（推荐给 APK）**

- Header：`Authorization: Bearer <token>`

2) **Cookie Session（Web SPA） + CSRF**

- Cookie 名默认：`flow_session`
- 写请求（POST/PUT/PATCH/DELETE）需要 CSRF header（默认 `X-CSRF-Token`）

### 1.3 统一错误返回：`ErrorResponse`

所有非 2xx 错误都会返回统一 JSON：

```json
{
  "error": "bad_request | unauthorized | forbidden | not_found | conflict | validation_error | internal_error | ...",
  "message": "human readable message",
  "request_id": "optional",
  "details": "optional any-json"
}
```

常见 `error` 值（与 HTTP status 对应）：

- 400 → `bad_request`
- 401 → `unauthorized`
- 403 → `forbidden`
- 404 → `not_found`
- 409 → `conflict`
- 422 → `validation_error`

### 1.4 LWW（Last-Write-Wins）与 `client_updated_at_ms`

Collections 使用 `client_updated_at_ms` 做 LWW。

- 单位：毫秒（Unix epoch ms）。
- 要求：对同一个 `id`，客户端应保证时间戳**单调递增**（至少不回退）。
- 服务器会对极端未来时间做 clamp：如果超出 `SYNC_MAX_CLIENT_CLOCK_SKEW_SECONDS`（默认 300s）会被截断到 `server_now + max_skew`。

冲突表现（重点）：

- **管理接口**（第 3 章）遇到旧写入会返回 **HTTP 409**。
  - `details.server_snapshot` 会给出服务端当前版本。
- **Sync push**（第 4 章）遇到冲突会返回 **HTTP 200**，但在 `rejected[]` 里标记 `reason="conflict"` 并带 `server` 快照。

### 1.5 软删除（tombstone）

- 删除不会物理删除 DB 行，而是设置 `deleted_at`。
- 客户端显示层面应当把 `deleted_at != null` 视为“已删除”。
- Sync pull 会包含 tombstone，便于多端一致删除。

### 1.6 排序规则

在同一 parent 下，服务端 list 默认排序：

1) `sort_order` 升序
2) `created_at` 升序（作为稳定 tie-break）

---

## 2. 数据结构

### 2.1 `CollectionItem`

Collections 的核心数据结构。

字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---:|:---:|---|
| `id` | string(<=36) | 是 | 建议 UUIDv4 字符串（36 位，含 `-`） |
| `item_type` | `folder` \| `note_ref` | 是 | folder=文件夹；note_ref=笔记引用 |
| `parent_id` | string(<=36) \| null | 否 | 父节点 id；root 为 null |
| `name` | string | 否 | folder 必须非空；note_ref 可为空字符串 |
| `color` | string \| null | 否 | 颜色/标签（自由字符串，最长 64） |
| `ref_type` | `flow_note` \| `memos_memo` \| null | 视 item_type | note_ref 必填；folder 必须为 null |
| `ref_id` | string \| null | 视 item_type | note_ref 必填；folder 必须为 null |
| `sort_order` | int | 是 | 排序值（允许重复） |
| `client_updated_at_ms` | int | 是 | 客户端更新时间戳（LWW） |
| `created_at` | datetime | 是 | 服务端创建时间（ISO 8601, UTC） |
| `updated_at` | datetime | 是 | 服务端更新时间（ISO 8601, UTC） |
| `deleted_at` | datetime \| null | 否 | tombstone；非空表示已删除 |

语义约束：

- 当 `item_type="folder"`：
  - `name` 必须非空
  - `ref_type/ref_id` 必须为 null
- 当 `item_type="note_ref"`：
  - `ref_type/ref_id` 必须存在且 `ref_id` 非空
  - `name` 允许为空（可选显示名）

### 2.2 `CollectionItemList`

```json
{
  "items": ["CollectionItem"],
  "total": 123,
  "limit": 200,
  "offset": 0
}
```

### 2.3 `OkResponse`

```json
{ "ok": true }
```

---

## 3. 管理接口（在线 API）

> 适用：在线直连、希望“即时保存到云端”的客户端。
>
> 如果你们是离线优先（本地先写，后面统一 sync），可以跳到第 4 章。

### 3.1 GET `/api/v1/collections/items`

用途：列出 collection items。

Query 参数：

- `parent_id`：可选；**当你提供该参数时**，表示只返回 `parent_id == <该值>` 的子节点。
  - 注意：**不传 parent_id 并不代表“只查 root”**，而是“不按 parent 过滤”（返回该用户全部 items）。
- `include_deleted`：可选，默认 `false`。
- `limit`：可选，默认 `200`，范围 `[1, 500]`。
- `offset`：可选，默认 `0`。

成功响应：200 `CollectionItemList`

常见错误：

- 401 `unauthorized`

示例（列出全部 items）：

```bash
curl -sS "http://localhost:31031/api/v1/collections/items?include_deleted=false&limit=200&offset=0" \
  -H "Authorization: Bearer $TOKEN"
```

示例（列出某个 folder 的直接子节点）：

```bash
curl -sS "http://localhost:31031/api/v1/collections/items?parent_id=$FOLDER_ID" \
  -H "Authorization: Bearer $TOKEN"
```

### 3.2 POST `/api/v1/collections/items`

用途：创建一个 folder 或 note_ref。

请求体（JSON）：`CollectionItemCreateRequest`

字段要点：

- `id` 可选：建议客户端生成 UUIDv4；不传则服务端生成。
- `client_updated_at_ms` 可选：不传/传 0 时服务端会用 server now。
- `sort_order` 可选：不传则默认为 0。

成功响应：201 `CollectionItem`

常见错误：

- 401 `unauthorized`
- 422 `validation_error`（字段缺失/语义不满足）
- 409 `conflict`（id 已存在）

示例：创建 root folder

```json
{
  "item_type": "folder",
  "parent_id": null,
  "name": "做饭",
  "color": "#3FA45B",
  "sort_order": 10,
  "client_updated_at_ms": 1730000000000
}
```

示例：创建 note_ref（引用 Flow note）

```json
{
  "item_type": "note_ref",
  "parent_id": "<folder-id>",
  "ref_type": "flow_note",
  "ref_id": "<note-id>",
  "color": null,
  "sort_order": 20,
  "client_updated_at_ms": 1730000000500
}
```

### 3.3 PATCH `/api/v1/collections/items/{item_id}`

用途：更新单个 item（改名/改色/改排序/（可选）改 parent/改引用）。

请求体（JSON）：`CollectionItemPatchRequest`

- 必填：`client_updated_at_ms`
- 至少提供一个要修改的字段（否则 422）

成功响应：200 `CollectionItem`

冲突：409 `conflict`

- 当 `client_updated_at_ms < server.client_updated_at_ms` 时。
- 返回：
  - `error="conflict"`
  - `details.server_snapshot`（服务端当前版本，用于客户端决策）

提示（推荐实践）：

- **移动/排序建议统一走 move 接口**（见 3.4），因为 move 会做 parent 存在性/防环校验。
- patch 支持写 `parent_id`，但并不适合作为“移动”的主通道。

### 3.4 PATCH `/api/v1/collections/items/move`

用途：批量移动/排序（也可用于单个 item）。

请求体（注意：是对象包一层 `items`，不是裸数组）：

```json
{
  "items": [
    {
      "id": "<item-id>",
      "parent_id": "<folder-id>" ,
      "sort_order": 100,
      "client_updated_at_ms": 1730000009999
    }
  ]
}
```

成功响应：200 `OkResponse`

常见错误：

- 400 `bad_request`
  - `cannot move folder under its descendant`
  - `cannot set parent_id to self`
  - `parent must be an active folder`
- 404 `not_found`：item 不存在或已删除
- 409 `conflict`：任一 item 的 `client_updated_at_ms` 旧于服务端

### 3.5 DELETE `/api/v1/collections/items/{item_id}?client_updated_at_ms=...`

用途：删除一个 item。

- 对 `note_ref`：只 tombstone 自己。
- 对 `folder`：会递归 tombstone 整棵子树（包含后代的 folder 与 note_ref）。

Query 参数：

- `client_updated_at_ms`（必填，`>=0`）

成功响应：204 No Content

冲突：409 `conflict`（同上，`client_updated_at_ms` 太旧）

### 3.6 POST `/api/v1/collections/items/batch-delete`

用途：批量删除（body 同样包一层 `items`）。

请求体：

```json
{
  "items": [
    {"id": "<id-1>", "client_updated_at_ms": 1730000000000},
    {"id": "<id-2>", "client_updated_at_ms": 1730000000100}
  ]
}
```

成功响应：200 `OkResponse`

---

## 4. 离线同步接口（强烈推荐给 APK：离线/多端）

Collections 已作为 sync 的一个新资源：`collection_item`。

### 4.1 资源名与 cursor 语义

- `resource`: `"collection_item"`
- cursor：沿用全局 `SyncEvent.id`（整数递增）。
- pull 的 `changes` 中 **总是存在** `collection_items` key（允许为空数组）。

### 4.2 `collection_item` 的 mutation data 形状

当 `op="upsert"` 时，`data` 的关键字段：

- `item_type`: `folder|note_ref`（必填）
- `parent_id`: string|null（可选）
- `name`: string（folder 必须非空；note_ref 可选）
- `color`: string|null（可选）
- `sort_order`: int（可选；不传则会沿用服务端当前值或默认 0）
- `ref_type`: `flow_note|memos_memo`（note_ref 必填）
- `ref_id`: string（note_ref 必填）

语义错误不会抛 4xx，而是进入 `rejected[]`（reason 如 `missing item_type` / `invalid item_type` / `name is required` 等）。

### 4.3 POST `/api/v1/sync/push`

请求体：

```json
{
  "mutations": [
    {
      "resource": "collection_item",
      "op": "upsert",
      "entity_id": "<collection-item-id>",
      "client_updated_at_ms": 1730000000000,
      "data": {
        "item_type": "folder",
        "name": "做饭",
        "parent_id": null,
        "sort_order": 10
      }
    }
  ]
}
```

响应体：

```json
{
  "cursor": 123,
  "applied": [{"resource":"collection_item","entity_id":"..."}],
  "rejected": [{"resource":"collection_item","entity_id":"...","reason":"conflict","server":{...}}]
}
```

注意：

- 即使有冲突/部分失败，HTTP 仍是 200；你要看 `applied`/`rejected`。
- upsert 会把 `deleted_at` 清空（允许 revive）。

### 4.4 GET `/api/v1/sync/pull?cursor=...&limit=...`

用途：拉取 cursor 后的增量变化。

响应体（关键字段）：

```json
{
  "cursor": 0,
  "next_cursor": 123,
  "has_more": false,
  "changes": {
    "collection_items": [
      {
        "id": "...",
        "item_type": "folder",
        "parent_id": null,
        "name": "...",
        "color": null,
        "ref_type": null,
        "ref_id": null,
        "sort_order": 0,
        "client_updated_at_ms": 1730000000000,
        "created_at": "2026-02-12T00:00:00Z",
        "updated_at": "2026-02-12T00:00:00Z",
        "deleted_at": null
      }
    ]
  }
}
```

客户端应用建议：

- 本地按 `id` 做 upsert：pull 里出现的每个 `CollectionItem` 都覆盖本地同 id 行（按服务端返回为准）。
- 若 `deleted_at != null`：本地标记删除（或直接从 UI 列表移除，但建议保留 tombstone 以便 debug）。
- 最终用 `parent_id` 组装树结构；root 节点条件是 `parent_id == null`。

---

## 5. 推荐的 APK 实现策略（经验建议）

### 5.1 离线优先（推荐）

1) 本地维护一张 `collection_items` 表（字段基本等同服务端）。
2) 任何本地操作都生成 mutation（upsert/delete）写入本地 outbox。
3) 定时或触发式调用 `/api/v1/sync/push` 发送 outbox。
4) 周期性调用 `/api/v1/sync/pull` 拉增量，更新本地表。

### 5.2 冲突处理建议

- 管理接口冲突（409）：
  - `details.server_snapshot` 是你做“覆盖/放弃/弹窗”的依据。
- sync 冲突（rejected reason=conflict）：
  - 用 `server` 快照比对；如果你们选择“客户端胜出”，则重新 upsert 并给一个更大的 `client_updated_at_ms`。

### 5.3 常见坑

- `GET /collections/items` 不传 `parent_id` 会返回“全部 items”，不是“root items”。
- `PATCH /collections/items/move` 的 body 需要 `{ "items": [...] }` 包装。
- `DELETE /collections/items/{id}` 必须带 query `client_updated_at_ms`。

---

## 6. 参考（机器可读）

- OpenAPI 快照：`apidocs/openapi-v1.json`
- 总接口文档：`apidocs/api.zh-CN.md`
