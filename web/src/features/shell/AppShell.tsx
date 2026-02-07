"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getUnreadCount } from "@/features/notifications/notificationsApi";
import { InkIcon } from "@/features/ui/InkIcon";
import { useI18n } from "@/lib/i18n/useI18n";
import type { MessageKey } from "@/lib/i18n/messages";
import { useTheme } from "@/lib/theme/ThemeProvider";
import { nextThemePalette, nextThemePreference, type ThemePalette } from "@/lib/theme/theme";
import { useAuth } from "@/lib/auth/useAuth";
import type { AuthUser } from "@/lib/auth/types";
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
  icon: Parameters<typeof InkIcon>[0]["name"];
};

const NAV: readonly NavItem[] = [
  { href: "/", labelKey: "nav.home", icon: "home" },
  { href: "/notes", labelKey: "nav.notes", icon: "notes" },
  { href: "/todos", labelKey: "nav.todos", icon: "todos" },
  { href: "/calendar", labelKey: "nav.calendar", icon: "calendar" },
  { href: "/search", labelKey: "nav.search", icon: "search" },
  { href: "/notifications", labelKey: "nav.notifications", icon: "notifications" },
  { href: "/settings", labelKey: "nav.settings", icon: "settings" },
];

function themeLabelKey(preference: "system" | "light" | "dark") {
  if (preference === "light") return "ui.theme.light";
  if (preference === "dark") return "ui.theme.dark";
  return "ui.theme.system";
}

function paletteLabelKey(palette: ThemePalette) {
  if (palette === "indigo") return "ui.palette.indigo";
  if (palette === "cyber") return "ui.palette.cyber";
  return "ui.palette.paperInk";
}

function isActiveHref(normalizedPathname: string | null, href: string): boolean {
  if (!normalizedPathname) return false;
  if (href === "/") return normalizedPathname === "/";
  return normalizedPathname === href || normalizedPathname.startsWith(`${href}/`);
}

