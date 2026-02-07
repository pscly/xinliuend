export const MEMOS_FEED_ENABLED_STORAGE_KEY = "memos_feed_enabled";

export function normalizeMemosFeedEnabled(raw: string | null | undefined): boolean {
  const v = (raw ?? "").trim().toLowerCase();
  if (!v) return false;
  if (v === "0" || v === "false" || v === "off" || v === "disabled") return false;
  return true;
}

export function getMemosFeedEnabled(): boolean {
  if (typeof window === "undefined") return false;
  const raw = window.localStorage.getItem(MEMOS_FEED_ENABLED_STORAGE_KEY);
  const enabled = normalizeMemosFeedEnabled(raw);
  if (raw === null) {
    window.localStorage.setItem(MEMOS_FEED_ENABLED_STORAGE_KEY, enabled ? "1" : "0");
  }
  return enabled;
}

export function setMemosFeedEnabled(enabled: boolean): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(MEMOS_FEED_ENABLED_STORAGE_KEY, enabled ? "1" : "0");
  window.dispatchEvent(new Event("memosFeed:enabledChanged"));
}

export function subscribeMemosFeedEnabled(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => undefined;

  const onCustom = () => onChange();
  const onStorage = (e: StorageEvent) => {
    if (e.key !== MEMOS_FEED_ENABLED_STORAGE_KEY) return;
    onChange();
  };

  window.addEventListener("memosFeed:enabledChanged", onCustom);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener("memosFeed:enabledChanged", onCustom);
    window.removeEventListener("storage", onStorage);
  };
}
