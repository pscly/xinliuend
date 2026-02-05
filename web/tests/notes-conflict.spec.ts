import { expect, test } from "@playwright/test";

function makeUniqueUsername(): string {
  // Backend restricts usernames to alphanumeric only.
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 10);
  return `pw${ts}${rand}`.replace(/[^A-Za-z0-9]/g, "").slice(0, 64);
}

test("notes: 409 conflict -> use server version", async ({ page }) => {
  const username = makeUniqueUsername();
  const password = "pass1234";

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

    type RegisterJson = null | { token?: unknown; [key: string]: unknown };
    let json: RegisterJson = null;
    try {
      json = (await resp.json()) as RegisterJson;
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

  // Create and save an initial note.
  await page.goto("/notes");
  await expect(page).toHaveURL(/\/notes/);
  const newButton = page.getByRole("button", { name: /^New$/ });
  const saveButton = page.getByRole("button", { name: /^Save$/ });
  const editor = page.locator("textarea");

  await expect(newButton).toBeVisible();
  await newButton.click();

  await expect(page).toHaveURL(/\/notes\/?\?id=/);
  const noteId = await page.evaluate(() => {
    return new URLSearchParams(window.location.search).get("id");
  });
  if (!noteId) {
    throw new Error("Expected note id in location.search (?id=...)");
  }

  const initialBody = [
    "# Initial body",
    "",
    `user: ${username}`,
    `ts: ${Date.now()}`,
  ].join("\n");
  await expect(editor).toBeVisible();
  await editor.fill(initialBody);

  await expect(saveButton).toBeEnabled();
  await saveButton.click();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();

  // Force a newer server version by PATCHing with a future timestamp.
  const serverBody = [
    "# Server body",
    "",
    "This is the server snapshot.",
    `noteId: ${noteId}`,
    `ts: ${Date.now()}`,
  ].join("\n");
  const futureClientUpdatedAtMs = Date.now() + 600_000;

  const forceServerResult = await page.evaluate(async ({ noteId, serverBody, futureClientUpdatedAtMs }) => {
    // Do not use Playwright request context: we want browser cookies included.
    const meResp = await fetch("/api/v1/me", { method: "GET", credentials: "include" });
    const meJson = await meResp.json().catch(() => null);
    const csrfToken: string | null = typeof meJson?.csrf_token === "string" ? meJson.csrf_token : null;

    const patchResp = await fetch(`/api/v1/notes/${noteId}`, {
      method: "PATCH",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
      },
      body: JSON.stringify({ body_md: serverBody, client_updated_at_ms: futureClientUpdatedAtMs }),
    });

    const patchJson = await patchResp.json().catch(() => null);
    return {
      meStatus: meResp.status,
      patchStatus: patchResp.status,
      patchJson,
    };
  }, { noteId, serverBody, futureClientUpdatedAtMs });

  expect(forceServerResult.meStatus, `me status=${forceServerResult.meStatus}`).toBe(200);
  expect(forceServerResult.patchStatus, `server patch status=${forceServerResult.patchStatus} body=${JSON.stringify(forceServerResult.patchJson)}`).toBe(200);

  // Make a local edit so Save is enabled, then attempt to save with normal Date.now().
  const localBody = `${initialBody}\n\nLocal edit ${Date.now()}`;
  await editor.fill(localBody);
  await expect(saveButton).toBeEnabled();

  const conflictRespPromise = page.waitForResponse(
    (resp) => resp.request().method() === "PATCH" && resp.url().endsWith(`/api/v1/notes/${noteId}`),
  );
  await saveButton.click();
  const conflictResp = await conflictRespPromise;
  expect(conflictResp.status(), `conflict status=${conflictResp.status()}`).toBe(409);

  // Assert conflict UI and the resolution action.
  await expect(page.getByText("Conflict", { exact: true })).toBeVisible();
  const useServerButton = page.getByRole("button", { name: "Use server version" });
  await expect(useServerButton).toBeVisible();

  // Clicking should replace the textarea with the server snapshot body.
  await useServerButton.click();
  await expect(editor).toHaveValue(serverBody);
});
