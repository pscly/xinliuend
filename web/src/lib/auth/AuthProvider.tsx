"use client";

import type { ReactNode } from "react";
import { createContext, useCallback, useEffect, useMemo, useState } from "react";

import { apiFetchJson } from "@/lib/api/client";
import { setCsrfToken } from "@/lib/api/csrf";

import type { AuthStatus, AuthUser, LoginResponse, LogoutResponse, MeResponse } from "./types";

type AuthContextValue = {
  status: AuthStatus;
  user: AuthUser | null;
  csrfToken: string | null;
  refreshMe: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [csrfToken, setLocalCsrfToken] = useState<string | null>(null);

  const setSession = useCallback((next: { user: AuthUser | null; csrfToken: string | null; status: AuthStatus }) => {
    setUser(next.user);
    setLocalCsrfToken(next.csrfToken);
    setCsrfToken(next.csrfToken);
    setStatus(next.status);
  }, []);

  const refreshMe = useCallback(async () => {
    try {
      const data = await apiFetchJson<MeResponse>("/api/v1/me", { method: "GET" });
      setSession({
        user: { username: data.username, isAdmin: data.is_admin },
        csrfToken: data.csrf_token,
        status: "authenticated",
      });
    } catch {
      // 401 is the expected signal for logged-out sessions.
      setSession({ user: null, csrfToken: null, status: "unauthenticated" });
    }
  }, [setSession]);

  const login = useCallback(
    async (username: string, password: string) => {
      // Cookie-session login: backend sets httpOnly cookie; frontend does not store tokens.
      await apiFetchJson<LoginResponse>("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      await refreshMe();
    },
    [refreshMe],
  );

  const logout = useCallback(async () => {
    // Ensure CSRF token is hydrated before a cookie-auth logout.
    if (!csrfToken) {
      await refreshMe().catch(() => undefined);
    }

    try {
      await apiFetchJson<LogoutResponse>("/api/v1/auth/logout", { method: "POST" });
    } catch {
      // Best-effort: local state should still clear even if network/CSRF fails.
    } finally {
      setSession({ user: null, csrfToken: null, status: "unauthenticated" });
    }
  }, [csrfToken, refreshMe, setSession]);

  useEffect(() => {
    void refreshMe();
  }, [refreshMe]);

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, csrfToken, refreshMe, login, logout }),
    [csrfToken, login, logout, refreshMe, status, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
