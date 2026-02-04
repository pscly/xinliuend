import type { ApiFetchOptions } from "@/lib/api/client";
import { apiFetch } from "@/lib/api/client";

import type {
  Note,
  NoteCreateRequest,
  NoteList,
  NotePatchRequest,
  NoteRestoreRequest,
  NotesConflictErrorBody,
  V2ErrorBody,
} from "./types";

export type NotesApiError =
  | {
      kind: "notes_conflict";
      status: 409;
      body: NotesConflictErrorBody;
      serverSnapshot?: Note;
    }
  | {
      kind: "v2_error";
      status: number;
      body: V2ErrorBody;
    }
  | {
      kind: "http_error";
      status: number;
      statusText: string;
      text?: string;
    };

export class NotesApiErrorException extends Error {
  readonly data: NotesApiError;

  constructor(data: NotesApiError) {
    super(formatNotesApiErrorMessage(data));
    this.name = "NotesApiError";
    this.data = data;
  }
}

function formatNotesApiErrorMessage(err: NotesApiError): string {
  if (err.kind === "notes_conflict") {
    return `Notes API conflict (409): ${err.body.message}`;
  }
  if (err.kind === "v2_error") {
    return `Notes API error (${err.status}): ${err.body.error} - ${err.body.message}`;
  }
  return `Notes API error (${err.status}): ${err.statusText}${err.text ? ` - ${err.text}` : ""}`;
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function isV2ErrorBody(v: unknown): v is V2ErrorBody {
  if (!isRecord(v)) return false;
  return typeof v.error === "string" && typeof v.message === "string";
}

async function readErrorPayload(res: Response): Promise<{ json?: unknown; text?: string }> {
  // Try JSON first for the v2 pinned error contract; fall back to text.
  const clone = res.clone();
  try {
    const json = (await res.json()) as unknown;
    return { json };
  } catch {
    const text = await clone.text().catch(() => "");
    return text ? { text } : {};
  }
}

async function toNotesApiError(res: Response): Promise<NotesApiError> {
  const { json, text } = await readErrorPayload(res);

  if (json && isV2ErrorBody(json)) {
    if (res.status === 409) {
      const body = json as NotesConflictErrorBody;
      return {
        kind: "notes_conflict",
        status: 409,
        body,
        serverSnapshot: body.details?.server_snapshot,
      };
    }

    return { kind: "v2_error", status: res.status, body: json };
  }

  return { kind: "http_error", status: res.status, statusText: res.statusText, text };
}

async function requestJson<T>(path: string, init: ApiFetchOptions): Promise<T> {
  const res = await apiFetch(path, init);
  if (!res.ok) {
    throw new NotesApiErrorException(await toNotesApiError(res));
  }
  return (await res.json()) as T;
}

function withQuery(path: string, query?: Record<string, string | number | boolean | undefined>): string {
  if (!query) return path;
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined) continue;
    sp.set(k, String(v));
  }
  const qs = sp.toString();
  return qs ? `${path}?${qs}` : path;
}

export async function listNotes(params: {
  limit?: number;
  offset?: number;
  tag?: string;
  q?: string;
  includeDeleted?: boolean;
} = {}): Promise<NoteList> {
  return await requestJson<NoteList>(
    withQuery("/api/v2/notes", {
      limit: params.limit,
      offset: params.offset,
      tag: params.tag,
      q: params.q,
      "include_deleted": params.includeDeleted,
    }),
    { method: "GET" },
  );
}

export async function createNote(payload: NoteCreateRequest): Promise<Note> {
  return await requestJson<Note>("/api/v2/notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getNote(noteId: string, params: { includeDeleted?: boolean } = {}): Promise<Note> {
  return await requestJson<Note>(
    withQuery(`/api/v2/notes/${encodeURIComponent(noteId)}`, {
      "include_deleted": params.includeDeleted,
    }),
    {
      method: "GET",
    },
  );
}

export async function patchNote(noteId: string, payload: NotePatchRequest): Promise<Note> {
  // Backend requires client_updated_at_ms and at least one other field.
  const anyField =
    payload.title !== undefined || payload.body_md !== undefined || payload.tags !== undefined;
  if (!anyField) {
    throw new NotesApiErrorException({
      kind: "http_error",
      status: 0,
      statusText: "invalid_request",
      text: "patchNote requires at least one of title/body_md/tags",
    });
  }

  return await requestJson<Note>(`/api/v2/notes/${encodeURIComponent(noteId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function deleteNote(noteId: string, clientUpdatedAtMs: number): Promise<void> {
  const res = await apiFetch(
    withQuery(`/api/v2/notes/${encodeURIComponent(noteId)}`, { "client_updated_at_ms": clientUpdatedAtMs }),
    { method: "DELETE" },
  );
  if (!res.ok) {
    throw new NotesApiErrorException(await toNotesApiError(res));
  }
}

export async function restoreNote(noteId: string, payload: NoteRestoreRequest): Promise<Note> {
  return await requestJson<Note>(`/api/v2/notes/${encodeURIComponent(noteId)}/restore`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
