export type MeData = {
  username: string;
  is_admin: boolean;
  csrf_token: string | null;
};

export type MeResponse = MeData;

export type LoginResponse = {
  // Intentionally ignored by the frontend in cookie-session mode.
  token: string;
  server_url: string;
  csrf_token: string;
};

export type LogoutResponse = { ok: boolean };

export type AuthUser = {
  username: string;
  isAdmin: boolean;
};

export type AuthStatus = "loading" | "authenticated" | "unauthenticated";
