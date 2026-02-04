export type Notification = {
  id: string;
  kind: string;
  payload: Record<string, unknown>;
  created_at: string;
  read_at: string | null;
};

export type NotificationListResponse = {
  notifications: Notification[];
  total: number;
  limit: number;
  offset: number;
};

export type UnreadCountResponse = {
  unread_count: number;
};
