import { apiFetchJson } from "@/lib/api/client";

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

async function requestMigration(path: string): Promise<MemosMigrationResponse> {
  return await apiFetchJson<MemosMigrationResponse>(path, { method: "POST" });
}

export async function previewMemosMigration(): Promise<MemosMigrationResponse> {
  return await requestMigration("/api/v1/memos/migration/preview");
}

export async function applyMemosMigration(): Promise<MemosMigrationResponse> {
  return await requestMigration("/api/v1/memos/migration/apply");
}
