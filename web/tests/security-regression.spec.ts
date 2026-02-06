import { expect, test } from "@playwright/test";

function makeUniqueUsername(): string {
  // Backend restricts usernames to alphanumeric only.
  const ts = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 10);
  return `pw${ts}${rand}`.replace(/[^A-Za-z0-9]/g, "").slice(0, 64);
}

function expectNonNull<T>(v: T | null | undefined, message: string): asserts v is T {
  expect(v, message).not.toBeNull();
  expect(v, message).not.toBeUndefined();
}

async function registerViaBrowserFetch(page: import("@playwright/test").Page, username: string, password: string) {
  // Establish an origin for relative fetch() calls.
  await page.goto("/login");

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

async function createNote(page: import("@playwright/test").Page, noteBody: string): Promise<string> {
  await page.goto("/notes");
  await expect(page).toHaveURL(/\/notes/);

  const newButton = page.getByTestId("notes-new");
  const saveButton = page.getByTestId("notes-save");
  const editor = page.locator("textarea");

  await expect(newButton).toBeVisible();
  await newButton.click();

  await expect(page).toHaveURL(/\/notes\/?\?id=/);
  await expect(editor).toBeVisible();

  const noteId = await page.evaluate(() => new URLSearchParams(window.location.search).get("id"));
  if (!noteId) throw new Error("Expected note id in location.search (?id=...)");

  await editor.fill(noteBody);
  await expect(saveButton).toBeEnabled();
  await saveButton.click();
  await expect(page.getByText(/^(Saved|\u5df2\u4fdd\u5b58)$/)).toBeVisible();

  return noteId;
}

async function createShareViaUi(page: import("@playwright/test").Page, noteId: string) {
  const shareCreateRespPromise = page.waitForResponse(
    (resp) =>
      resp.request().method() === "POST" &&
      resp.url().includes(`/api/v1/notes/${noteId}/shares`) &&
      (resp.status() === 201 || resp.status() === 200),
  );

  await page.getByTestId("create-share").click();
  const shareCreateResp = await shareCreateRespPromise;

  const json = (await shareCreateResp.json().catch(() => null)) as unknown;
  if (!json || typeof json !== "object") {
    throw new Error(`Share create returned invalid JSON: ${JSON.stringify(json)}`);
  }

  const shareId = (json as { share_id?: unknown }).share_id;
  const shareUrl = (json as { share_url?: unknown }).share_url;
  expect(typeof shareId, `share_id type=${typeof shareId}`).toBe("string");
  expect(typeof shareUrl, `share_url type=${typeof shareUrl}`).toBe("string");
  expectNonNull(shareId as string | null, "share_id present");
  expectNonNull(shareUrl as string | null, "share_url present");

  await expect(page.getByTestId("share-url")).toHaveValue(shareUrl as string);
  const shareUrlAbs = (shareUrl as string).startsWith("http") ? (shareUrl as string) : new URL(shareUrl as string, page.url()).toString();
  return { shareId: shareId as string, shareUrlAbs };
}

async function enableAnonymousCommentsNoCaptcha(page: import("@playwright/test").Page, shareId: string) {
  const patchConfigResult = await page.evaluate(async ({ shareId }) => {
    const meResp = await fetch("/api/v1/me", { method: "GET", credentials: "include" });
    const meJson: unknown = await meResp.json().catch(() => null);
    const csrfToken: string | null =
      typeof meJson === "object" &&
      meJson !== null &&
      "csrf_token" in meJson &&
      typeof (meJson as { csrf_token?: unknown }).csrf_token === "string"
        ? (meJson as { csrf_token: string }).csrf_token
        : null;

    const resp = await fetch(`/api/v1/shares/${shareId}/comment-config`, {
      method: "PATCH",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
      },
      body: JSON.stringify({ allow_anonymous_comments: true, anonymous_comments_require_captcha: false }),
    });
    const json: unknown = await resp.json().catch(() => null);
    return { meStatus: meResp.status, status: resp.status, json };
  }, { shareId });

  expect(patchConfigResult.meStatus, `me status=${patchConfigResult.meStatus}`).toBe(200);
  expect(
    patchConfigResult.status,
    `comment-config status=${patchConfigResult.status} body=${JSON.stringify(patchConfigResult.json)}`,
  ).toBe(200);
}

