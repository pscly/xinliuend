import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

function makeUniqueUsername(): string {
  // Backend restricts usernames to alphanumeric only.
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 10);
  return `pw${ts}${rand}`.replace(/[^A-Za-z0-9]/g, "").slice(0, 64);
}

function ensureEvidenceDirExists(): string {
  const dir = path.resolve(process.cwd(), "..", ".sisyphus", "evidence");
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function evidencePath(filename: string): string {
  return path.resolve(process.cwd(), "..", ".sisyphus", "evidence", filename);
}

async function registerViaContextRequest(context: import("@playwright/test").BrowserContext, username: string, password: string) {
  // Use BrowserContext request so Set-Cookie is persisted in the context.
  const resp = await context.request.post("/api/v1/auth/register", {
    data: { username, password },
    headers: { "Content-Type": "application/json" },
  });

  expect(resp.status(), `register status=${resp.status()}`).toBe(200);
  const json = await resp.json().catch(() => null);
  expect(typeof json?.token, `register response=${JSON.stringify(json)}`).toBe("string");
}

async function loginViaUi(page: import("@playwright/test").Page, username: string, password: string) {
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

async function createNoteOpenRichPreview(page: import("@playwright/test").Page, noteContent: string) {
  await page.goto("/notes");
  await expect(page).toHaveURL(/\/notes/);

  const newButton = page.getByTestId("notes-new");
  const saveButton = page.getByTestId("notes-save");
  const richButton = page.getByRole("button", { name: /^(Rich|\u5bcc\u6587\u672c)$/ });
  const editor = page.locator("textarea");

  await expect(newButton).toBeVisible();
  await newButton.click();

  // Wait until the new note is actually created/selected.
  await expect(page).toHaveURL(/\/notes\/?\?id=/);

  await expect(editor).toBeVisible();
  await editor.fill(noteContent);

  await expect(richButton).toBeVisible();
  await richButton.click();

  const previewCheckbox = page.getByRole("checkbox", { name: /^(Preview|\u9884\u89c8)$/ });
  await previewCheckbox.check();
  await expect(page.getByText(/^(Preview \(plain text\)|\u9884\u89c8\uff08\u7eaf\u6587\u672c\uff09)$/)).toBeVisible();
  // Avoid strict-mode ambiguity: noteContent exists in both textarea and preview.
  await expect(page.locator("pre")).toContainText(noteContent);

  // Optional: persist the note so evidence captures a realistic state.
  await expect(saveButton).toBeEnabled();
  await saveButton.click();
  await expect(page.getByText(/^(Saved|\u5df2\u4fdd\u5b58)$/)).toBeVisible();
}

async function runEvidenceFlow(theme: "light" | "dark", screenshotFilename: string, { browser }: { browser: import("@playwright/test").Browser }, testInfo: import("@playwright/test").TestInfo) {
  ensureEvidenceDirExists();

  // Playwright's `TestProject.use` typing is not always specific enough here.
  // Cast via `unknown` to avoid `any` while keeping runtime behavior identical.
  const baseURL = (testInfo.project.use as unknown as { baseURL?: string }).baseURL;
  const context = await browser.newContext({ baseURL });
  await context.addInitScript((themeValue) => {
    window.localStorage.setItem("theme-preference", themeValue);
  }, theme);

  const username = makeUniqueUsername();
  const password = "pass1234";

  // Register via BrowserContext request so Set-Cookie is stored.
  await registerViaContextRequest(context, username, password);
  await context.clearCookies();

  const page = await context.newPage();
  await loginViaUi(page, username, password);

  const noteContent = `Playwright evidence ${Date.now()} ${username}`;
  await createNoteOpenRichPreview(page, noteContent);

  const absPath = evidencePath(screenshotFilename);
  await page.screenshot({ path: absPath, fullPage: true });

  await page.close();
  await context.close();
}

test("evidence: notes editor (light)", async ({ browser }, testInfo) => {
  await runEvidenceFlow("light", "notes-editor-light.png", { browser }, testInfo);
});

test("evidence: notes editor (dark)", async ({ browser }, testInfo) => {
  await runEvidenceFlow("dark", "notes-editor-dark.png", { browser }, testInfo);
});
