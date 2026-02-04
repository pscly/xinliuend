import { getCsrfToken } from "./csrf";

export type ApiFetchOptions = Omit<RequestInit, "credentials"> & {
  credentials?: RequestCredentials;
};

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
    const text = await res.text().catch(() => "");
    throw new Error(`API request failed: ${res.status} ${res.statusText}${text ? ` - ${text}` : ""}`);
  }
  return (await res.json()) as T;
}
