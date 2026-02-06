import { apiFetch } from "@/lib/api/client";

export type MemosMigrationSummary = {
  remote_total: number;
  created_local: number;
  updated_local_from_remote: number;
  deleted_local_from_remote: number;
  conflicts: number;
};

export type MemosMigrationResponse = {
  ok: boolean;
  kind: "preview" | "apply";
  summary: MemosMigrationSummary;
  memos_base_url: string;
  warnings: string[];
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

async function requestMigration(path: string): Promise<MemosMigrationResponse> {
  const res = await apiFetch(path, { method: "POST" });
  if (!res.ok) {
    const clone = res.clone();
    try {
      const json = (await res.json()) as unknown;
      if (isRecord(json) && typeof json.message === "string" && json.message) {
        throw new Error(json.message);
      }
    } catch {
      // Ignore JSON parse errors; fall back to text.
    }

    const text = await clone.text().catch(() => "");
    if (text) throw new Error(text);
    throw new Error(`请求失败（HTTP ${res.status}）`);
  }
  return (await res.json()) as MemosMigrationResponse;
}

export async function previewMemosMigration(): Promise<MemosMigrationResponse> {
  return await requestMigration("/api/v1/memos/migration/preview");
}

export async function applyMemosMigration(): Promise<MemosMigrationResponse> {
  return await requestMigration("/api/v1/memos/migration/apply");
}
