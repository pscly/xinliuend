export type IsoDateTimeString = string;

// Local datetimes are stored/transported without offset (backend enforces length=19).
// Example: "2026-02-03T13:45:00" (YYYY-MM-DDTHH:mm:ss)
export type LocalDateTimeString = string;

// Mirrors backend v1 todo routes:
// - src/flow_backend/routers/todo.py
// - src/flow_backend/schemas_todo.py

export type TodoList = {
  id: string;
  name: string;
  color: string | null;
  sort_order: number;
  archived: boolean;
  client_updated_at_ms: number;
  updated_at: IsoDateTimeString;
};

export type TodoItem = {
  id: string;
  list_id: string;
  parent_id: string | null;
  title: string;
  note: string;
  status: string;
  priority: number;
  due_at_local: LocalDateTimeString | null;
  completed_at_local: LocalDateTimeString | null;
  sort_order: number;
  tags: string[];
  is_recurring: boolean;
  rrule: string | null;
  dtstart_local: LocalDateTimeString | null;
  tzid: string;
  reminders: Array<Record<string, unknown>>;
  client_updated_at_ms: number;
  updated_at: IsoDateTimeString;
  deleted_at: IsoDateTimeString | null;
};

export type TodoOccurrence = {
  id: string;
  item_id: string;
  tzid: string;
  recurrence_id_local: LocalDateTimeString;
  status_override: string | null;
  title_override: string | null;
  note_override: string | null;
  due_at_override_local: LocalDateTimeString | null;
  completed_at_local: LocalDateTimeString | null;
  client_updated_at_ms: number;
  updated_at: IsoDateTimeString;
};

export type TodoListsResponse = { items: TodoList[] };
export type TodoItemsResponse = { items: TodoItem[] };
export type TodoOccurrencesResponse = { items: TodoOccurrence[] };

export type OkResponse = { ok: boolean };
export type IdResponse = { id: string };
export type IdsResponse = { ids: string[] };

// Request payloads (Pydantic defaults => optional fields in TS).

export type TodoListUpsertRequest = {
  id?: string | null;
  name: string;
  color?: string | null;
  sort_order?: number;
  archived?: boolean;
  client_updated_at_ms?: number;
};

export type TodoListPatchRequest = {
  name?: string | null;
  color?: string | null;
  sort_order?: number | null;
  archived?: boolean | null;
  client_updated_at_ms?: number;
};

export type TodoListReorderItem = {
  id: string;
  sort_order: number;
  client_updated_at_ms?: number;
};

export type TodoItemUpsertRequest = {
  id?: string | null;
  list_id: string;
  parent_id?: string | null;
  title: string;
  note?: string;
  status?: string;
  priority?: number;
  due_at_local?: LocalDateTimeString | null;
  completed_at_local?: LocalDateTimeString | null;
  sort_order?: number;
  tags?: string[];
  is_recurring?: boolean;
  rrule?: string | null;
  dtstart_local?: LocalDateTimeString | null;
  tzid?: string;
  reminders?: Array<Record<string, unknown>>;
  client_updated_at_ms?: number;
};

export type TodoItemPatchRequest = {
  list_id?: string | null;
  parent_id?: string | null;
  title?: string | null;
  note?: string | null;
  status?: string | null;
  priority?: number | null;
  due_at_local?: LocalDateTimeString | null;
  completed_at_local?: LocalDateTimeString | null;
  sort_order?: number | null;
  tags?: string[] | null;
  is_recurring?: boolean | null;
  rrule?: string | null;
  dtstart_local?: LocalDateTimeString | null;
  tzid?: string | null;
  reminders?: Array<Record<string, unknown>> | null;
  client_updated_at_ms?: number;
};

export type TodoOccurrenceUpsertRequest = {
  id?: string | null;
  item_id: string;
  tzid?: string;
  recurrence_id_local: LocalDateTimeString;
  status_override?: string | null;
  title_override?: string | null;
  note_override?: string | null;
  due_at_override_local?: LocalDateTimeString | null;
  completed_at_local?: LocalDateTimeString | null;
  client_updated_at_ms?: number;
};

// Common query shapes.
export type TodoListsQuery = {
  include_archived?: boolean;
};

export type TodoItemsQuery = {
  list_id?: string;
  status?: string;
  tag?: string;
  include_archived_lists?: boolean;
  include_deleted?: boolean;
  limit?: number;
  offset?: number;
};

export type TodoOccurrencesQuery = {
  item_id: string;
  from?: LocalDateTimeString;
  to?: LocalDateTimeString;
};
