import type { DBSchema, IDBPDatabase } from "idb";
import { openDB } from "idb";

import type { Note } from "@/features/notes/types";

export const OFFLINE_DB_NAME = "xinliu-web-offline";
export const OFFLINE_DB_VERSION = 1;

export type OfflineUserKey = string; // username

export type CachedNoteRow = Note & {
  key: string; // `${user}::${id}`
  user: OfflineUserKey;
  // Local-only metadata (not sent to server)
  local_updated_at_ms: number;
  local_status: "clean" | "queued" | "conflict";
  conflict_server_snapshot: Note | null;
  conflict_local_snapshot: Pick<Note, "title" | "body_md" | "tags" | "client_updated_at_ms"> | null;
};

export type OutboxResource = "note";
export type OutboxOp = "upsert" | "delete";

export type OutboxRow = {
  id?: number; // auto-increment
  user: OfflineUserKey;
  resource: OutboxResource;
  op: OutboxOp;
  entity_id: string;
  client_updated_at_ms: number;
  data: Record<string, unknown>;
  created_at_ms: number;
  status: "pending" | "blocked";
  last_error: string | null;
};

export type SyncCursorRow = {
  user: OfflineUserKey;
  cursor: number;
  updated_at_ms: number;
};

interface OfflineDbSchema extends DBSchema {
  notes: {
    key: string;
    value: CachedNoteRow;
    indexes: { "by-user": OfflineUserKey };
  };
  outbox: {
    key: number;
    value: OutboxRow;
    indexes: {
      "by-user": OfflineUserKey;
      "by-user-status-created": [OfflineUserKey, OutboxRow["status"], number];
      "by-user-resource-entity": [OfflineUserKey, OutboxResource, string];
    };
  };
  sync_cursors: {
    key: OfflineUserKey;
    value: SyncCursorRow;
  };
}

let _dbPromise: Promise<IDBPDatabase<OfflineDbSchema>> | null = null;

export function noteKey(user: OfflineUserKey, noteId: string): string {
  return `${user}::${noteId}`;
}

export function getOfflineDb(): Promise<IDBPDatabase<OfflineDbSchema>> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("离线数据库仅在浏览器环境可用"));
  }
  if (_dbPromise) return _dbPromise;

  _dbPromise = openDB<OfflineDbSchema>(OFFLINE_DB_NAME, OFFLINE_DB_VERSION, {
    upgrade(db) {
      if (!db.objectStoreNames.contains("notes")) {
        const store = db.createObjectStore("notes", { keyPath: "key" });
        store.createIndex("by-user", "user");
      }
      if (!db.objectStoreNames.contains("outbox")) {
        const store = db.createObjectStore("outbox", { keyPath: "id", autoIncrement: true });
        store.createIndex("by-user", "user");
        store.createIndex("by-user-status-created", ["user", "status", "created_at_ms"]);
        store.createIndex("by-user-resource-entity", ["user", "resource", "entity_id"]);
      }
      if (!db.objectStoreNames.contains("sync_cursors")) {
        db.createObjectStore("sync_cursors", { keyPath: "user" });
      }
    },
  });

  return _dbPromise;
}

function deleteBrowserDatabase(name: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.deleteDatabase(name);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error ?? new Error("删除 IndexedDB 失败"));
    // 若被其它 tab/连接阻塞，这里仍 resolve，让调用方自行提示用户刷新重试。
    req.onblocked = () => resolve();
  });
}

/**
 * 清空离线数据库（IndexedDB）。
 *
 * 说明：这不会删除服务端数据，仅清理浏览器本地缓存与 outbox。
 */
export async function resetOfflineDb(): Promise<void> {
  if (typeof window === "undefined") return;

  const prev = _dbPromise;
  _dbPromise = null;
  if (prev) {
    try {
      const db = await prev;
      db.close();
    } catch {
      // Ignore close errors.
    }
  }

  await deleteBrowserDatabase(OFFLINE_DB_NAME);
}
