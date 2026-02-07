import type { ReactNode } from "react";

import { cx } from "./cx";
import styles from "./InkCard.module.css";

export type InkCardVariant = "surface" | "surface2";

export function InkCard({
  variant = "surface",
  elevated = false,
  interactive = false,
  selected = false,
  className,
  children,
  ...props
}: {
  variant?: InkCardVariant;
  elevated?: boolean;
  interactive?: boolean;
  selected?: boolean;
  className?: string;
  children: ReactNode;
} & React.HTMLAttributes<HTMLElement>) {
  return (
    <section
      {...props}
      className={cx(
        styles.card,
        variant === "surface2" ? styles.variantSurface2 : null,
        elevated ? styles.elevated : null,
        interactive ? styles.interactive : null,
        selected ? styles.selected : null,
        className
      )}
    >
      {children}
    </section>
  );
}

export function InkCardHeader({
  title,
  subtitle,
  right,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx(styles.header, className)}>
      <div className={styles.headerText}>
        <div className={styles.title}>{title}</div>
        {subtitle ? <div className={styles.subtitle}>{subtitle}</div> : null}
      </div>
      {right ? <div>{right}</div> : null}
    </div>
  );
}

export function InkCardBody({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cx(styles.body, className)}>{children}</div>;
}

export function InkCardFooter({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cx(styles.footer, className)}>{children}</div>;
}

