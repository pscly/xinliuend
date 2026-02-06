import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

function makeUniqueUsername(): string {
  // Backend restricts usernames to alphanumeric only.
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 10);
  return `pw${ts}${rand}`.replace(/[^A-Za-z0-9]/g, "").slice(0, 64);
}

async function registerUserViaApi(page: Page, username: string, password: string) {
  // Establish an origin for relative fetch() calls.
  await page.goto("/login");

  // Create a fresh user inside the browser context.
  const registerResult = await page.evaluate(async ({ username, password }) => {
    const resp = await fetch("/api/v1/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ username, password }),
    });

    // Keep json loosely typed but avoid explicit `any`.
    let json: Record<string, unknown> | null = null;
    try {
      json = await resp.json();
    } catch {
      // ignore
    }
    return { status: resp.status, json };
  }, { username, password });

  expect(registerResult.status, `register status=${registerResult.status}`).toBe(200);
  expect(
    typeof registerResult.json?.token,
    `register response=${JSON.stringify(registerResult.json)}`,
  ).toBe("string");

  // Register endpoint sets an authenticated cookie-session; clear it so we can validate UI login.
  await page.context().clearCookies();
}

async function loginViaUi(page: Page, username: string, password: string) {
  await page.goto("/login");
  await expect(page).toHaveURL(/\/login\/?$/);
  await page.locator('input[autocomplete="username"]').fill(username);
  await page.locator('input[autocomplete="current-password"]').fill(password);

  const submit = page.locator('button[type="submit"]');
  await expect(submit).toBeEnabled();

  const loginRespPromise = page.waitForResponse(
    (resp) => resp.request().method() === "POST" && /\/api\/v1\/auth\/login$/.test(resp.url()),
  );
  const meRespPromise = page.waitForResponse(
    (resp) => resp.request().method() === "GET" && /\/api\/v1\/me$/.test(resp.url()) && resp.status() === 200,
  );

  await submit.click();
  const loginResp = await loginRespPromise;
  expect(loginResp.status(), `login status=${loginResp.status()}`).toBe(200);
  await meRespPromise;

  // Login page may use trailing slashes; just ensure we've left /login.
  await page.waitForURL((url) => !/\/login\/?$/.test(url.pathname));
}

test("admin gate: non-admin cannot access /settings/admin", async ({ page }) => {
  const username = makeUniqueUsername();
  const password = "pass1234";

  await registerUserViaApi(page, username, password);
  await loginViaUi(page, username, password);

  // /settings should not show any admin entry link to non-admins.
  await page.goto("/settings");
  await expect(page).toHaveURL(/\/settings\/?$/);
  // Ensure page has hydrated with the authenticated user.
  await expect(page.getByRole("main").getByText(username, { exact: true })).toBeVisible();
  await expect(page.getByTestId("settings-admin-link")).toHaveCount(0);

  // Visiting /settings/admin as non-admin should redirect to dashboard.
  await page.goto("/settings/admin");
  await page.waitForURL((url) => !/\/settings\/admin\/?$/.test(url.pathname));
  expect(new URL(page.url()).pathname).toBe("/");
  await expect(page.getByText(/^(Quick links|\u5feb\u6377\u5165\u53e3)$/)).toBeVisible();
  await expect(page.getByTestId("settings-admin-page")).toHaveCount(0);
});
