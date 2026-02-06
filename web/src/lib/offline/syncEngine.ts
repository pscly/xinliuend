import { apiFetch } from "@/lib/api/client";

import type { Note } from "@/features/notes/types";

import { cacheClearConflict, cacheSetConflict, cacheUpsertNotes, cacheGetNote } from "./notesCache";
import { deleteOutboxRows, listPendingMutations, markOutboxBlocked } from "./outbox";
import { getSyncCursor, setSyncCursor } from "./syncState";
import type { OfflineUserKey, OutboxResource } from "./db";

export type SyncStatus = {
  online: boolean;
  syncing: boolean;
  pending: number;
  last_sync_at_ms: number | null;
  last_error: string | null;
};

type SyncListener = (next: SyncStatus) => void;

let _status: SyncStatus = {
  online: typeof navigator !== "undefined" ? navigator.onLine : true,
  syncing: false,
  pending: 0,
  last_sync_at_ms: null,
  last_error: null,
};

const _listeners = new Set<SyncListener>();

function setStatus(patch: Partial<SyncStatus>) {
  _status = { ..._status, ...patch };
  for (const fn of _listeners) fn(_status);
}

export function getSyncStatus(): SyncStatus {
  return _status;
}

export function subscribeSyncStatus(fn: SyncListener): () => void {
  _listeners.add(fn);
  fn(_status);
  return () => _listeners.delete(fn);
}

function nowMs(): number {
  return Date.now();
}

function normalizeErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  try {
    return JSON.stringify(err);
  } catch {
    return "未知错误";
  }
}

type SyncPushApplied = { resource: string; entity_id: string };
type SyncPushRejected = { resource: string; entity_id: string; reason: string; server?: unknown };
type SyncPushResponse = { cursor: number; applied: SyncPushApplied[]; rejected: SyncPushRejected[] };

