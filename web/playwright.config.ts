import { defineConfig, devices } from "@playwright/test";

function ensureLocalhostBypassesProxy() {
  const localhostHosts = ["127.0.0.1", "localhost", "::1"];
  const currentValue = (process.env.NO_PROXY ?? process.env.no_proxy ?? "").trim();
  const currentParts = currentValue
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  const merged = Array.from(new Set([...currentParts, ...localhostHosts])).join(",");
  process.env.NO_PROXY = merged;
  process.env.no_proxy = merged;
}

// Playwright 的 webServer 可用性探测使用 Node 请求，默认会受 http_proxy/https_proxy 影响。
// 在当前环境里如果没有配置 NO_PROXY，会导致 127.0.0.1 被代理“假响应”，从而误判服务可用。
ensureLocalhostBypassesProxy();

const backendOrigin = "http://127.0.0.1:31031";

export default defineConfig({
  testDir: "./tests",
  outputDir: "./test-results",
  // SQLite DB used by the Playwright webServer is single-writer; keep E2E deterministic.
  workers: 1,
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: backendOrigin,
    trace: "on-first-retry",
  },
  webServer: {
    // Next `output: "export"` can't run via `next start`; build the static export then
    // start the backend which serves `web/out` on the same origin.
    command:
      "npm run build && uv --directory .. run alembic -c alembic.ini upgrade head && uv --directory .. run uvicorn flow_backend.main:app --host 127.0.0.1 --port 31031",
    url: backendOrigin,
    reuseExistingServer: !process.env.CI,
    timeout: 5 * 60 * 1000,
    env: {
      ...process.env,
      DEV_BYPASS_MEMOS: "true",
      DATABASE_URL: "sqlite:///./playwright-e2e.db",
      // 在部分受限/沙箱环境中，uv 默认缓存目录（~/.cache/uv）可能不可写。
      // 这里显式把缓存写到 /tmp，避免 E2E 在启动阶段因权限失败。
      UV_CACHE_DIR: "/tmp/uv-cache",
      // E2E determinism: parallel auth flows can trip 429 + contend on SQLite.
      // Disabling these is safe here because it only affects the Playwright-launched server.
      AUTH_REGISTER_RATE_LIMIT_PER_IP: "0",
      AUTH_LOGIN_RATE_LIMIT_PER_IP: "0",
      AUTH_LOGIN_RATE_LIMIT_PER_IP_USER: "0",
      ADMIN_LOGIN_RATE_LIMIT_PER_IP: "0",
      // Avoid background DB writes that can overlap requests on SQLite.
      DEVICE_TRACKING_ASYNC: "false",
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
