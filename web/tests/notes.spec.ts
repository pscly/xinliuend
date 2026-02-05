import { expect, test } from "@playwright/test";

function makeUniqueUsername(): string {
  // Backend restricts usernames to alphanumeric only.
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 10);
  return `pw${ts}${rand}`.replace(/[^A-Za-z0-9]/g, "").slice(0, 64);
}

test("notes: register -> login -> create -> save -> reload persists", async ({ page }) => {
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

  // Navigate to /notes.
  await page.goto("/notes");
  await expect(page).toHaveURL(/\/notes/);
  const newButton = page.getByRole("button", { name: /^New$/ });
  const richButton = page.getByRole("button", { name: /^Rich$/ });
  const saveButton = page.getByRole("button", { name: /^Save$/ });
  const editor = page.locator("textarea");

  await expect(newButton).toBeVisible();
  await newButton.click();

  // Wait until the new note is actually created/selected.
  await expect(page).toHaveURL(/\/notes\/?\?id=/);
  await expect(editor).toHaveValue(/\S/);

  const noteContent = [
    "# Playwright note",
    "",
    `user: ${username}`,
    `ts: ${Date.now()}`,
    "",
    "- item 1",
    "- item 2",
    "",
    "**bold** _italic_",
  ].join("\n");
  await expect(editor).toBeVisible();
  await editor.fill(noteContent);

  // Explicitly switch to Rich mode before saving.
  await expect(richButton).toBeVisible();
  await richButton.click();

  // Optional: enable Preview if the checkbox exists and is stable.
  const previewCheckbox = page.getByRole("checkbox", { name: /preview/i });
  if (await previewCheckbox.isVisible().catch(() => false)) {
    if (!(await previewCheckbox.isChecked())) {
      await previewCheckbox.check();
    }
  }

  await expect(saveButton).toBeEnabled();
  await saveButton.click();
  await expect(page.getByText(/^Saved$/)).toBeVisible();

  // Reload and verify the note persists (URL keeps id=... for selection).
  await expect(page).toHaveURL(/\/notes\/?\?id=/);
  await page.reload();
  await expect(page).toHaveURL(/\/notes\/?\?id=/);
  const markdownButton = page.getByRole("button", { name: /^Markdown$/ });
  if (!(await editor.isVisible().catch(() => false)) && (await markdownButton.isVisible().catch(() => false))) {
    await markdownButton.click();
  }
  await expect(editor).toHaveValue(noteContent);
});
