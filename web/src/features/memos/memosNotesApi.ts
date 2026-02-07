import { apiFetchJson } from "@/lib/api/client";

export type MemosNote = {
  remote_id: string;
  title: string;
  body_md: string;
  updated_at: string | null;
  deleted: boolean;
  source: "memos";
  linked_local_note_id: string | null;
};

export type MemosNoteListResponse = {
  items: MemosNote[];
  total: number;
  limit: number;
  offset: number;
  warnings: string[];
};

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

export async function listMemosNotes(params: {
  limit?: number;
  offset?: number;
  includeDeleted?: boolean;
} = {}): Promise<MemosNoteListResponse> {
  return await apiFetchJson<MemosNoteListResponse>(
    withQuery("/api/v1/memos/notes", {
      limit: params.limit,
      offset: params.offset,
      include_deleted: params.includeDeleted,
    }),
    { method: "GET" },
  );
}
