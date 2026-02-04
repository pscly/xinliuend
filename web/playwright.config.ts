import { defineConfig, devices } from "@playwright/test";

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