type SyncPullResponse = {
  cursor: number;
  next_cursor: number;
  has_more: boolean;
  changes: { notes: Note[] };
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function parseServerNoteSnapshot(v: unknown): Note | null {
  if (!isRecord(v)) return null;
  const id = v.id;
  const title = v.title;
  const body_md = v.body_md;
  const tags = v.tags;
  const client_updated_at_ms = v.client_updated_at_ms;
  const created_at = v.created_at;
  const updated_at = v.updated_at;
  const deleted_at = v.deleted_at;

  if (typeof id !== "string" || !id) return null;
  if (typeof title !== "string") return null;
  if (typeof body_md !== "string") return null;
  if (!Array.isArray(tags)) return null;
  if (typeof client_updated_at_ms !== "number") return null;
  if (typeof created_at !== "string") return null;
  if (typeof updated_at !== "string") return null;
  if (!(typeof deleted_at === "string" || deleted_at === null)) return null;

  return {
    id,
    title,
    body_md,
    tags: tags.map((t) => String(t)),
    client_updated_at_ms,
    created_at,
    updated_at,
    deleted_at,
  };
}

function resourceSupportsOfflineSync(resource: string): resource is OutboxResource {
  return resource === "note";
}

let _activeUser: OfflineUserKey | null = null;
let _timer: number | null = null;
let _syncing = false;

export function startSyncLoop(user: OfflineUserKey) {
  if (_activeUser === user && _timer !== null) return;
  stopSyncLoop();

  _activeUser = user;

  const onOnline = () => {
    setStatus({ online: true });
    void syncNow();
  };
  const onOffline = () => {
    setStatus({ online: false });
  };
  window.addEventListener("online", onOnline);
  window.addEventListener("offline", onOffline);

  // First sync quickly, then poll.
  void syncNow();
  _timer = window.setInterval(() => {
    void syncNow();
  }, 15_000);

  return () => {
    window.removeEventListener("online", onOnline);
    window.removeEventListener("offline", onOffline);
    stopSyncLoop();
  };
}

export function stopSyncLoop() {
  _activeUser = null;
  if (_timer !== null) {
    window.clearInterval(_timer);
    _timer = null;
  }
}

export async function syncNow(): Promise<void> {
  const user = _activeUser;
  if (!user) return;
  if (!navigator.onLine) {
    setStatus({ online: false });
    return;
  }
  setStatus({ online: true });
  if (_syncing) return;
  _syncing = true;
  setStatus({ syncing: true, last_error: null });
  try {
    await syncOnce(user);
    setStatus({ last_sync_at_ms: nowMs(), last_error: null });
  } catch (err) {
    setStatus({ last_error: normalizeErrorMessage(err) });
  } finally {
    _syncing = false;
    setStatus({ syncing: false });
  }
}

async function syncOnce(user: OfflineUserKey): Promise<void> {
  // 1) Push pending mutations (best-effort).
  const pending = await listPendingMutations(user, 200);
  setStatus({ pending: pending.length });

  if (pending.length) {
    const payload = {
      mutations: pending.map((m) => ({
        resource: m.resource,
        op: m.op,
        entity_id: m.entity_id,
        client_updated_at_ms: m.client_updated_at_ms,
        data: m.data,
      })),
    };

    const res = await apiFetch("/api/v1/sync/push", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(text || `同步 push 失败（HTTP ${res.status}）`);
    }

    const json = (await res.json()) as SyncPushResponse;
    const appliedKeys = new Set(json.applied.map((a) => `${a.resource}::${a.entity_id}`));
    const rejectedByKey = new Map<string, SyncPushRejected>();
    for (const r of json.rejected) rejectedByKey.set(`${r.resource}::${r.entity_id}`, r);

    const idsToDelete: number[] = [];
    for (const row of pending) {
      const key = `${row.resource}::${row.entity_id}`;
      if (appliedKeys.has(key)) {
        idsToDelete.push(row.id);
        // Applied -> clear conflict flag if any.
        if (resourceSupportsOfflineSync(row.resource)) {
          await cacheClearConflict(user, row.entity_id);
        }
        continue;
      }

      const rej = rejectedByKey.get(key);
      if (!rej) continue;

      if (resourceSupportsOfflineSync(rej.resource) && rej.reason === "conflict") {
        idsToDelete.push(row.id);
        const serverNote = parseServerNoteSnapshot(rej.server);
        if (serverNote) {
          const localRow = await cacheGetNote(user, row.entity_id);
          if (localRow) {
            await cacheSetConflict(user, row.entity_id, {
              server: serverNote,
              local: {
                title: localRow.title,
                body_md: localRow.body_md,
                tags: localRow.tags,
                client_updated_at_ms: localRow.client_updated_at_ms,
              },
            });
          }
        }
        continue;
      }

      // Other rejection reasons: block the mutation (avoid hot-loop).
      await markOutboxBlocked(row.id, rej.reason || "rejected");
    }

    await deleteOutboxRows(idsToDelete);
    setStatus({ pending: Math.max(0, pending.length - idsToDelete.length) });
  }

  // 2) Pull server changes and refresh local cache.
  let cursor = await getSyncCursor(user);
  for (let i = 0; i < 50; i += 1) {
    const url = new URL("/api/v1/sync/pull", window.location.origin);
    url.searchParams.set("cursor", String(cursor));
    url.searchParams.set("limit", "200");
    const res2 = await apiFetch(url.toString(), { method: "GET" });
    if (!res2.ok) {
      const text = await res2.text().catch(() => "");
      throw new Error(text || `同步 pull 失败（HTTP ${res2.status}）`);
    }
    const data = (await res2.json()) as SyncPullResponse;
    const notes = Array.isArray(data?.changes?.notes) ? data.changes.notes : [];
    if (notes.length) {
      await cacheUpsertNotes(user, notes);
    }
    cursor = Number(data.next_cursor || cursor);
    await setSyncCursor(user, cursor);
    if (!data.has_more) break;
  }
}
