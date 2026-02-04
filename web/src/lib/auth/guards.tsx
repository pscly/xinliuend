"use client";

import type { ReactNode } from "react";
import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "./useAuth";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [router, status]);

  if (status === "loading") {
    return null;
  }

  if (status === "unauthenticated") {
    // Prevent UI flash while redirecting.
    return null;
  }

  // Extra safety: if the app group ever gets mounted under /login.
  if (pathname === "/login") {
    return null;
  }

  return children;
}

export function RequireAdmin({ children }: { children: ReactNode }) {
  const { status, user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
      return;
    }

    if (status === "authenticated" && user && !user.isAdmin) {
      router.replace("/");
    }
  }, [router, status, user]);

  if (status === "loading") {
    return null;
  }

  if (status === "unauthenticated") {
    // Prevent UI flash while redirecting.
    return null;
  }

  // Extra safety: if a guarded subtree ever gets mounted under /login.
  if (pathname === "/login") {
    return null;
  }

  if (!user?.isAdmin) {
    // Prevent UI flash while redirecting non-admins.
    return null;
  }

  return children;
}

export function RedirectIfAuthenticated({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated") {
      router.replace("/");
    }
  }, [router, status]);

  if (status === "loading") {
    return null;
  }

  if (status === "authenticated") {
    return null;
  }

  return children;
}
