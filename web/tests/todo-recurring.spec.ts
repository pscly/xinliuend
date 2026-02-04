import { expect, test } from "@playwright/test";

function makeUniqueUsername(): string {
  // Backend restricts usernames to alphanumeric only.
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 10);
  return `pw${ts}${rand}`.replace(/[^A-Za-z0-9]/g, "").slice(0, 64);
}

function makeUniqueLabel(prefix: string): string {
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 8);
  return `${prefix}-${ts}-${rand}`;
}

test("todos: recurring daily occurrences render + mark done persists", async ({ page }) => {
  const username = makeUniqueUsername();
  const password = "pass1234";

  const listName = makeUniqueLabel("pw-list");
  const itemTitle = makeUniqueLabel("pw-recurring");
  const days = 7;

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
    let json: ({ code?: number } & Record<string, unknown>) | null = null;
    try {
      json = await resp.json();
    } catch {
      // ignore
    }
    return { status: resp.status, json };
  }, { username, password });

  expect(registerResult.status, `register status=${registerResult.status}`).toBe(200);
  expect(registerResult.json?.code, `register response=${JSON.stringify(registerResult.json)}`).toBe(200);

  // Register endpoint sets an authenticated cookie-session; clear it so we can validate UI login.
  await page.context().clearCookies();

  // Login via UI at /login.
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

  // Go to /todos and create a list + recurring item.
  await page.goto("/todos");
  await expect(page).toHaveURL(/\/todos/);
  const todoListSelect = page.getByLabel("Todo list");
  await expect(todoListSelect).toBeVisible();

  await page.getByLabel("New list name").fill(listName);
  await page.getByRole("button", { name: /^Create list$/ }).click();
  const listOption = page.getByRole("option", { name: listName });
  await expect(listOption).toHaveCount(1);
  const listId = await listOption.getAttribute("value");
  expect(listId, "created list option has value").not.toBeNull();
  await expect(todoListSelect).toHaveValue(listId);

  await page.getByLabel("New item title").fill(itemTitle);
  await page.getByRole("checkbox", { name: /^Create as daily recurring$/ }).check();
  await page.getByLabel("Days").fill(String(days));

  const addItemRespPromise = page.waitForResponse(
    (resp) => resp.request().method() === "POST" && /\/api\/v1\/todo\/items\b/.test(resp.url()) && resp.status() === 200,
  );
  await page.getByRole("button", { name: /^Add item$/ }).click();
  await addItemRespPromise;
  await expect(page.getByText(itemTitle, { exact: true })).toBeVisible();

  // Go to /calendar and verify the 7-day range shows 7 occurrences.
  const calItemsRespPromise = page.waitForResponse(
    (resp) => resp.request().method() === "GET" && /\/api\/v1\/todo\/items\b/.test(resp.url()) && resp.status() === 200,
  );
  const calOccRespPromise = page.waitForResponse(
    (resp) => resp.request().method() === "GET" && /\/api\/v1\/todo\/occurrences\b/.test(resp.url()) && resp.status() === 200,
  );
  await page.goto("/calendar");
  await expect(page).toHaveURL(/\/calendar/);
  await Promise.all([calItemsRespPromise, calOccRespPromise]);
  await expect(page.getByText(/Showing recurring todo occurrences only\./)).toBeVisible();

  const titleNodes = page.getByTitle(itemTitle);
  await expect(titleNodes).toHaveCount(days);

  // Mark one occurrence done and verify UI updates.
  const markOccRespPromise = page.waitForResponse(
    (resp) => resp.request().method() === "POST" && /\/api\/v1\/todo\/occurrences\b/.test(resp.url()) && resp.status() === 200,
  );
  const firstMarkButton = titleNodes.first().locator("..").locator("..").getByRole("button", { name: /^Mark$/ });
  await expect(firstMarkButton).toBeEnabled();
  await firstMarkButton.click();
  await markOccRespPromise;

  const doneButtonsForTitle = titleNodes.locator("..").locator("..").getByRole("button", { name: /^Done$/ });
  await expect(doneButtonsForTitle).toHaveCount(1);

  // Reload /calendar and verify done state persists (exactly 1 Done for this title).
  await page.reload();
  await expect(page).toHaveURL(/\/calendar/);
  await expect(page.getByTitle(itemTitle)).toHaveCount(days);
  const doneButtonsForTitleAfterReload = page
    .getByTitle(itemTitle)
    .locator("..")
    .locator("..")
    .getByRole("button", { name: /^Done$/ });
  await expect(doneButtonsForTitleAfterReload).toHaveCount(1);
});
