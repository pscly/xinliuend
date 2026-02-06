import { getCsrfToken } from "./csrf";

export type ApiFetchOptions = Omit<RequestInit, "credentials"> & {
  credentials?: RequestCredentials;
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function normalizeMessage(v: unknown): string | null {
  if (typeof v !== "string") return null;
  const trimmed = v.trim();
  return trimmed ? trimmed : null;
}

function extractMessageFromErrorPayload(payload: unknown): string | null {
  if (!isRecord(payload)) return null;

  const direct =
    normalizeMessage(payload.message) ??
    normalizeMessage(payload.detail) ??
    normalizeMessage(payload.error);
  if (direct) return direct;

  // FastAPI validation errors: {"detail":[{"loc":[...],"msg":"...","type":"..."}]}
  const detail = payload.detail;
  if (Array.isArray(detail)) {
    const msgs: string[] = [];
    for (const it of detail) {
      if (!isRecord(it)) continue;
      const m = normalizeMessage(it.msg);
      if (m) msgs.push(m);
    }
    if (msgs.length) return msgs.join("；");
  }

  return null;
}

async function readResponseErrorMessage(res: Response): Promise<string | null> {
  const raw = await res.text().catch(() => "");
  const trimmed = raw.trim();
  if (!trimmed) return null;

  try {
    const json = JSON.parse(trimmed) as unknown;
    const extracted = extractMessageFromErrorPayload(json);
    if (extracted) return extracted;
  } catch {
    // Not JSON; fall back to raw text.
  }

  return trimmed;
}

function resolveUrl(path: string): string {
  // Absolute URL: pass through.
  if (/^https?:\/\//i.test(path)) return path;

  // Client-side relative fetch works fine (and keeps cookies same-origin).
  if (typeof window !== "undefined") return path;

  // Server-side fetch needs an absolute URL. This default is only for
  // scaffolding; override in deployments.
  const origin = process.env.NEXT_PUBLIC_APP_ORIGIN ?? "http://localhost:3000";
  return new URL(path, origin).toString();
}

export async function apiFetch(path: string, init: ApiFetchOptions = {}) {
  const url = resolveUrl(path);

  const method = (init.method ?? "GET").toUpperCase();
  const isSafeMethod = method === "GET" || method === "HEAD" || method === "OPTIONS";
  const csrfToken = !isSafeMethod ? getCsrfToken() : null;

  const res = await fetch(url, {
    ...init,
    credentials: init.credentials ?? "include",
    headers: {
      // For cookie-session auth, non-safe methods require X-CSRF-Token.
      ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
      ...(init.headers ?? {}),
      Accept: "application/json",
    },
  });
  return res;
}

export async function apiFetchJson<T>(path: string, init: ApiFetchOptions = {}): Promise<T> {
  const res = await apiFetch(path, init);
  if (!res.ok) {
    const msg = await readResponseErrorMessage(res);
    const prefix = `请求失败（HTTP ${res.status}）`;
    throw new Error(msg ? `${prefix}：${msg}` : prefix);
  }
  return (await res.json()) as T;
}
