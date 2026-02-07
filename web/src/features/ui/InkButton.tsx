import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from "react";
import Link from "next/link";

import { cx } from "./cx";
import styles from "./InkButton.module.css";

export type InkButtonVariant = "surface" | "ghost" | "primary";
export type InkButtonSize = "sm" | "md";

type BaseProps = {
  variant?: InkButtonVariant;
  size?: InkButtonSize;
  pill?: boolean;
  className?: string;
  children: ReactNode;
};

export function InkButton({
  variant = "surface",
  size = "md",
  pill = false,
  className,
  children,
  ...props
}: BaseProps & ButtonHTMLAttributes<HTMLButtonElement>) {
  const disabled = Boolean(props.disabled);
  return (
    <button
      {...props}
      data-disabled={disabled ? "1" : undefined}
      className={cx(
        styles.button,
        size === "sm" ? styles.sizeSm : styles.sizeMd,
        variant === "primary" ? styles.variantPrimary : variant === "ghost" ? styles.variantGhost : styles.variantSurface,
        pill ? styles.pill : null,
        className
      )}
    >
      {children}
    </button>
  );
}

export function InkLink({
  href,
  variant = "ghost",
  size = "md",
  pill = false,
  className,
  children,
  ...props
}: BaseProps & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & { href: string }) {
  return (
    <Link
      href={href}
      className={cx(
        styles.button,
        size === "sm" ? styles.sizeSm : styles.sizeMd,
        variant === "primary" ? styles.variantPrimary : variant === "ghost" ? styles.variantGhost : styles.variantSurface,
        pill ? styles.pill : null,
        className
      )}
      {...props}
    >
      {children}
    </Link>
  );
}