function DrawerContent({
  normalizedPathname,
  t,
  user,
  unreadCount,
  palette,
  preference,
  setPalette,
  setPreference,
  onLogout,
  onNavigate,
}: {
  normalizedPathname: string | null;
  t: (key: MessageKey) => string;
  user: AuthUser | null;
  unreadCount: number;
  palette: ThemePalette;
  preference: "system" | "light" | "dark";
  setPalette: (next: ThemePalette) => void;
  setPreference: (next: "system" | "light" | "dark") => void;
  onLogout: () => Promise<void>;
  onNavigate?: () => void;
}) {
  const showUser = Boolean(user);
  const showBadge = Boolean(user) && unreadCount > 0;

  return (
    <div className={styles.drawerInner}>
      <div className={styles.drawerHeader}>
        <div className={styles.drawerBrand}>
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

        {showUser ? (
          <div className={styles.drawerUser}>
            <div className={styles.drawerUserName}>{user?.username}</div>
            <div className={styles.drawerUserMeta}>{user?.isAdmin ? "管理员" : "用户"}</div>
          </div>
        ) : null}
      </div>

      <nav className={styles.drawerNav} aria-label="Primary">
        {NAV.map((item) => {
          const active = isActiveHref(normalizedPathname, item.href);
          const isNotifications = item.href === "/notifications";
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              className={active ? `${styles.navLink} ${styles.navActive}` : styles.navLink}
              data-testid={isNotifications ? "nav-notifications" : undefined}
            >
              <span className={styles.navIcon}>
                <InkIcon name={item.icon} size={18} />
              </span>
              <span className={styles.navLabel}>{t(item.labelKey)}</span>
              {isNotifications && showBadge ? <span className={styles.navBadge}>{unreadCount}</span> : null}
            </Link>
          );
        })}
      </nav>

      <div className={styles.drawerSection}>
        <div className={styles.drawerSectionTitle}>{t("ui.theme")}</div>
        <button
          type="button"
          className={styles.drawerControl}
          onClick={() => setPreference(nextThemePreference(preference))}
          aria-label={`${t("ui.theme")}（当前：${t(themeLabelKey(preference))}）`}
        >
          <span className={styles.controlIcon}>
            <InkIcon name="theme" size={18} />
          </span>
          <span className={styles.controlText}>
            <span className={styles.controlLabel}>{t("ui.theme")}</span>
            <span className={styles.controlValue}>{t(themeLabelKey(preference))}</span>
          </span>
        </button>

        <button
          type="button"
          className={styles.drawerControl}
          onClick={() => setPalette(nextThemePalette(palette))}
          aria-label={`${t("ui.palette")}（当前：${t(paletteLabelKey(palette))}）`}
        >
          <span className={styles.controlIcon}>
            <InkIcon name="palette" size={18} />
          </span>
          <span className={styles.controlText}>
            <span className={styles.controlLabel}>{t("ui.palette")}</span>
            <span className={styles.controlValue}>{t(paletteLabelKey(palette))}</span>
          </span>
        </button>
      </div>

      {user ? (
        <div className={styles.drawerSection}>
          <div className={styles.drawerSectionTitle}>{t("settings.account.title")}</div>
          <button type="button" className={styles.drawerControl} onClick={onLogout}>
            <span className={styles.controlIcon}>
              <InkIcon name="logout" size={18} />
            </span>
            <span className={styles.controlText}>
              <span className={styles.controlLabel}>{t("auth.logout")}</span>
              <span className={styles.controlValue}>{user.username}</span>
            </span>
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { t } = useI18n();
  const { palette, preference, setPalette, setPreference } = useTheme();
  const { user, logout } = useAuth();
  const { offlineEnabled } = useOfflineEnabled();

  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);

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

  useEffect(() => {
    if (!drawerOpen) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [drawerOpen]);

  return (
    <div className={styles.shell}>
      <header className={styles.appBar}>
        <div className={styles.appBarInner}>
          <div className={styles.appBarLeft}>
            <button
              type="button"
              className={styles.menuButton}
              onClick={() => setDrawerOpen(true)}
              aria-label="打开菜单"
            >
              <InkIcon name="menu" size={20} />
            </button>

            <div className={styles.brandInline}>
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
          </div>

          <div className={styles.appBarRight}>
            <button
              type="button"
              className={styles.iconButton}
              onClick={() => setPreference(nextThemePreference(preference))}
              aria-label={`${t("ui.theme")}: ${t(themeLabelKey(preference))}`}
              title={t("ui.theme")}
            >
              <InkIcon name="theme" size={18} />
            </button>

            <button
              type="button"
              className={styles.iconButton}
              onClick={() => setPalette(nextThemePalette(palette))}
              aria-label={`${t("ui.palette")}: ${t(paletteLabelKey(palette))}`}
              title={t("ui.palette")}
            >
              <InkIcon name="palette" size={18} />
            </button>

            {user ? (
              <button
                type="button"
                className={styles.iconButton}
                onClick={async () => {
                  await logout();
                  router.replace("/login");
                }}
                title={t("auth.logout")}
                aria-label={t("auth.logout")}
              >
                <InkIcon name="logout" size={18} />
              </button>
            ) : null}
          </div>
        </div>
      </header>

      <div className={styles.body}>
        <aside className={styles.drawerDesktop} aria-label="Sidebar">
          <DrawerContent
            normalizedPathname={normalizedPathname}
            t={t}
            user={user}
            unreadCount={unreadCount}
            palette={palette}
            preference={preference}
            setPalette={setPalette}
            setPreference={setPreference}
            onLogout={async () => {
              await logout();
              router.replace("/login");
            }}
          />
        </aside>

        <main className={styles.main}>
          <div className={styles.mainInner}>{children}</div>
        </main>
      </div>

      {drawerOpen ? (
        <div
          className={styles.drawerOverlay}
          role="presentation"
          onClick={() => setDrawerOpen(false)}
        >
          <aside
            className={styles.drawerMobile}
            aria-label="Navigation Drawer"
            onClick={(e) => e.stopPropagation()}
          >
            <DrawerContent
              normalizedPathname={normalizedPathname}
              t={t}
              user={user}
              unreadCount={unreadCount}
              palette={palette}
              preference={preference}
              setPalette={setPalette}
              setPreference={setPreference}
              onLogout={async () => {
                await logout();
                router.replace("/login");
              }}
              onNavigate={() => setDrawerOpen(false)}
            />
          </aside>
        </div>
      ) : null}
    </div>
  );
}
