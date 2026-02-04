export type IsoDateTimeString = string;

// Mirrors backend v2 schema: src/flow_backend/v2/schemas/notes.py
export type Note = {
  id: string;
  title: string;
  body_md: string;
  tags: string[];
  client_updated_at_ms: number;
  created_at: IsoDateTimeString;
  updated_at: IsoDateTimeString;
  deleted_at: IsoDateTimeString | null;
};

export type NoteList = {
  items: Note[];
  total: number;
  limit: number;
  offset: number;
};

export type NoteCreateRequest = {
  id?: string | null;
  title?: string | null;
  body_md: string;
  tags?: string[];
  client_updated_at_ms?: number | null;
};

// Enforce (at the type level) that patch includes at least one mutable field.
export type NotePatchFields =
  | { title: string; body_md?: string; tags?: string[] | null }
  | { body_md: string; title?: string; tags?: string[] | null }
  | { tags: string[] | null; title?: string; body_md?: string };

export type NotePatchRequest = NotePatchFields & {
  client_updated_at_ms: number;
};

export type NoteRestoreRequest = {
  client_updated_at_ms: number;
};

// Pinned v2 error contract: src/flow_backend/v2/schemas/errors.py
export type V2ErrorBody<TDetails = unknown> = {
  error: string;
  message: string;
  request_id?: string;
  details?: TDetails;
};

export type NotesConflictDetails = {
  server_snapshot?: Note;
};

export type NotesConflictErrorBody = V2ErrorBody<NotesConflictDetails>;
