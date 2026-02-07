"use client";

import { useCallback, useEffect, useState } from "react";

import {
  getMemosFeedEnabled,
  setMemosFeedEnabled,
  subscribeMemosFeedEnabled,
} from "./memosFeedSettings";

export function useMemosFeedEnabled(): {
  memosFeedEnabled: boolean;
  updateMemosFeedEnabled: (next: boolean) => void;
} {
  const [memosFeedEnabled, setMemosFeedEnabledState] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return getMemosFeedEnabled();
  });

  useEffect(() => {
    return subscribeMemosFeedEnabled(() => {
      setMemosFeedEnabledState(getMemosFeedEnabled());
    });
  }, []);

  const updateMemosFeedEnabled = useCallback((next: boolean) => {
    setMemosFeedEnabled(next);
    setMemosFeedEnabledState(next);
  }, []);

  return { memosFeedEnabled, updateMemosFeedEnabled };
}
