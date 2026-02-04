import { AppShell } from "@/features/shell/AppShell";
import { RequireAuth } from "@/lib/auth/guards";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <AppShell>{children}</AppShell>
    </RequireAuth>
  );
}
