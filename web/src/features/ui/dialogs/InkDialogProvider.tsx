"use client";

import type { ReactNode } from "react";
import { createContext, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { InkButton, type InkButtonVariant } from "@/features/ui/InkButton";
import { InkDialog } from "@/features/ui/InkDialog";
import { useI18n } from "@/lib/i18n/useI18n";

export type ConfirmOptions = {
  title?: ReactNode;
  message: ReactNode;
  confirmText?: string;
  cancelText?: string;
  confirmVariant?: InkButtonVariant;
  cancelVariant?: InkButtonVariant;
  confirmTestId?: string;
  cancelTestId?: string;
};

export type InkDialogApi = {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
};

export const InkDialogContext = createContext<InkDialogApi | null>(null);

type ConfirmRequest = {
  id: number;
  options: ConfirmOptions;
  resolve: (value: boolean) => void;
};

export function InkDialogProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n();

  const queueRef = useRef<ConfirmRequest[]>([]);
  const nextIdRef = useRef<number>(1);

  const activeRef = useRef<ConfirmRequest | null>(null);
  const [active, setActive] = useState<ConfirmRequest | null>(null);
  const [open, setOpen] = useState<boolean>(false);

  // Avoid double-resolving from <dialog> close/cancel events.
  const closingRef = useRef<boolean>(false);
  const timerRef = useRef<number | null>(null);

  const showNext = useCallback(() => {
    const next = queueRef.current.shift() ?? null;
    activeRef.current = next;
    closingRef.current = false;
    setActive(next);
    setOpen(Boolean(next));
  }, []);

  const confirm = useCallback(
    (options: ConfirmOptions) => {
      const id = nextIdRef.current++;
      return new Promise<boolean>((resolve) => {
        queueRef.current.push({ id, options, resolve });
        if (!activeRef.current && !closingRef.current) {
          showNext();
        }
      });
    },
    [showNext],
  );

  const closeActive = useCallback(
    (result: boolean) => {
      const req = activeRef.current;
      if (!req) return;
      if (closingRef.current) return;
      closingRef.current = true;

      setOpen(false);

      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
      }

      // Let <dialog> close before resolving and showing the next one.
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null;
        req.resolve(result);
        activeRef.current = null;
        showNext();
      }, 0);
    },
    [showNext],
  );

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }

      const activeReq = activeRef.current;
      if (activeReq) activeReq.resolve(false);

      for (const req of queueRef.current) {
        req.resolve(false);
      }
      queueRef.current = [];
      activeRef.current = null;
    };
  }, []);

  const value = useMemo<InkDialogApi>(() => ({ confirm }), [confirm]);

  const options = active?.options ?? null;
  const title = options?.title ?? t("common.confirm");
  const message = options?.message ?? null;
  const confirmText = options?.confirmText ?? t("common.confirm");
  const cancelText = options?.cancelText ?? t("common.cancel");
  const confirmVariant = options?.confirmVariant ?? "primary";
  const cancelVariant = options?.cancelVariant ?? "surface";
  const confirmTestId = options?.confirmTestId ?? "ink-confirm-ok";
  const cancelTestId = options?.cancelTestId ?? "ink-confirm-cancel";

  return (
    <InkDialogContext.Provider value={value}>
      {children}

      <InkDialog
        open={open}
        title={title}
        onClose={() => {
          closeActive(false);
        }}
        footer={
          <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10, flexWrap: "wrap" }}>
            <InkButton type="button" size="sm" variant={cancelVariant} onClick={() => closeActive(false)} data-testid={cancelTestId}>
              {cancelText}
            </InkButton>
            <InkButton type="button" size="sm" variant={confirmVariant} onClick={() => closeActive(true)} data-testid={confirmTestId}>
              {confirmText}
            </InkButton>
          </div>
        }
      >
        {message}
      </InkDialog>
    </InkDialogContext.Provider>
  );
}

