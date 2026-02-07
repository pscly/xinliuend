"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cx } from "./cx";
import styles from "./SealFab.module.css";

export function SealFab({
  glyph = "记",
  hint,
  className,
  ...props
}: {
  glyph?: string;
  hint?: ReactNode;
  className?: string;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  const disabled = Boolean(props.disabled);
  return (
    <button
      {...props}
      data-disabled={disabled ? "1" : undefined}
      className={cx(styles.fab, className)}
    >
      <span className={styles.glyph}>{glyph}</span>
      {hint ? <span className={styles.hint}>{hint}</span> : null}
    </button>
  );
}

