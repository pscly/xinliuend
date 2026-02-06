import { getOfflineDb, type OfflineUserKey } from "./db";

function nowMs(): number {
  return Date.now();
}

export async function getSyncCursor(user: OfflineUserKey): Promise<number> {
  const db = await getOfflineDb();
  const row = await db.get("sync_cursors", user);
  return row?.cursor ?? 0;
}

export async function setSyncCursor(user: OfflineUserKey, cursor: number): Promise<void> {
  const db = await getOfflineDb();
  await db.put("sync_cursors", { user, cursor, updated_at_ms: nowMs() });
}

