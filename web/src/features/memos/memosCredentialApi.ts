import { apiFetchJson } from "@/lib/api/client";
import { setCsrfToken } from "@/lib/api/csrf";

export type MemosCredentialStatus = {
  memos_base_url: string;
  has_token: boolean;
  token_preview: string | null;
  memos_user_id: number | null;
  can_auto_issue_token: boolean;
};

export type MemosCredentialUpdateResponse = {
  ok: boolean;
  token: string;
  server_url: string;
  memos_user_id: number;
  memos_username: string;
  token_preview: string;
  csrf_token: string | null;
};

function hydrateCsrf(data: MemosCredentialUpdateResponse) {
  if (data.csrf_token) setCsrfToken(data.csrf_token);
  return data;
}

export async function getMemosCredentialStatus(): Promise<MemosCredentialStatus> {
  return apiFetchJson<MemosCredentialStatus>("/api/v1/me/memos-credential", { method: "GET" });
}

export async function updateMemosCredentialToken(payload: {
  memos_token: string;
  memos_user_id?: number | null;
}): Promise<MemosCredentialUpdateResponse> {
  const data = await apiFetchJson<MemosCredentialUpdateResponse>("/api/v1/me/memos-credential/token", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      memos_token: payload.memos_token,
      memos_user_id: payload.memos_user_id ?? null,
    }),
  });
  return hydrateCsrf(data);
}

export async function issueMemosCredentialToken(payload: { current_password: string }): Promise<MemosCredentialUpdateResponse> {
  const data = await apiFetchJson<MemosCredentialUpdateResponse>("/api/v1/me/memos-credential/issue-token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return hydrateCsrf(data);
}
