"use client";

import type { ReactNode } from "react";
import { useEffect, useRef } from "react";

import { cx } from "./cx";
import styles from "./InkDialog.module.css";

export function InkDialog({
  open,
  title,
  children,
  footer,
  className,
  onClose,
}: {
  open: boolean;
  title?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open) {
      if (!el.open) {
        try {
          el.showModal();
        } catch {
          // Fallback for browsers without showModal support.
          el.setAttribute("open", "true");
        }
      }
    } else {
      if (el.open) el.close();
    }
  }, [open]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const onCancel = (e: Event) => {
      e.preventDefault();
      onClose();
    };

    const onCloseEvent = () => {
      onClose();
    };

    el.addEventListener("cancel", onCancel);
    el.addEventListener("close", onCloseEvent);
    return () => {
      el.removeEventListener("cancel", onCancel);
      el.removeEventListener("close", onCloseEvent);
    };
  }, [onClose]);

  return (
    <dialog ref={ref} className={cx(styles.dialog, className)}>
      <div className={styles.inner}>
        <div className={styles.header}>
          <div className={styles.title}>{title}</div>
          <button type="button" className={styles.close} onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>

        <div className={styles.body}>{children}</div>

        {footer ? <div className={styles.footer}>{footer}</div> : null}
      </div>
    </dialog>
  );
}

