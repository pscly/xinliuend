export const OFFLINE_ENABLED_STORAGE_KEY = "offline_enabled";

export function normalizeOfflineEnabled(raw: string | null | undefined): boolean {
  const v = (raw ?? "").trim().toLowerCase();
  if (!v) return true; // 默认启用（可在设置中关闭）
  if (v === "0" || v === "false" || v === "off" || v === "disabled") return false;
  return true;
}

export function getOfflineEnabled(): boolean {
  if (typeof window === "undefined") return true;
  const raw = window.localStorage.getItem(OFFLINE_ENABLED_STORAGE_KEY);
  const enabled = normalizeOfflineEnabled(raw);
  if (raw === null) {
    window.localStorage.setItem(OFFLINE_ENABLED_STORAGE_KEY, enabled ? "1" : "0");
  }
  return enabled;
}

export function setOfflineEnabled(enabled: boolean): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(OFFLINE_ENABLED_STORAGE_KEY, enabled ? "1" : "0");
  // 说明：除了 storage 事件（跨 tab），这里额外发一个自定义事件，便于当前 tab 立即响应。
  window.dispatchEvent(new Event("offline:enabledChanged"));
}

export function subscribeOfflineEnabled(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => undefined;

  const onCustom = () => onChange();
  const onStorage = (e: StorageEvent) => {
    if (e.key !== OFFLINE_ENABLED_STORAGE_KEY) return;
    onChange();
  };

  window.addEventListener("offline:enabledChanged", onCustom);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener("offline:enabledChanged", onCustom);
    window.removeEventListener("storage", onStorage);
  };
}

