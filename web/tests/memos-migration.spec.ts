import { expect, test, type Page } from "@playwright/test";

function makeUniqueUsername(): string {
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 10);
  return `pw${ts}${rand}`.replace(/[^A-Za-z0-9]/g, "").slice(0, 64);
}

async function registerUser(page: Page, username: string, password: string) {
  await page.goto("/login");
  const registerResult = await page.evaluate(async ({ username, password }) => {
    const resp = await fetch("/api/v1/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ username, password }),
    });

    let json: Record<string, unknown> | null = null;
    try {
      json = await resp.json();
    } catch {
      // ignore
    }
    return { status: resp.status, json };
  }, { username, password });

  expect(registerResult.status, `register status=${registerResult.status}`).toBe(200);
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
  await submit.click();
  const loginResp = await loginRespPromise;
  expect(loginResp.status(), `login status=${loginResp.status()}`).toBe(200);
  await page.waitForURL((url) => !/\/login\/?$/.test(url.pathname));
}

test("设置页：Memos 迁移预览与确认执行", async ({ page }) => {
  const username = makeUniqueUsername();
  const password = "pass1234";

  await registerUser(page, username, password);
  await loginViaUi(page, username, password);

  await page.route("**/api/v1/memos/migration/preview", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        kind: "preview",
        summary: {
          remote_total: 3,
          created_local: 1,
          updated_local_from_remote: 1,
          deleted_local_from_remote: 0,
          conflicts: 1,
        },
        memos_base_url: "https://memos.example.com",
        warnings: [],
      }),
    });
  });

  await page.route("**/api/v1/memos/migration/apply", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        kind: "apply",
        summary: {
          remote_total: 3,
          created_local: 1,
          updated_local_from_remote: 1,
          deleted_local_from_remote: 0,
          conflicts: 1,
        },
        memos_base_url: "https://memos.example.com",
        warnings: [],
      }),
    });
  });

  await page.goto("/settings");
  await expect(page).toHaveURL(/\/settings/);

  const previewBtn = page.getByTestId("settings-memos-preview");
  const applyBtn = page.getByTestId("settings-memos-apply");

  await expect(previewBtn).toBeVisible();
  await expect(applyBtn).toBeVisible();
  await expect(applyBtn).toBeDisabled();

  await previewBtn.click();
  const summary = page.getByTestId("settings-memos-summary");
  await expect(summary).toBeVisible();
  await expect(summary).toContainText("预览结果");
  await expect(summary).toContainText("远端条目");
  await expect(summary).toContainText("3");

  await expect(applyBtn).toBeEnabled();

  await applyBtn.click();
  const confirmOk = page.getByTestId("ink-confirm-ok");
  await expect(confirmOk).toBeVisible();
  await confirmOk.click();
  await expect(page.getByText("执行结果")).toBeVisible();
});
