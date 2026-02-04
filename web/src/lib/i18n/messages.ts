import type { AppLocale } from "./locales";

export type MessageKey =
  | "app.name"
  | "nav.home"
  | "nav.notes"
  | "nav.todos"
  | "nav.calendar"
  | "nav.search"
  | "nav.notifications"
  | "nav.settings"
  | "page.home.title"
  | "page.home.subtitle"
  | "page.login.title"
  | "page.login.subtitle"
  | "page.notes.title"
  | "page.todos.title"
  | "page.calendar.title"
  | "page.search.title"
  | "page.settings.title"
  | "page.settings.admin.title"
  | "page.settings.admin.subtitle"
  | "page.notifications.title"
  | "page.notifications.subtitle"
  | "notifications.unreadOnly"
  | "notifications.refresh"
  | "notifications.empty"
  | "notifications.openShare"
  | "notifications.markRead"
  | "notifications.read"
  | "notifications.unread"
  | "notifications.marking"
  | "settings.account.title"
  | "settings.account.signedInAs"
  | "settings.account.role"
  | "settings.account.role.admin"
  | "settings.account.role.user"
  | "settings.admin.title"
  | "settings.admin.subtitle"
  | "settings.admin.openAppAdmin"
  | "settings.admin.openBackendAdmin"
  | "settings.admin.page.description"
  | "settings.admin.page.backToSettings"
  | "auth.username"
  | "auth.password"
  | "auth.login"
  | "auth.logout"
  | "auth.username.help"
  | "auth.username.error"
  | "auth.login.error"
  | "ui.theme"
  | "ui.theme.system"
  | "ui.theme.light"
  | "ui.theme.dark"
  | "ui.language";

type Messages = Record<MessageKey, string>;

const zhCN: Messages = {
  "app.name": "心流",
  "nav.home": "首页",
  "nav.notes": "笔记",
  "nav.todos": "待办",
  "nav.calendar": "日历",
  "nav.search": "搜索",
  "nav.notifications": "通知",
  "nav.settings": "设置",
  "page.home.title": "欢迎",
  "page.home.subtitle": "这是用户端前端工程的最小脚手架：i18n + 暗色模式 + Playwright。",
  "page.login.title": "登录",
  "page.login.subtitle": "使用账号密码建立会话（Cookie + CSRF）。",
  "page.notes.title": "笔记",
  "page.todos.title": "待办",
  "page.calendar.title": "日历",
  "page.search.title": "搜索",
  "page.settings.title": "设置",
  "page.settings.admin.title": "管理区",
  "page.settings.admin.subtitle": "仅管理员可访问的用户端管理功能。",
  "page.notifications.title": "通知中心",
  "page.notifications.subtitle": "提及、分享等提醒（支持未读筛选）。",
  "notifications.unreadOnly": "只看未读",
  "notifications.refresh": "刷新",
  "notifications.empty": "暂无通知。",
  "notifications.openShare": "打开分享",
  "notifications.markRead": "标记已读",
  "notifications.read": "已读",
  "notifications.unread": "未读",
  "notifications.marking": "标记中…",
  "settings.account.title": "账号",
  "settings.account.signedInAs": "当前用户",
  "settings.account.role": "角色",
  "settings.account.role.admin": "管理员",
  "settings.account.role.user": "普通用户",
  "settings.admin.title": "管理",
  "settings.admin.subtitle": "管理入口（仅管理员可见）。",
  "settings.admin.openAppAdmin": "打开应用管理区",
  "settings.admin.openBackendAdmin": "打开后端 /admin",
  "settings.admin.page.description": "这里是用户端的管理区（/settings/admin）。后端的 /admin 使用自己的登录体系，因此仅提供外链入口。",
  "settings.admin.page.backToSettings": "返回设置",
  "auth.username": "用户名",
  "auth.password": "密码",
  "auth.login": "登录",
  "auth.logout": "退出登录",
  "auth.username.help": "仅支持字母数字（1-64）。",
  "auth.username.error": "用户名只能包含字母和数字，长度 1-64。",
  "auth.login.error": "登录失败，请检查用户名或密码。",
  "ui.theme": "主题",
  "ui.theme.system": "跟随系统",
  "ui.theme.light": "浅色",
  "ui.theme.dark": "深色",
  "ui.language": "语言",
};

const en: Messages = {
  "app.name": "XinLiu",
  "nav.home": "Home",
  "nav.notes": "Notes",
  "nav.todos": "Todos",
  "nav.calendar": "Calendar",
  "nav.search": "Search",
  "nav.notifications": "Notifications",
  "nav.settings": "Settings",
  "page.home.title": "Welcome",
  "page.home.subtitle": "Minimal user-frontend scaffold: i18n + dark mode + Playwright.",
  "page.login.title": "Sign in",
  "page.login.subtitle": "Start a cookie session (Cookie + CSRF).",
  "page.notes.title": "Notes",
  "page.todos.title": "Todos",
  "page.calendar.title": "Calendar",
  "page.search.title": "Search",
  "page.settings.title": "Settings",
  "page.settings.admin.title": "Admin",
  "page.settings.admin.subtitle": "Admin-only tools inside the user app.",
  "page.notifications.title": "Notification Center",
  "page.notifications.subtitle": "Mentions and updates (with unread filter).",
  "notifications.unreadOnly": "Unread only",
  "notifications.refresh": "Refresh",
  "notifications.empty": "No notifications.",
  "notifications.openShare": "Open share",
  "notifications.markRead": "Mark read",
  "notifications.read": "Read",
  "notifications.unread": "Unread",
  "notifications.marking": "Marking…",
  "settings.account.title": "Account",
  "settings.account.signedInAs": "Signed in as",
  "settings.account.role": "Role",
  "settings.account.role.admin": "Admin",
  "settings.account.role.user": "User",
  "settings.admin.title": "Admin",
  "settings.admin.subtitle": "Admin entry points.",
  "settings.admin.openAppAdmin": "Open app admin",
  "settings.admin.openBackendAdmin": "Open backend /admin",
  "settings.admin.page.description": "This is the user-app admin area (/settings/admin). The backend /admin has its own login, so we only provide an external link.",
  "settings.admin.page.backToSettings": "Back to Settings",
  "auth.username": "Username",
  "auth.password": "Password",
  "auth.login": "Sign in",
  "auth.logout": "Sign out",
  "auth.username.help": "Alphanumeric only (1-64).",
  "auth.username.error": "Username must be alphanumeric, length 1-64.",
  "auth.login.error": "Sign-in failed. Check your username and password.",
  "ui.theme": "Theme",
  "ui.theme.system": "System",
  "ui.theme.light": "Light",
  "ui.theme.dark": "Dark",
  "ui.language": "Language",
};

export const MESSAGES_BY_LOCALE: Record<AppLocale, Messages> = {
  "zh-CN": zhCN,
  en,
};
