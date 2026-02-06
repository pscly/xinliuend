import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

type AppTheme = "light" | "dark" | "system";

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

async function registerViaContextRequest(
  context: import("@playwright/test").BrowserContext,
  username: string,
  password: string,
) {
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

async function waitForAppShell(page: import("@playwright/test").Page) {
  // The nav uses a stable aria-label (not localized).
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
}

async function waitForPageHeading(page: import("@playwright/test").Page) {
  // Each authenticated page uses <Page> which renders an <h1>.
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
}

async function createNoteAndShareUrl(page: import("@playwright/test").Page, noteContent: string): Promise<string> {
  await page.goto("/notes");
  await expect(page).toHaveURL(/\/notes/);
  await waitForAppShell(page);
  await waitForPageHeading(page);

  const newButton = page.getByTestId("notes-new");
  await expect(newButton).toBeVisible();
  await newButton.click();

  // Wait until the new note is actually created/selected.
  await expect(page).toHaveURL(/\/notes\/?\?id=/);

  const editor = page.locator("textarea");
  await expect(editor).toBeVisible();
  await editor.fill(noteContent);

  // Optional: persist the note so the share page has realistic content.
  const saveButton = page.getByTestId("notes-save");
  await expect(saveButton).toBeEnabled();
  await saveButton.click();
  await expect(page.getByText(/^(Saved|\u5df2\u4fdd\u5b58)$/)).toBeVisible();

  const createShare = page.getByTestId("create-share");
  await expect(createShare).toBeEnabled();
  await createShare.click();

  const shareUrlInput = page.getByTestId("share-url");
  await expect(shareUrlInput).toBeVisible();

  const shareUrl = await shareUrlInput.inputValue();
  expect(shareUrl, "share url should include token").toMatch(/\/share\?token=/);
  return shareUrl;
}

async function screenshot(page: import("@playwright/test").Page, filename: string) {
  ensureEvidenceDirExists();
  await page.screenshot({ path: evidencePath(filename), fullPage: true });
}

async function runEvidenceSet(
  opts: {
    theme: Exclude<AppTheme, "system">;
    filenames: {
      dashboard: string;
      notes: string;
      todos: string;
      extra1: string;
      extra2: string;
    };
  },
  { browser }: { browser: import("@playwright/test").Browser },
  testInfo: import("@playwright/test").TestInfo,
) {
  ensureEvidenceDirExists();

  // Playwright's `TestProject.use` typing is not always specific enough here.
  const baseURL = (testInfo.project.use as unknown as { baseURL?: string }).baseURL;
  const context = await browser.newContext({ baseURL });
  await context.addInitScript(
    ({ themeValue }: { themeValue: Exclude<AppTheme, "system"> }) => {
      window.localStorage.setItem("theme-preference", themeValue);
    },
    { themeValue: opts.theme },
  );

  const username = makeUniqueUsername();
  const password = "pass1234";

  // Register via BrowserContext request so Set-Cookie is stored.
  await registerViaContextRequest(context, username, password);
  await context.clearCookies();

  const page = await context.newPage();
  await loginViaUi(page, username, password);
  await waitForAppShell(page);

  // Dashboard
  await page.goto("/");
  await waitForPageHeading(page);
  await expect(page.getByText("快捷入口", { exact: true })).toBeVisible();
  await screenshot(page, opts.filenames.dashboard);

  // Notes (also generate a share URL for /share evidence).
  const noteContent = `Playwright 证据 ${Date.now()} ${username}`;
  const shareUrl = await createNoteAndShareUrl(page, noteContent);
  await screenshot(page, opts.filenames.notes);

  // Todos
  await page.goto("/todos");
  await waitForPageHeading(page);
  await expect(page.getByText("待办清单", { exact: true })).toBeVisible();
  await screenshot(page, opts.filenames.todos);

  // Extra pages depend on which set we are running.
  if (opts.filenames.extra1.includes("share")) {
    await page.goto(shareUrl);
    await expect(page.getByText("公开分享", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await screenshot(page, opts.filenames.extra1);

    await page.goto("/settings");
    await waitForPageHeading(page);
    // Avoid strict-mode collisions with the header user pill.
    await expect(page.getByRole("main").getByText(username)).toBeVisible();
    await screenshot(page, opts.filenames.extra2);
  } else {
    await page.goto("/notifications");
    await waitForPageHeading(page);
    await expect(page.locator('input[type="checkbox"]').first()).toBeVisible();
    await screenshot(page, opts.filenames.extra1);

    await page.goto("/search");
    await waitForPageHeading(page);
    await expect(page.getByTestId("search-query-input")).toBeVisible();
    await screenshot(page, opts.filenames.extra2);
  }

  await page.close();
  await context.close();
}

test("evidence: pages (zh-CN + light)", async ({ browser }, testInfo) => {
  await runEvidenceSet(
    {
      theme: "light",
      filenames: {
        dashboard: "dashboard-zh-light.png",
        notes: "notes-zh-light.png",
        todos: "todos-zh-light.png",
        extra1: "share-zh-light.png",
        extra2: "settings-zh-light.png",
      },
    },
    { browser },
    testInfo,
  );
});

test("evidence: pages (zh-CN + dark)", async ({ browser }, testInfo) => {
  await runEvidenceSet(
    {
      theme: "dark",
      filenames: {
        dashboard: "dashboard-zh-dark.png",
        notes: "notes-zh-dark.png",
        todos: "todos-zh-dark.png",
        extra1: "notifications-zh-dark.png",
        extra2: "search-zh-dark.png",
      },
    },
    { browser },
    testInfo,
  );
});
