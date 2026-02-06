import { getOfflineDb, type OfflineUserKey, type OutboxOp, type OutboxResource, type OutboxRow } from "./db";

function nowMs(): number {
  return Date.now();
}

export type EnqueueMutationInput = {
  user: OfflineUserKey;
  resource: OutboxResource;
  op: OutboxOp;
  entity_id: string;
  client_updated_at_ms: number;
  data: Record<string, unknown>;
};

export async function enqueueMutation(input: EnqueueMutationInput): Promise<void> {
  const db = await getOfflineDb();
  const tx = db.transaction("outbox", "readwrite");

  // De-dup: keep only the latest pending mutation for the same (user, resource, entity).
  const idx = tx.store.index("by-user-resource-entity");
  const existing = await idx.getAll([input.user, input.resource, input.entity_id]);
  for (const row of existing) {
    if (row.status === "pending") {
      if (typeof row.id === "number") {
        await tx.store.delete(row.id);
      }
    }
  }

  const row: OutboxRow = {
    user: input.user,
    resource: input.resource,
    op: input.op,
    entity_id: input.entity_id,
    client_updated_at_ms: input.client_updated_at_ms,
    data: input.data,
    created_at_ms: nowMs(),
    status: "pending",
    last_error: null,
  };
  await tx.store.add(row);
  await tx.done;
}

export type PendingOutboxRow = Required<OutboxRow> & { id: number };

export async function listPendingMutations(user: OfflineUserKey, limit = 100): Promise<PendingOutboxRow[]> {
  const db = await getOfflineDb();
  const idx = db.transaction("outbox").store.index("by-user-status-created");
  const range = IDBKeyRange.bound([user, "pending", 0], [user, "pending", Number.MAX_SAFE_INTEGER]);
  const rows = await idx.getAll(range, limit);
  return rows.filter((r): r is PendingOutboxRow => typeof r.id === "number");
}

export async function deleteOutboxRows(ids: number[]): Promise<void> {
  if (!ids.length) return;
  const db = await getOfflineDb();
  const tx = db.transaction("outbox", "readwrite");
  for (const id of ids) {
    await tx.store.delete(id);
  }
  await tx.done;
}

export async function markOutboxBlocked(id: number, message: string): Promise<void> {
  const db = await getOfflineDb();
  const tx = db.transaction("outbox", "readwrite");
  const row = await tx.store.get(id);
  if (!row) return;
  row.status = "blocked";
  row.last_error = message;
  await tx.store.put(row);
  await tx.done;
}
