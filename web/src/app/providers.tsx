"use client";

import type { ReactNode } from "react";

import { AuthProvider } from "@/lib/auth/AuthProvider";
import { I18nProvider } from "@/lib/i18n/I18nProvider";
import { ThemeProvider } from "@/lib/theme/ThemeProvider";
import { InkDialogProvider } from "@/features/ui/dialogs/InkDialogProvider";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <I18nProvider>
        <InkDialogProvider>
          <AuthProvider>{children}</AuthProvider>
        </InkDialogProvider>
      </I18nProvider>
    </ThemeProvider>
  );
}
