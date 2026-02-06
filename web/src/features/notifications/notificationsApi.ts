import { apiFetchJson } from "@/lib/api/client";

import type { Notification, NotificationListResponse, UnreadCountResponse } from "./types";

type QueryValue = string | number | boolean | null | undefined;

function withQuery(path: string, query: Record<string, QueryValue>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null) continue;
    sp.set(k, String(v));
  }
  const qs = sp.toString();
  return qs ? `${path}?${qs}` : path;
}

export async function listNotifications(params: {
  unread_only?: boolean;
  limit?: number;
  offset?: number;
} = {}): Promise<NotificationListResponse> {
  return await apiFetchJson<NotificationListResponse>(
    withQuery("/api/v1/notifications", {
      unread_only: params.unread_only,
      limit: params.limit,
      offset: params.offset,
    }),
    { method: "GET" },
  );
}

export async function getUnreadCount(): Promise<number> {
  const res = await apiFetchJson<UnreadCountResponse>("/api/v1/notifications/unread-count", { method: "GET" });
  return res.unread_count;
}

export async function markNotificationRead(notificationId: string): Promise<Notification> {
  // Cookie-session auth: apiFetchJson will inject X-CSRF-Token for non-safe methods.
  return await apiFetchJson<Notification>(`/api/v1/notifications/${encodeURIComponent(notificationId)}/read`, { method: "POST" });
}