test.describe("security regression", () => {
  test("stored-XSS: share comment body is rendered as text (no <img>)", async ({ page, browser }) => {
    const username = makeUniqueUsername();
    const password = "pass1234";
    const xss = `<img src=x onerror=alert(1)>`;

    await registerViaBrowserFetch(page, username, password);
    await page.context().clearCookies();
    await loginViaUi(page, username, password);

    const noteId = await createNote(page, `# Share seed\nuser: ${username}\n${Date.now()}`);
    const { shareId, shareUrlAbs } = await createShareViaUi(page, noteId);
    await enableAnonymousCommentsNoCaptcha(page, shareId);

    const anonContext = await browser.newContext();
    const anonPage = await anonContext.newPage();
    await anonPage.goto(shareUrlAbs);

    const commentBox = anonPage.getByTestId("share-comment-body");
    await expect(commentBox).toBeVisible();

    const postCommentRespPromise = anonPage.waitForResponse(
      (resp) => resp.request().method() === "POST" && /\/api\/v1\/public\/shares\/.+\/comments$/.test(resp.url()),
    );
    await commentBox.fill(xss);
    await anonPage.getByTestId("share-post-comment").click();
    const postResp = await postCommentRespPromise;
    expect([200, 201], `post comment status=${postResp.status()}`).toContain(postResp.status());

    const commentCard = anonPage.locator("article", { hasText: xss }).first();
    await expect(commentCard).toBeVisible();
    await expect(commentCard.locator("pre")).toContainText(xss);
    await expect(commentCard.locator("img")).toHaveCount(0);

    await anonContext.close();
  });

  test("stored-XSS: notes preview does not render HTML (no <img>)", async ({ page }) => {
    const username = makeUniqueUsername();
    const password = "pass1234";
    const xss = `<img src=x onerror=alert(1)>`;

    await registerViaBrowserFetch(page, username, password);
    await page.context().clearCookies();
    await loginViaUi(page, username, password);

    await page.goto("/notes");
    await expect(page).toHaveURL(/\/notes/);

    const newButton = page.getByTestId("notes-new");
    const richButton = page.getByRole("button", { name: /^(Rich|\u5bcc\u6587\u672c)$/ });
    const editor = page.locator("textarea");
    await expect(newButton).toBeVisible();
    await newButton.click();
    await expect(page).toHaveURL(/\/notes\/?\?id=/);
    await expect(editor).toBeVisible();

    const noteBody = [`# XSS preview regression`, `user: ${username}`, `payload: ${xss}`].join("\n");
    await editor.fill(noteBody);

    await expect(richButton).toBeVisible();
    await richButton.click();

    const previewCheckbox = page.getByRole("checkbox", { name: /^(Preview|\u9884\u89c8)$/ });
    await previewCheckbox.check();

    const previewHeading = page.getByText(/^(Preview \(plain text\)|\u9884\u89c8\uff08\u7eaf\u6587\u672c\uff09)$/);
    await expect(previewHeading).toBeVisible();
    const previewPane = previewHeading.locator("..");
    await expect(previewPane.locator("pre")).toContainText(noteBody);
    await expect(previewPane.locator("img")).toHaveCount(0);
  });

  test("CSRF: cookie-session POST without X-CSRF-Token is rejected (403)", async ({ page }) => {
    const username = makeUniqueUsername();
    const password = "pass1234";

    await registerViaBrowserFetch(page, username, password);
    await page.context().clearCookies();
    await loginViaUi(page, username, password);

    const noteId = await createNote(page, `# CSRF regression\nuser: ${username}\n${Date.now()}`);

    const result = await page.evaluate(async ({ noteId }) => {
      const resp = await fetch(`/api/v1/notes/${encodeURIComponent(noteId)}/shares`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          // Intentionally omit X-CSRF-Token.
        },
        credentials: "include",
        body: JSON.stringify({}),
      });
      return { status: resp.status, text: await resp.text().catch(() => "") };
    }, { noteId });

    expect(result.status, `expected 403, got ${result.status} body=${result.text}`).toBe(403);
  });
});
