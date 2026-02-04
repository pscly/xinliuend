import { apiFetchJson } from "@/lib/api/client";

import type {
  IdResponse,
  IdsResponse,
  OkResponse,
  TodoItemsQuery,
  TodoItemsResponse,
  TodoItemPatchRequest,
  TodoItemUpsertRequest,
  TodoListsQuery,
  TodoListsResponse,
  TodoListPatchRequest,
  TodoListReorderItem,
  TodoListUpsertRequest,
  TodoOccurrencesQuery,
  TodoOccurrencesResponse,
  TodoOccurrenceUpsertRequest,
} from "./types";

type QueryValue = string | number | boolean | null | undefined;

function buildQueryString(params: Record<string, QueryValue>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    sp.set(k, typeof v === "string" ? v : String(v));
  }
  const qs = sp.toString();
  return qs ? `?${qs}` : "";
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  };
}

const TODO_V1_BASE = "/api/v1/todo";

// Lists

export function getTodoLists(query: TodoListsQuery = {}): Promise<TodoListsResponse> {
  const qs = buildQueryString({
    include_archived: query.include_archived,
  });
  return apiFetchJson<TodoListsResponse>(`${TODO_V1_BASE}/lists${qs}`);
}

export function upsertTodoList(payload: TodoListUpsertRequest): Promise<IdResponse> {
  return apiFetchJson<IdResponse>(`${TODO_V1_BASE}/lists`, jsonInit("POST", payload));
}

export function patchTodoList(listId: string, payload: TodoListPatchRequest): Promise<OkResponse> {
  const id = encodeURIComponent(listId);
  return apiFetchJson<OkResponse>(`${TODO_V1_BASE}/lists/${id}`, jsonInit("PATCH", payload));
}

export function reorderTodoLists(items: TodoListReorderItem[]): Promise<OkResponse> {
  return apiFetchJson<OkResponse>(`${TODO_V1_BASE}/lists/reorder`, jsonInit("POST", items));
}

export function deleteTodoList(listId: string, clientUpdatedAtMs: number): Promise<OkResponse> {
  const id = encodeURIComponent(listId);
  const qs = buildQueryString({ client_updated_at_ms: clientUpdatedAtMs });
  return apiFetchJson<OkResponse>(`${TODO_V1_BASE}/lists/${id}${qs}`, { method: "DELETE" });
}

// Items

export function getTodoItems(query: TodoItemsQuery = {}): Promise<TodoItemsResponse> {
  const qs = buildQueryString({
    list_id: query.list_id,
    status: query.status,
    tag: query.tag,
    include_archived_lists: query.include_archived_lists,
    include_deleted: query.include_deleted,
    limit: query.limit,
    offset: query.offset,
  });
  return apiFetchJson<TodoItemsResponse>(`${TODO_V1_BASE}/items${qs}`);
}

export function upsertTodoItem(payload: TodoItemUpsertRequest): Promise<IdResponse> {
  return apiFetchJson<IdResponse>(`${TODO_V1_BASE}/items`, jsonInit("POST", payload));
}

export function bulkUpsertTodoItems(payloads: TodoItemUpsertRequest[]): Promise<IdsResponse> {
  return apiFetchJson<IdsResponse>(`${TODO_V1_BASE}/items/bulk`, jsonInit("POST", payloads));
}

export function patchTodoItem(itemId: string, payload: TodoItemPatchRequest): Promise<OkResponse> {
  const id = encodeURIComponent(itemId);
  return apiFetchJson<OkResponse>(`${TODO_V1_BASE}/items/${id}`, jsonInit("PATCH", payload));
}

export function deleteTodoItem(itemId: string, clientUpdatedAtMs: number): Promise<OkResponse> {
  const id = encodeURIComponent(itemId);
  const qs = buildQueryString({ client_updated_at_ms: clientUpdatedAtMs });
  return apiFetchJson<OkResponse>(`${TODO_V1_BASE}/items/${id}${qs}`, { method: "DELETE" });
}

// Occurrences

export function getTodoOccurrences(query: TodoOccurrencesQuery): Promise<TodoOccurrencesResponse> {
  const qs = buildQueryString({
    item_id: query.item_id,
    from: query.from,
    to: query.to,
  });
  return apiFetchJson<TodoOccurrencesResponse>(`${TODO_V1_BASE}/occurrences${qs}`);
}

export function upsertTodoOccurrence(payload: TodoOccurrenceUpsertRequest): Promise<IdResponse> {
  return apiFetchJson<IdResponse>(`${TODO_V1_BASE}/occurrences`, jsonInit("POST", payload));
}

export function bulkUpsertTodoOccurrences(payloads: TodoOccurrenceUpsertRequest[]): Promise<IdsResponse> {
  return apiFetchJson<IdsResponse>(`${TODO_V1_BASE}/occurrences/bulk`, jsonInit("POST", payloads));
}

export function deleteTodoOccurrence(
  occurrenceId: string,
  clientUpdatedAtMs: number
): Promise<OkResponse> {
  const id = encodeURIComponent(occurrenceId);
  const qs = buildQueryString({ client_updated_at_ms: clientUpdatedAtMs });
  return apiFetchJson<OkResponse>(`${TODO_V1_BASE}/occurrences/${id}${qs}`, { method: "DELETE" });
}
