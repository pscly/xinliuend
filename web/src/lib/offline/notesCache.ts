import type { Note } from "@/features/notes/types";

import { getOfflineDb, noteKey, type CachedNoteRow, type OfflineUserKey } from "./db";

function nowMs(): number {
  return Date.now();
}

function toCachedRow(user: OfflineUserKey, note: Note, prev?: CachedNoteRow | null): CachedNoteRow {
  return {
    ...note,
    key: noteKey(user, note.id),
    user,
    local_updated_at_ms: nowMs(),
    local_status: prev?.local_status ?? "clean",
    conflict_server_snapshot: prev?.conflict_server_snapshot ?? null,
    conflict_local_snapshot: prev?.conflict_local_snapshot ?? null,
  };
}

export async function cacheUpsertNote(user: OfflineUserKey, note: Note): Promise<void> {
  const db = await getOfflineDb();
  const key = noteKey(user, note.id);
  const prev = (await db.get("notes", key)) ?? null;
  const row = toCachedRow(user, note, prev);
  row.local_status = "clean";
  row.conflict_server_snapshot = null;
  row.conflict_local_snapshot = null;
  await db.put("notes", row);
}

export async function cacheUpsertNotes(user: OfflineUserKey, notes: Note[]): Promise<void> {
  const db = await getOfflineDb();
  const tx = db.transaction("notes", "readwrite");
  for (const n of notes) {
    const key = noteKey(user, n.id);
    const prev = (await tx.store.get(key)) ?? null;
    const row = toCachedRow(user, n, prev);
    row.local_status = "clean";
    row.conflict_server_snapshot = null;
    row.conflict_local_snapshot = null;
    await tx.store.put(row);
  }
  await tx.done;
}

export async function cacheGetNote(user: OfflineUserKey, noteId: string): Promise<CachedNoteRow | null> {
  const db = await getOfflineDb();
  const row = await db.get("notes", noteKey(user, noteId));
  return row ?? null;
}

export async function cacheListNotes(user: OfflineUserKey): Promise<CachedNoteRow[]> {
  const db = await getOfflineDb();
  return await db.getAllFromIndex("notes", "by-user", user);
}

export async function cacheMarkQueued(
  user: OfflineUserKey,
  noteId: string,
): Promise<void> {
  const db = await getOfflineDb();
  const key = noteKey(user, noteId);
  const row = await db.get("notes", key);
  if (!row) return;
  row.local_status = row.local_status === "conflict" ? "conflict" : "queued";
  row.local_updated_at_ms = nowMs();
  await db.put("notes", row);
}

export async function cacheSetConflict(
  user: OfflineUserKey,
  noteId: string,
  params: {
    server: Note;
    local: Pick<Note, "title" | "body_md" | "tags" | "client_updated_at_ms">;
  },
): Promise<void> {
  const db = await getOfflineDb();
  const key = noteKey(user, noteId);
  const row = await db.get("notes", key);
  if (!row) return;
  row.local_status = "conflict";
  row.conflict_server_snapshot = params.server;
  row.conflict_local_snapshot = params.local;
  row.local_updated_at_ms = nowMs();
  await db.put("notes", row);
}

export async function cacheClearConflict(user: OfflineUserKey, noteId: string): Promise<void> {
  const db = await getOfflineDb();
  const key = noteKey(user, noteId);
  const row = await db.get("notes", key);
  if (!row) return;
  row.local_status = "clean";
  row.conflict_server_snapshot = null;
  row.conflict_local_snapshot = null;
  row.local_updated_at_ms = nowMs();
  await db.put("notes", row);
}

export function deriveNoteTitle(bodyMd: string): string {
  for (const line of (bodyMd || "").split("\n")) {
    const trimmed = line.trim();
    if (trimmed) return trimmed.slice(0, 500);
  }
  return "";
}

