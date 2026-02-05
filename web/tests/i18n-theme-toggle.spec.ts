import { expect, test, type Page } from "@playwright/test";

function makeUniqueUsername(): string {
  // Backend restricts usernames to alphanumeric only.
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 10);
  return `pw${ts}${rand}`.replace(/[^A-Za-z0-9]/g, "").slice(0, 64);
}

async function registerUser(page: Page, username: string, password: string) {
  // Establish an origin for relative fetch() calls.
  await page.goto("/login");

  const registerResult = await page.evaluate(async ({ username, password }) => {
    const resp = await fetch("/api/v1/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ username, password }),
    });

    // Keep json loosely typed but avoid explicit `any` (ESLint no-explicit-any).
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

test("i18n + theme toggles: CN/EN and light/dark persist", async ({ page }) => {
  const username = makeUniqueUsername();
  const password = "pass1234";

  await registerUser(page, username, password);
  await loginViaUi(page, username, password);

  // Land on a shell page with header pills + nav items.
  await page.goto("/notes");
  await expect(page).toHaveURL(/\/notes/);

  const languageToggle = page.getByRole("button", { name: /^(Language|\u8bed\u8a00):/ });
  const themeToggle = page.getByRole("button", { name: /^(Theme|\u4e3b\u9898):/ });
  await expect(languageToggle).toBeVisible();
  await expect(themeToggle).toBeVisible();

  // Theme: system -> light -> dark (attribute on <html> + localStorage persistence).
  await themeToggle.click();
  await page.waitForFunction(() => document.documentElement.dataset.theme === "light");
  await expect(page.evaluate(() => localStorage.getItem("theme-preference"))).resolves.toBe("light");

  await themeToggle.click();
  await page.waitForFunction(() => document.documentElement.dataset.theme === "dark");
  await expect(page.evaluate(() => localStorage.getItem("theme-preference"))).resolves.toBe("dark");

  // Language: toggle and assert the notifications label flips between EN/CN.
  const navNotifications = page.getByTestId("nav-notifications");
  await expect(navNotifications).toBeVisible();

  const EN_LABEL = "Notifications";
  const ZH_LABEL = "\u901a\u77e5";

  const initialLabelText = await navNotifications.innerText();
  const initialIsEn = initialLabelText.includes(EN_LABEL);
  const initialIsZh = initialLabelText.includes(ZH_LABEL);
  expect(
    initialIsEn || initialIsZh,
    `unexpected nav-notifications label: ${JSON.stringify(initialLabelText)}`,
  ).toBeTruthy();

  const expectedAfterLabel = initialIsEn ? ZH_LABEL : EN_LABEL;
  const expectedLocaleAfter = initialIsEn ? "zh-CN" : "en";

  await languageToggle.click();
  await expect(navNotifications).toContainText(expectedAfterLabel);
  await expect(page.evaluate(() => localStorage.getItem("locale"))).resolves.toBe(expectedLocaleAfter);

  // Reload: verify both preferences persist.
  await page.reload();
  await expect(navNotifications).toBeVisible();
  await expect(navNotifications).toContainText(expectedAfterLabel);
  await page.waitForFunction(() => document.documentElement.dataset.theme === "dark");

  const stored = await page.evaluate(() => ({
    theme: localStorage.getItem("theme-preference"),
    locale: localStorage.getItem("locale"),
  }));
  expect(stored).toEqual({ theme: "dark", locale: expectedLocaleAfter });
});
