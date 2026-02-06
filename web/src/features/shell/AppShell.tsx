"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getUnreadCount } from "@/features/notifications/notificationsApi";
import { useI18n } from "@/lib/i18n/useI18n";
import { useTheme } from "@/lib/theme/ThemeProvider";
import { nextThemePreference } from "@/lib/theme/theme";
import { useAuth } from "@/lib/auth/useAuth";
import { useOfflineEnabled } from "@/lib/offline/useOfflineEnabled";
import { startSyncLoop } from "@/lib/offline/syncEngine";

import styles from "./AppShell.module.css";

type NavItem = {
  href: string;
  labelKey:
    | "nav.home"
    | "nav.notes"
    | "nav.todos"
    | "nav.calendar"
    | "nav.search"
    | "nav.notifications"
    | "nav.settings";
};

const NAV: readonly NavItem[] = [
  { href: "/", labelKey: "nav.home" },
  { href: "/notes", labelKey: "nav.notes" },
  { href: "/todos", labelKey: "nav.todos" },
  { href: "/calendar", labelKey: "nav.calendar" },
  { href: "/search", labelKey: "nav.search" },
  { href: "/notifications", labelKey: "nav.notifications" },
  { href: "/settings", labelKey: "nav.settings" },
];

function themeLabelKey(preference: "system" | "light" | "dark") {
  if (preference === "light") return "ui.theme.light";
  if (preference === "dark") return "ui.theme.dark";
  return "ui.theme.system";
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { t } = useI18n();
  const { preference, setPreference } = useTheme();
  const { user, logout } = useAuth();
  const { offlineEnabled } = useOfflineEnabled();

  const [unreadCount, setUnreadCount] = useState<number>(0);

  useEffect(() => {
    if (!user) return;

    let cancelled = false;
    const refresh = async () => {
      try {
        const c = await getUnreadCount();
        if (!cancelled) setUnreadCount(c);
      } catch {
        // Best-effort: badge should not block nav.
        if (!cancelled) setUnreadCount(0);
      }
    };

    void refresh();

    const onChanged = () => {
      void refresh();
    };
    window.addEventListener("notifications:changed", onChanged);
    return () => {
      cancelled = true;
      window.removeEventListener("notifications:changed", onChanged);
    };
  }, [user]);

  const username = user?.username ?? null;

  useEffect(() => {
    if (!username) return;
    if (!offlineEnabled) return;
    const cleanup = startSyncLoop(username);
    return () => {
      if (typeof cleanup === "function") cleanup();
    };
  }, [offlineEnabled, username]);

  const normalizedPathname = pathname && pathname.endsWith("/") && pathname !== "/" ? pathname.slice(0, -1) : pathname;

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <div>
            <div className={styles.brand}>
              <img
                className={styles.brandMark}
                src="/icon-192.png"
                alt=""
                aria-hidden="true"
                draggable={false}
                decoding="async"
              />
              <div className={styles.brandName}>{t("app.name")}</div>
            </div>
            <nav className={styles.nav} aria-label="Primary">
              {NAV.map((item) => {
                const active = normalizedPathname === item.href;
                const className = active
                  ? `${styles.navLink} ${styles.navActive}`
                  : styles.navLink;
                const isNotifications = item.href === "/notifications";
                const showBadge = Boolean(user) && isNotifications && unreadCount > 0;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={className}
                    data-testid={isNotifications ? "nav-notifications" : undefined}
                  >
                    <span className={styles.navLinkInner}>
                      <span>{t(item.labelKey)}</span>
                      {showBadge ? <span className={styles.navBadge}>{unreadCount}</span> : null}
                    </span>
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className={styles.controls}>
            <button
              type="button"
              className={styles.pill}
              onClick={() => setPreference(nextThemePreference(preference))}
              aria-label={`${t("ui.theme")}: ${t(themeLabelKey(preference))}`}
            >
              <span className={styles.pillLabel}>{t("ui.theme")}</span>
              <span className={styles.pillValue}>{t(themeLabelKey(preference))}</span>
            </button>

            {user ? (
              <button
                type="button"
                className={styles.pill}
                onClick={async () => {
                  await logout();
                  router.replace("/login");
                }}
              >
                <span className={styles.pillLabel}>{user.username}</span>
                <span className={styles.pillValue}>{t("auth.logout")}</span>
              </button>
            ) : null}
          </div>
        </div>
      </header>
      <main className={styles.main}>{children}</main>
    </div>
  );
}
