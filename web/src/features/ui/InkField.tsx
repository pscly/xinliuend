import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

import { cx } from "./cx";
import styles from "./InkField.module.css";

function FieldFrame({
  label,
  help,
  error,
  children,
  className,
}: {
  label?: ReactNode;
  help?: ReactNode;
  error?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cx(styles.field, className)}>
      {label ? <span className={styles.label}>{label}</span> : null}
      {children}
      {help ? <span className={styles.help}>{help}</span> : null}
      {error ? <span className={styles.error}>{error}</span> : null}
    </label>
  );
}

export function InkTextField({
  label,
  help,
  error,
  mono = false,
  className,
  inputClassName,
  ...props
}: {
  label?: ReactNode;
  help?: ReactNode;
  error?: ReactNode;
  mono?: boolean;
  className?: string;
  inputClassName?: string;
} & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <FieldFrame label={label} help={help} error={error} className={className}>
      <input {...props} className={cx(styles.control, mono ? styles.mono : null, inputClassName)} />
    </FieldFrame>
  );
}

export function InkSelectField({
  label,
  help,
  error,
  className,
  selectClassName,
  children,
  ...props
}: {
  label?: ReactNode;
  help?: ReactNode;
  error?: ReactNode;
  className?: string;
  selectClassName?: string;
  children: ReactNode;
} & SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <FieldFrame label={label} help={help} error={error} className={className}>
      <select {...props} className={cx(styles.control, selectClassName)}>
        {children}
      </select>
    </FieldFrame>
  );
}

export function InkTextareaField({
  label,
  help,
  error,
  mono = false,
  className,
  textareaClassName,
  ...props
}: {
  label?: ReactNode;
  help?: ReactNode;
  error?: ReactNode;
  mono?: boolean;
  className?: string;
  textareaClassName?: string;
} & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <FieldFrame label={label} help={help} error={error} className={className}>
      <textarea {...props} className={cx(styles.control, styles.textarea, mono ? styles.mono : null, textareaClassName)} />
    </FieldFrame>
  );
}

