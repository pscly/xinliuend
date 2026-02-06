"use client";

import type { ReactNode } from "react";

import type { MessageKey } from "@/lib/i18n/messages";
import { useI18n } from "@/lib/i18n/useI18n";

import styles from "./Page.module.css";

export function Page({ titleKey, subtitleKey, children }: { titleKey: MessageKey; subtitleKey?: MessageKey; children?: ReactNode }) {
  const { t } = useI18n();
  return (
    <div className={styles.page}>
      <section className={styles.card}>
        <div className={styles.cardInner}>
          <h1 className={styles.title}>{t(titleKey)}</h1>
          {subtitleKey ? <p className={styles.subtitle}>{t(subtitleKey)}</p> : null}
        </div>
        {children}
      </section>
    </div>
  );
}

export function SkeletonBlocks({ count = 3 }: { count?: number }) {
  const { t } = useI18n();
  const blocks = Array.from({ length: count }, (_, i) => i);
  return (
    <div className={styles.grid}>
      {blocks.map((i) => (
        <div key={i} className={styles.block}>
          <div className={styles.blockTitle}>{t("common.placeholder")}</div>
          <div className={`skeleton ${styles.blockRow}`} style={{ width: "92%" }} />
          <div className={`skeleton ${styles.blockRow}`} style={{ width: "78%" }} />
          <div className={`skeleton ${styles.blockRow}`} style={{ width: "86%" }} />
        </div>
      ))}
    </div>
  );
}
