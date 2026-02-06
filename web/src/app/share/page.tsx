import { Suspense } from "react";

import ShareClient from "./ShareClient";

export default function SharePage() {
  return (
    <Suspense
      fallback={
        <div style={{ minHeight: "100vh", padding: "28px 16px 60px", color: "var(--color-text-muted)" }}>
          加载中...
        </div>
      }
    >
      <ShareClient />
    </Suspense>
  );
}
