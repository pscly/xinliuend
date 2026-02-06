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
  | "page.settings.password.title"
  | "page.settings.password.subtitle"
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
  | "notifications.errorLoad"
  | "notifications.errorMarkRead"
  | "settings.account.title"
  | "settings.account.signedInAs"
  | "settings.account.role"
  | "settings.account.role.admin"
  | "settings.account.role.user"
  | "settings.account.changePassword"
  | "settings.memosMigration.title"
  | "settings.memosMigration.cardTitle"
  | "settings.memosMigration.subtitle"
  | "settings.memosMigration.preview"
  | "settings.memosMigration.previewing"
  | "settings.memosMigration.apply"
  | "settings.memosMigration.applying"
  | "settings.memosMigration.confirmApply"
  | "settings.memosMigration.hint"
  | "settings.memosMigration.warningsTitle"
  | "settings.memosMigration.warningsEmpty"
  | "settings.memosMigration.errorPrefix"
  | "settings.memosMigration.errorGeneric"
  | "settings.memosMigration.previewResult"
  | "settings.memosMigration.applyResult"
  | "settings.memosMigration.memosBaseUrlPrefix"
  | "settings.memosMigration.summary.remoteTotal"
  | "settings.memosMigration.summary.create"
  | "settings.memosMigration.summary.update"
  | "settings.memosMigration.summary.delete"
  | "settings.memosMigration.summary.conflicts"
  | "settings.offline.title"
  | "settings.offline.cardTitle"
  | "settings.offline.subtitle"
  | "settings.offline.toggleLabel"
  | "settings.offline.status.title"
  | "settings.offline.status.online"
  | "settings.offline.status.offline"
  | "settings.offline.status.syncing"
  | "settings.offline.status.pending"
  | "settings.offline.status.lastSync"
  | "settings.offline.status.never"
  | "settings.offline.actions.syncNow"
  | "settings.offline.actions.clearCache"
  | "settings.offline.confirmClearCache"
  | "settings.admin.title"
  | "settings.admin.subtitle"
  | "settings.admin.openAppAdmin"
  | "settings.admin.openBackendAdmin"
  | "settings.admin.page.description"
  | "settings.admin.page.backToSettings"
  | "settings.password.form.title"
  | "settings.password.current"
  | "settings.password.new"
  | "settings.password.confirm"
  | "settings.password.hint"
  | "settings.password.submit"
  | "settings.password.submitting"
  | "settings.password.back"
  | "settings.password.success"
  | "settings.password.errorInvalidCurrent"
  | "settings.password.errorMismatch"
  | "settings.password.errorGeneric"
  | "settings.password.errorNetwork"
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
  | "ui.language"
  | "common.loading"
  | "common.loadingDots"
  | "common.refresh"
  | "common.reload"
  | "common.open"
  | "common.error"
  | "common.done"
  | "common.mark"
  | "common.new"
  | "common.create"
  | "common.creating"
  | "common.save"
  | "common.saving"
  | "common.saved"
  | "common.apply"
  | "common.copy"
  | "common.copied"
  | "common.placeholder"
  | "common.tip"
  | "common.untitled"
  | "common.empty"
  | "home.quickLinks.title"
  | "home.quickLinks.subtitle"
  | "home.quickLinks.notes.subtitle"
  | "home.quickLinks.todos.subtitle"
  | "home.quickLinks.calendar.subtitle"
  | "home.quickLinks.search.subtitle"
  | "home.quickLinks.settings.subtitle"
  | "home.today.title"
  | "home.today.failedPrefix"
  | "home.today.noOccurrences"
  | "home.today.overrideWarning"
  | "home.today.showingPrefix"
  | "home.recentNotes.title"
  | "home.recentNotes.failedPrefix"
  | "home.recentNotes.empty"
  | "search.query.label"
  | "search.query.placeholder"
  | "search.query.placeholderTagActive"
  | "search.tag.label"
  | "search.tag.placeholder"
  | "search.tag.clear"
  | "search.tag.modeHint"
  | "search.active.prefix"
  | "search.active.tagPrefix"
  | "search.active.queryPrefix"
  | "search.tip"
  | "search.section.notes"
  | "search.section.todos"
  | "search.subtitle.error"
  | "search.empty.notes"
  | "search.empty.todos"
  | "search.tag.filterByTagTitlePrefix"
  | "todos.list.label"
  | "todos.list.none"
  | "todos.lists.loadFailedPrefix"
  | "todos.list.new.label"
  | "todos.list.new.placeholder"
  | "todos.list.new.create"
  | "todos.items.titleFallback"
  | "todos.items.loading"
  | "todos.items.countUnit"
  | "todos.items.loadFailedPrefix"
  | "todos.item.new.label"
  | "todos.item.new.placeholder"
  | "todos.item.new.placeholderNoList"
  | "todos.item.new.add"
  | "todos.item.new.adding"
  | "todos.item.recurring.daily"
  | "todos.item.recurring.days"
  | "todos.items.empty"
  | "todos.item.recurring"
  | "todos.item.oneOff"
  | "calendar.range.prefix"
  | "calendar.range.to"
  | "calendar.empty"
  | "calendar.action.titleMarkDone"
  | "calendar.action.titleMarkUndone"
  | "calendar.footer.hint"
  | "notes.untitled"
  | "notes.sidebar.itemsUnit"
  | "notes.editor.title"
  | "notes.editor.noSelection"
  | "notes.editor.mode.markdown"
  | "notes.editor.mode.rich"
  | "notes.editor.previewToggle"
  | "notes.rich.bold"
  | "notes.rich.italic"
  | "notes.rich.link"
  | "notes.rich.list"
  | "notes.rich.code"
  | "notes.rich.codeBlock"
  | "notes.rich.previewPlainText"
  | "notes.share.title"
  | "notes.share.subtitle"
  | "notes.share.create"
  | "notes.share.recreate"
  | "notes.share.copy"
  | "notes.share.copyFailed"
  | "notes.conflict.title"
  | "notes.conflict.subtitle"
  | "notes.conflict.useServer"
  | "notes.textarea.placeholderNoSelection"
  | "notes.footer.tip"
  | "notes.error.loadNotes"
  | "notes.error.loadNote"
  | "notes.error.createNote"
  | "notes.error.saveNote"
  | "notes.error.notAuthorizedPrefix"
  | "notes.error.notAuthorizedGeneric"
  | "notes.error.createSharePrefix"
  | "notes.error.createShareGeneric"
  | "notes.error.shareResponseInvalid"
  | "notes.error.createShareLink"
  | "notes.newNoteTemplate"
  | "notes.link.placeholderText"
  | "share.header.title"
  | "share.header.tokenPrefix"
  | "share.header.openHint"
  | "share.missingToken.title"
  | "share.missingToken.subtitle"
  | "share.note.updatedPrefix"
  | "share.note.body"
  | "share.note.attachments"
  | "share.note.download"
  | "share.title.fallback"
  | "share.error.invalidOrRevoked"
  | "share.error.expired"
  | "share.error.invalidResponse"
  | "share.error.failedLoadShare"
  | "share.error.failedLoadComments"
  | "share.error.commentsDisabled"
  | "share.error.captchaRequired"
  | "share.error.failedPostComment"
  | "share.error.uploadInvalidResponse"
  | "share.error.uploadFailed"
  | "share.error.reportFailed"
  | "share.comment.sectionTitle"
  | "share.comment.writeTitle"
  | "share.comment.field.nameOptional"
  | "share.comment.field.message"
  | "share.comment.field.captchaToken"
  | "share.comment.placeholder.anonymous"
  | "share.comment.placeholder.message"
  | "share.comment.attachHint"
  | "share.comment.post"
  | "share.comment.posting"
  | "share.comment.reload"
  | "share.comment.none"
  | "share.comment.folded"
  | "share.comment.report"
  | "share.comment.reasonPrefix"
  | "share.upload.sectionTitle"
  | "share.upload.uploadedTitle"
  | "share.upload.upload"
  | "share.upload.uploading";

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
  "page.home.subtitle": "在这里管理你的笔记、待办、日历与通知。",
  "page.login.title": "登录",
  "page.login.subtitle": "使用账号密码建立会话（Cookie + CSRF）。",
  "page.notes.title": "笔记",
  "page.todos.title": "待办",
  "page.calendar.title": "日历",
  "page.search.title": "搜索",
  "page.settings.title": "设置",
  "page.settings.admin.title": "管理区",
  "page.settings.admin.subtitle": "仅管理员可访问的用户端管理功能。",
  "page.settings.password.title": "修改密码",
  "page.settings.password.subtitle": "修改后端账号密码，并同步更新 Memos 密码。",
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
  "notifications.errorLoad": "加载通知失败。",
  "notifications.errorMarkRead": "标记已读失败。",
  "settings.account.title": "账号",
  "settings.account.signedInAs": "当前用户",
  "settings.account.role": "角色",
  "settings.account.role.admin": "管理员",
  "settings.account.role.user": "普通用户",
  "settings.account.changePassword": "修改密码",
  "settings.memosMigration.title": "数据迁移",
  "settings.memosMigration.cardTitle": "从 Memos 迁移笔记",
  "settings.memosMigration.subtitle": "将 Memos 中的笔记拉取到当前后端（仅拉取，不会写回 Memos）。",
  "settings.memosMigration.preview": "预览变更（不写入）",
  "settings.memosMigration.previewing": "预览中…",
  "settings.memosMigration.apply": "确认执行迁移",
  "settings.memosMigration.applying": "执行中…",
  "settings.memosMigration.confirmApply": "确定要执行迁移吗？这会把 Memos 的更新覆盖到本地，并可能生成冲突快照。",
  "settings.memosMigration.hint": "建议先预览：执行迁移后，本地会按 Memos 最新内容更新；若覆盖本地修改，会保留冲突快照（可在冲突列表中查看）。",
  "settings.memosMigration.warningsTitle": "注意事项",
  "settings.memosMigration.warningsEmpty": "无",
  "settings.memosMigration.errorPrefix": "迁移失败：",
  "settings.memosMigration.errorGeneric": "请求失败，请稍后重试。",
  "settings.memosMigration.previewResult": "预览结果（预计）",
  "settings.memosMigration.applyResult": "执行结果（实际）",
  "settings.memosMigration.memosBaseUrlPrefix": "Memos 地址：",
  "settings.memosMigration.summary.remoteTotal": "远端条目",
  "settings.memosMigration.summary.create": "将新增",
  "settings.memosMigration.summary.update": "将更新",
  "settings.memosMigration.summary.delete": "将删除",
  "settings.memosMigration.summary.conflicts": "冲突快照",
  "settings.offline.title": "离线与同步",
  "settings.offline.cardTitle": "本地缓存与后台同步",
  "settings.offline.subtitle": "可选：在浏览器端缓存数据，并后台增量同步（适合弱网/断网场景）。",
  "settings.offline.toggleLabel": "启用本地缓存与后台同步",
  "settings.offline.status.title": "同步状态",
  "settings.offline.status.online": "在线",
  "settings.offline.status.offline": "离线",
  "settings.offline.status.syncing": "同步中…",
  "settings.offline.status.pending": "待同步",
  "settings.offline.status.lastSync": "上次同步",
  "settings.offline.status.never": "从未",
  "settings.offline.actions.syncNow": "立即同步",
  "settings.offline.actions.clearCache": "清空本地缓存",
  "settings.offline.confirmClearCache": "确定要清空本地缓存吗？这不会删除服务端数据。",
  "settings.admin.title": "管理",
  "settings.admin.subtitle": "管理入口（仅管理员可见）。",
  "settings.admin.openAppAdmin": "打开应用管理区",
  "settings.admin.openBackendAdmin": "打开后端 /admin",
  "settings.admin.page.description": "这里是用户端的管理区（/settings/admin）。后端的 /admin 使用自己的登录体系，因此仅提供外链入口。",
  "settings.admin.page.backToSettings": "返回设置",
  "settings.password.form.title": "修改密码",
  "settings.password.current": "当前密码",
  "settings.password.new": "新密码",
  "settings.password.confirm": "确认新密码",
  "settings.password.hint": "要求：至少 6 位；为了兼容 Memos 密码规则（+x），UTF-8 不能超过 71 字节。",
  "settings.password.submit": "保存",
  "settings.password.submitting": "保存中…",
  "settings.password.back": "返回设置",
  "settings.password.success": "密码修改成功。",
  "settings.password.errorInvalidCurrent": "当前密码错误。",
  "settings.password.errorMismatch": "两次输入的新密码不一致。",
  "settings.password.errorGeneric": "修改失败，请稍后重试。",
  "settings.password.errorNetwork": "网络错误或服务不可用，请稍后重试。",
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
  "common.loading": "加载中…",
  "common.loadingDots": "加载中...",
  "common.refresh": "刷新",
  "common.reload": "重新加载",
  "common.open": "打开",
  "common.error": "错误",
  "common.done": "完成",
  "common.mark": "标记",
  "common.new": "新建",
  "common.create": "创建",
  "common.creating": "创建中…",
  "common.save": "保存",
  "common.saving": "保存中…",
  "common.saved": "已保存",
  "common.apply": "应用",
  "common.copy": "复制",
  "common.copied": "已复制",
  "common.placeholder": "占位",
  "common.tip": "提示",
  "common.untitled": "(无标题)",
  "common.empty": "(空)",
  "home.quickLinks.title": "快捷入口",
  "home.quickLinks.subtitle": "快速进入",
  "home.quickLinks.notes.subtitle": "写作、回顾、标签",
  "home.quickLinks.todos.subtitle": "清单 + 重复",
  "home.quickLinks.calendar.subtitle": "重复预览",
  "home.quickLinks.search.subtitle": "笔记 + 待办",
  "home.quickLinks.settings.subtitle": "账号 + 同步",
  "home.today.title": "今天（Asia/Shanghai）",
  "home.today.failedPrefix": "加载今日失败：",
  "home.today.noOccurrences": "今天没有需要展示的重复事项。",
  "home.today.overrideWarning": "部分覆盖项加载失败，已尽量展示可用结果。",
  "home.today.showingPrefix": "仅展示前 10 条：",
  "home.recentNotes.title": "最近笔记",
  "home.recentNotes.failedPrefix": "加载笔记失败：",
  "home.recentNotes.empty": "暂无笔记。",
  "search.query.label": "搜索",
  "search.query.placeholder": "搜索笔记 + 待办",
  "search.query.placeholderTagActive": "（已启用标签过滤）",
  "search.tag.label": "标签过滤",
  "search.tag.placeholder": "输入标签（可选）",
  "search.tag.clear": "清除标签过滤",
  "search.tag.modeHint": "标签模式会同时对笔记与待办按标签查询。",
  "search.active.prefix": "当前：",
  "search.active.tagPrefix": "标签：",
  "search.active.queryPrefix": "关键词：",
  "search.tip": "提示：可直接粘贴 URL 参数，例如 ?q=meeting 或 ?tag=work。",
  "search.section.notes": "笔记",
  "search.section.todos": "待办",
  "search.subtitle.error": "错误",
  "search.empty.notes": "没有匹配的笔记。",
  "search.empty.todos": "没有匹配的待办。",
  "search.tag.filterByTagTitlePrefix": "按标签过滤：",
  "todos.list.label": "待办清单",
  "todos.list.none": "暂无清单",
  "todos.lists.loadFailedPrefix": "加载清单失败：",
  "todos.list.new.label": "新清单名称",
  "todos.list.new.placeholder": "例如：个人",
  "todos.list.new.create": "创建清单",
  "todos.items.titleFallback": "待办事项",
  "todos.items.loading": "加载待办中…",
  "todos.items.countUnit": "项",
  "todos.items.loadFailedPrefix": "加载待办失败：",
  "todos.item.new.label": "新待办标题",
  "todos.item.new.placeholder": "例如：喝水",
  "todos.item.new.placeholderNoList": "请先创建或选择一个清单",
  "todos.item.new.add": "添加待办",
  "todos.item.new.adding": "添加中…",
  "todos.item.recurring.daily": "设为每日重复",
  "todos.item.recurring.days": "天数",
  "todos.items.empty": "暂无待办。",
  "todos.item.recurring": "重复",
  "todos.item.oneOff": "单次",
  "calendar.range.prefix": "范围（Asia/Shanghai）：",
  "calendar.range.to": "至",
  "calendar.empty": "暂无发生项",
  "calendar.action.titleMarkDone": "标记为已完成",
  "calendar.action.titleMarkUndone": "标记为未完成",
  "calendar.footer.hint": "仅展示重复待办的发生项；只有存在覆盖项时才可删除覆盖。",
  "notes.untitled": "无标题",
  "notes.sidebar.itemsUnit": "条",
  "notes.editor.title": "编辑器",
  "notes.editor.noSelection": "未选择笔记",
  "notes.editor.mode.markdown": "Markdown",
  "notes.editor.mode.rich": "富文本",
  "notes.editor.previewToggle": "预览",
  "notes.rich.bold": "加粗",
  "notes.rich.italic": "斜体",
  "notes.rich.link": "链接",
  "notes.rich.list": "列表",
  "notes.rich.code": "代码",
  "notes.rich.codeBlock": "代码块",
  "notes.rich.previewPlainText": "预览（纯文本）",
  "notes.share.title": "分享",
  "notes.share.subtitle": "为该笔记创建一个公开链接。",
  "notes.share.create": "创建分享链接",
  "notes.share.recreate": "重新生成链接",
  "notes.share.copy": "复制链接",
  "notes.share.copyFailed": "复制失败，请手动复制链接。",
  "notes.conflict.title": "冲突",
  "notes.conflict.subtitle": "你的保存与服务器上的新版本发生冲突。",
  "notes.conflict.useServer": "使用服务器版本",
  "notes.textarea.placeholderNoSelection": "从左侧选择一条笔记，或先新建一条。",
  "notes.footer.tip": "提示：/notes?id=<note_id>",
  "notes.error.loadNotes": "加载笔记列表失败。",
  "notes.error.loadNote": "加载笔记失败。",
  "notes.error.createNote": "创建笔记失败。",
  "notes.error.saveNote": "保存笔记失败。",
  "notes.error.notAuthorizedPrefix": "无权限：",
  "notes.error.notAuthorizedGeneric": "无权限，请重新登录。",
  "notes.error.createSharePrefix": "创建分享失败：",
  "notes.error.createShareGeneric": "创建分享失败。",
  "notes.error.shareResponseInvalid": "分享创建成功，但返回内容不符合预期。",
  "notes.error.createShareLink": "创建分享链接失败。",
  "notes.newNoteTemplate": "# 新笔记\n\n",
  "notes.link.placeholderText": "文字",
  "share.header.title": "公开分享",
  "share.header.tokenPrefix": "令牌：",
  "share.header.openHint": "打开分享链接以查看笔记。",
  "share.missingToken.title": "缺少 token",
  "share.missingToken.subtitle": "此页面需要在 URL 中提供 share token。例如：",
  "share.note.updatedPrefix": "更新于：",
  "share.note.body": "正文",
  "share.note.attachments": "附件",
  "share.note.download": "下载",
  "share.title.fallback": "分享的笔记",
  "share.error.invalidOrRevoked": "该分享链接无效或已被撤销。",
  "share.error.expired": "该分享链接已过期。",
  "share.error.invalidResponse": "分享内容返回格式无效。",
  "share.error.failedLoadShare": "加载分享失败。",
  "share.error.failedLoadComments": "加载评论失败。",
  "share.error.commentsDisabled": "该分享已禁用匿名评论。",
  "share.error.captchaRequired": "需要验证码令牌：请粘贴后重试。",
  "share.error.failedPostComment": "发表评论失败。",
  "share.error.uploadInvalidResponse": "上传成功但返回内容无效。",
  "share.error.uploadFailed": "上传失败。",
  "share.error.reportFailed": "举报失败。",
  "share.comment.sectionTitle": "评论",
  "share.comment.writeTitle": "发表评论",
  "share.comment.field.nameOptional": "称呼（可选）",
  "share.comment.field.message": "内容",
  "share.comment.field.captchaToken": "验证码令牌（如需要）",
  "share.comment.placeholder.anonymous": "匿名",
  "share.comment.placeholder.message": "友善一点：不支持 HTML 渲染。",
  "share.comment.attachHint": "将附加所选附件到本条评论。",
  "share.comment.post": "发布评论",
  "share.comment.posting": "提交中...",
  "share.comment.reload": "重新加载评论",
  "share.comment.none": "暂无评论。",
  "share.comment.folded": "已折叠",
  "share.comment.report": "举报",
  "share.comment.reasonPrefix": "原因：",
  "share.upload.sectionTitle": "上传（可选）",
  "share.upload.uploadedTitle": "已上传（选择后可在下一条评论中附加）",
  "share.upload.upload": "上传",
  "share.upload.uploading": "上传中...",
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
  "page.settings.password.title": "Change password",
  "page.settings.password.subtitle": "Update your backend password and sync Memos password.",
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
  "notifications.errorLoad": "Failed to load notifications.",
  "notifications.errorMarkRead": "Failed to mark notification read.",
  "settings.account.title": "Account",
  "settings.account.signedInAs": "Signed in as",
  "settings.account.role": "Role",
  "settings.account.role.admin": "Admin",
  "settings.account.role.user": "User",
  "settings.account.changePassword": "Change password",
  "settings.memosMigration.title": "Data migration",
  "settings.memosMigration.cardTitle": "Migrate notes from Memos",
  "settings.memosMigration.subtitle": "Pull memos into this backend (pull-only; never writes back to Memos).",
  "settings.memosMigration.preview": "Preview (dry-run)",
  "settings.memosMigration.previewing": "Previewing…",
  "settings.memosMigration.apply": "Apply migration",
  "settings.memosMigration.applying": "Applying…",
  "settings.memosMigration.confirmApply": "Proceed with migration? This may overwrite local notes and create conflict snapshots.",
  "settings.memosMigration.hint": "Preview first. The migration pulls the latest content from Memos; overwrites preserve conflict snapshots for later review.",
  "settings.memosMigration.warningsTitle": "Warnings",
  "settings.memosMigration.warningsEmpty": "None",
  "settings.memosMigration.errorPrefix": "Migration failed: ",
  "settings.memosMigration.errorGeneric": "Request failed. Please try again.",
  "settings.memosMigration.previewResult": "Preview (planned)",
  "settings.memosMigration.applyResult": "Result (applied)",
  "settings.memosMigration.memosBaseUrlPrefix": "Memos URL: ",
  "settings.memosMigration.summary.remoteTotal": "Remote total",
  "settings.memosMigration.summary.create": "Create",
  "settings.memosMigration.summary.update": "Update",
  "settings.memosMigration.summary.delete": "Delete",
  "settings.memosMigration.summary.conflicts": "Conflicts",
  "settings.offline.title": "Offline & Sync",
  "settings.offline.cardTitle": "Offline cache and background sync",
  "settings.offline.subtitle": "Optional: cache data in the browser and keep it in sync in the background (helps in bad networks).",
  "settings.offline.toggleLabel": "Enable offline cache and background sync",
  "settings.offline.status.title": "Sync status",
  "settings.offline.status.online": "Online",
  "settings.offline.status.offline": "Offline",
  "settings.offline.status.syncing": "Syncing…",
  "settings.offline.status.pending": "Pending",
  "settings.offline.status.lastSync": "Last sync",
  "settings.offline.status.never": "Never",
  "settings.offline.actions.syncNow": "Sync now",
  "settings.offline.actions.clearCache": "Clear offline cache",
  "settings.offline.confirmClearCache": "Clear offline cache? This does not delete server data.",
  "settings.admin.title": "Admin",
  "settings.admin.subtitle": "Admin entry points.",
  "settings.admin.openAppAdmin": "Open app admin",
  "settings.admin.openBackendAdmin": "Open backend /admin",
  "settings.admin.page.description": "This is the user-app admin area (/settings/admin). The backend /admin has its own login, so we only provide an external link.",
  "settings.admin.page.backToSettings": "Back to Settings",
  "settings.password.form.title": "Change password",
  "settings.password.current": "Current password",
  "settings.password.new": "New password",
  "settings.password.confirm": "Confirm password",
  "settings.password.hint": "Requirements: 6+ chars. For Memos (+x) compatibility, UTF-8 must be ≤ 71 bytes.",
  "settings.password.submit": "Save",
  "settings.password.submitting": "Saving…",
  "settings.password.back": "Back to Settings",
  "settings.password.success": "Password updated.",
  "settings.password.errorInvalidCurrent": "Current password is incorrect.",
  "settings.password.errorMismatch": "Passwords do not match.",
  "settings.password.errorGeneric": "Update failed. Please try again.",
  "settings.password.errorNetwork": "Network error or service unavailable. Please try again.",
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
  "common.loading": "Loading…",
  "common.loadingDots": "Loading...",
  "common.refresh": "Refresh",
  "common.reload": "Reload",
  "common.open": "Open",
  "common.error": "Error",
  "common.done": "Done",
  "common.mark": "Mark",
  "common.new": "New",
  "common.create": "Create",
  "common.creating": "Creating…",
  "common.save": "Save",
  "common.saving": "Saving…",
  "common.saved": "Saved",
  "common.apply": "Apply",
  "common.copy": "Copy",
  "common.copied": "Copied",
  "common.placeholder": "Placeholder",
  "common.tip": "Tip",
  "common.untitled": "(Untitled)",
  "common.empty": "(empty)",
  "home.quickLinks.title": "Quick links",
  "home.quickLinks.subtitle": "Jump in",
  "home.quickLinks.notes.subtitle": "Write, review, tag",
  "home.quickLinks.todos.subtitle": "Lists + recurring",
  "home.quickLinks.calendar.subtitle": "Recurring preview",
  "home.quickLinks.search.subtitle": "Notes + todos",
  "home.quickLinks.settings.subtitle": "Account + sync",
  "home.today.title": "Today (Asia/Shanghai)",
  "home.today.failedPrefix": "Failed to load today: ",
  "home.today.noOccurrences": "No recurring occurrences for today.",
  "home.today.overrideWarning": "Some overrides failed to load. Showing best-effort results.",
  "home.today.showingPrefix": "Showing 10 / ",
  "home.recentNotes.title": "Recent notes",
  "home.recentNotes.failedPrefix": "Failed to load notes: ",
  "home.recentNotes.empty": "No notes yet.",
  "search.query.label": "Search",
  "search.query.placeholder": "Search notes + todos",
  "search.query.placeholderTagActive": "(Tag filter active)",
  "search.tag.label": "Tag filter",
  "search.tag.placeholder": "Type tag (optional)",
  "search.tag.clear": "Clear tag filter",
  "search.tag.modeHint": "Tag mode uses tag endpoints for both notes and todos.",
  "search.active.prefix": "Active: ",
  "search.active.tagPrefix": "Tag: ",
  "search.active.queryPrefix": "Query: ",
  "search.tip": "Tip: paste a URL like ?q=meeting or ?tag=work.",
  "search.section.notes": "Notes",
  "search.section.todos": "Todos",
  "search.subtitle.error": "Error",
  "search.empty.notes": "No matching notes.",
  "search.empty.todos": "No matching todos.",
  "search.tag.filterByTagTitlePrefix": "Filter by tag: ",
  "todos.list.label": "Todo list",
  "todos.list.none": "No lists",
  "todos.lists.loadFailedPrefix": "Failed to load lists: ",
  "todos.list.new.label": "New list name",
  "todos.list.new.placeholder": "e.g. Personal",
  "todos.list.new.create": "Create list",
  "todos.items.titleFallback": "Todo items",
  "todos.items.loading": "Loading items…",
  "todos.items.countUnit": "items",
  "todos.items.loadFailedPrefix": "Failed to load items: ",
  "todos.item.new.label": "New item title",
  "todos.item.new.placeholder": "e.g. Drink water",
  "todos.item.new.placeholderNoList": "Create/select a list first",
  "todos.item.new.add": "Add item",
  "todos.item.new.adding": "Adding…",
  "todos.item.recurring.daily": "Create as daily recurring",
  "todos.item.recurring.days": "Days",
  "todos.items.empty": "No items yet.",
  "todos.item.recurring": "Recurring",
  "todos.item.oneOff": "One-off",
  "calendar.range.prefix": "Range (Asia/Shanghai): ",
  "calendar.range.to": "to",
  "calendar.empty": "No occurrences",
  "calendar.action.titleMarkDone": "Mark occurrence done",
  "calendar.action.titleMarkUndone": "Mark occurrence undone",
  "calendar.footer.hint": "Showing recurring todo occurrences only. Override deletion only applies when an override exists.",
  "notes.untitled": "Untitled",
  "notes.sidebar.itemsUnit": "items",
  "notes.editor.title": "Editor",
  "notes.editor.noSelection": "No note selected",
  "notes.editor.mode.markdown": "Markdown",
  "notes.editor.mode.rich": "Rich",
  "notes.editor.previewToggle": "Preview",
  "notes.rich.bold": "Bold",
  "notes.rich.italic": "Italic",
  "notes.rich.link": "Link",
  "notes.rich.list": "List",
  "notes.rich.code": "Code",
  "notes.rich.codeBlock": "Code Block",
  "notes.rich.previewPlainText": "Preview (plain text)",
  "notes.share.title": "Share",
  "notes.share.subtitle": "Create a public link for this note.",
  "notes.share.create": "Create share link",
  "notes.share.recreate": "Recreate link",
  "notes.share.copy": "Copy link",
  "notes.share.copyFailed": "Copy failed. Please copy the URL manually.",
  "notes.conflict.title": "Conflict",
  "notes.conflict.subtitle": "Your save conflicted with a newer server version.",
  "notes.conflict.useServer": "Use server version",
  "notes.textarea.placeholderNoSelection": "Select a note from the list, or create a new one.",
  "notes.footer.tip": "Tip: /notes?id=<note_id>",
  "notes.error.loadNotes": "Failed to load notes.",
  "notes.error.loadNote": "Failed to load note.",
  "notes.error.createNote": "Failed to create note.",
  "notes.error.saveNote": "Failed to save note.",
  "notes.error.notAuthorizedPrefix": "Not authorized: ",
  "notes.error.notAuthorizedGeneric": "Not authorized. Please log in again.",
  "notes.error.createSharePrefix": "Failed to create share: ",
  "notes.error.createShareGeneric": "Failed to create share.",
  "notes.error.shareResponseInvalid": "Share created but response is invalid.",
  "notes.error.createShareLink": "Failed to create share link.",
  "notes.newNoteTemplate": "# New note\n\n",
  "notes.link.placeholderText": "text",
  "share.header.title": "Public Share",
  "share.header.tokenPrefix": "Token: ",
  "share.header.openHint": "Open a share link to view a note.",
  "share.missingToken.title": "Missing token",
  "share.missingToken.subtitle": "This page expects a share token in the URL. Example:",
  "share.note.updatedPrefix": "Updated: ",
  "share.note.body": "Body",
  "share.note.attachments": "Attachments",
  "share.note.download": "Download",
  "share.title.fallback": "Shared note",
  "share.error.invalidOrRevoked": "This share link is invalid or has been revoked.",
  "share.error.expired": "This share link has expired.",
  "share.error.invalidResponse": "Invalid share response",
  "share.error.failedLoadShare": "Failed to load share.",
  "share.error.failedLoadComments": "Failed to load comments.",
  "share.error.commentsDisabled": "Anonymous comments are disabled for this share.",
  "share.error.captchaRequired": "Captcha token required. Paste it in the field above and retry.",
  "share.error.failedPostComment": "Failed to post comment.",
  "share.error.uploadInvalidResponse": "Upload succeeded but response is invalid.",
  "share.error.uploadFailed": "Upload failed.",
  "share.error.reportFailed": "Failed to report comment.",
  "share.comment.sectionTitle": "Comments",
  "share.comment.writeTitle": "Write a comment",
  "share.comment.field.nameOptional": "Name (optional)",
  "share.comment.field.message": "Message",
  "share.comment.field.captchaToken": "Captcha token (if required)",
  "share.comment.placeholder.anonymous": "Anonymous",
  "share.comment.placeholder.message": "Be kind. No HTML is rendered.",
  "share.comment.attachHint": "Attaching selected files to this comment.",
  "share.comment.post": "Post comment",
  "share.comment.posting": "Posting...",
  "share.comment.reload": "Reload comments",
  "share.comment.none": "No comments yet.",
  "share.comment.folded": "Folded",
  "share.comment.report": "Report",
  "share.comment.reasonPrefix": "Reason: ",
  "share.upload.sectionTitle": "Upload (optional)",
  "share.upload.uploadedTitle": "Uploaded (select to attach in next comment)",
  "share.upload.upload": "Upload",
  "share.upload.uploading": "Uploading...",
};

export const MESSAGES_BY_LOCALE: Record<AppLocale, Messages> = {
  "zh-CN": zhCN,
  en,
};
