"use client";

import { useCallback, useEffect, useState } from "react";

import { getOfflineEnabled, setOfflineEnabled, subscribeOfflineEnabled } from "./offlineSettings";

export function useOfflineEnabled(): {
  offlineEnabled: boolean;
  updateOfflineEnabled: (next: boolean) => void;
} {
  const [offlineEnabled, setOfflineEnabledState] = useState<boolean>(() => {
    if (typeof window === "undefined") return true;
    return getOfflineEnabled();
  });

  useEffect(() => {
    // Keep in sync with storage/custom events.
    return subscribeOfflineEnabled(() => {
      setOfflineEnabledState(getOfflineEnabled());
    });
  }, []);

  const updateOfflineEnabled = useCallback((next: boolean) => {
    setOfflineEnabled(next);
    setOfflineEnabledState(next);
  }, []);

  return { offlineEnabled, updateOfflineEnabled };
}
