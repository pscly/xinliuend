import type { TextareaHTMLAttributes } from "react";
import { forwardRef } from "react";

import { cx } from "./cx";
import styles from "./ScrollPaperTextarea.module.css";

export const ScrollPaperTextarea = forwardRef<
  HTMLTextAreaElement,
  { className?: string; mono?: boolean } & TextareaHTMLAttributes<HTMLTextAreaElement>
>(function ScrollPaperTextarea({ className, mono = false, ...props }, ref) {
  return <textarea ref={ref} {...props} className={cx(styles.textarea, mono ? styles.mono : null, className)} />;
});
