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

test("notifications: @mention from anonymous share comment", async ({ page, browser }) => {
  const username = makeUniqueUsername();
  const password = "pass1234";
  const mentionKey = `pw-mention-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

  // Establish an origin for relative fetch() calls (required before any page.evaluate(fetch...)).
  await page.goto("/login");

  // 1) Register user A via browser fetch.
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

  // 2) Login as user A via UI at /login.
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
  await page.waitForURL((url) => !/\/login\/?$/.test(url.pathname));

  // 3) Create a note and share link.
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

  await editor.fill(["# Mention seed", `user: ${username}`, `key: ${mentionKey}`].join("\n"));
  await expect(saveButton).toBeEnabled();
  await saveButton.click();
  await expect(page.getByText(/^(Saved|\u5df2\u4fdd\u5b58)$/)).toBeVisible();

  const shareCreateRespPromise = page.waitForResponse(
    (resp) =>
      resp.request().method() === "POST" &&
      resp.url().includes(`/api/v1/notes/${noteId}/shares`) &&
      (resp.status() === 201 || resp.status() === 200),
  );
  await page.getByTestId("create-share").click();
  const shareCreateResp = await shareCreateRespPromise;

  const shareCreateJson = (await shareCreateResp.json().catch(() => null)) as unknown;
  if (!shareCreateJson || typeof shareCreateJson !== "object") {
    throw new Error(`Share create returned invalid JSON: ${JSON.stringify(shareCreateJson)}`);
  }
  const shareId = (shareCreateJson as { share_id?: unknown }).share_id;
  const shareUrl = (shareCreateJson as { share_url?: unknown }).share_url;
  expect(typeof shareId, `share_id type=${typeof shareId}`).toBe("string");
  expect(typeof shareUrl, `share_url type=${typeof shareUrl}`).toBe("string");
  expectNonNull(shareId as string | null, "share_id present");
  expectNonNull(shareUrl as string | null, "share_url present");
  await expect(page.getByTestId("share-url")).toHaveValue(shareUrl as string);

  // 4) Enable anonymous comments (captcha NOT required) via authenticated PATCH.
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
  }, { shareId: shareId as string });

  expect(patchConfigResult.meStatus, `me status=${patchConfigResult.meStatus}`).toBe(200);
  expect(
    patchConfigResult.status,
    `comment-config status=${patchConfigResult.status} body=${JSON.stringify(patchConfigResult.json)}`,
  ).toBe(200);

  // 5) In an anonymous context, open the share URL and post a comment mentioning @username.
  const shareUrlAbs = (shareUrl as string).startsWith("http")
    ? (shareUrl as string)
    : new URL(shareUrl as string, page.url()).toString();
  const token = new URL(shareUrlAbs).searchParams.get("token");
  if (!token) throw new Error(`Expected share token in URL: ${shareUrlAbs}`);

  const anonContext = await browser.newContext();
  const anonPage = await anonContext.newPage();
  await anonPage.goto(shareUrlAbs);
  await expect(anonPage.getByText(/^(Public Share|\u516c\u5f00\u5206\u4eab)$/)).toBeVisible();

  const commentBox = anonPage.getByTestId("share-comment-body");
  await expect(commentBox).toBeVisible();
  const comment = `hello @${username} ${mentionKey}`;

  const postCommentRespPromise = anonPage.waitForResponse(
    (resp) => resp.request().method() === "POST" && /\/api\/v1\/public\/shares\/.+\/comments$/.test(resp.url()),
  );
  await commentBox.fill(comment);
  await anonPage.getByTestId("share-post-comment").click();
  const postResp = await postCommentRespPromise;
  expect([200, 201], `post comment status=${postResp.status()}`).toContain(postResp.status());
  await expect(anonPage.getByText(comment, { exact: true })).toBeVisible();
  await anonContext.close();

  // 6) Back as user A, open /notifications and find an unread mention notification containing the snippet.
  const notifListRespPromise = page.waitForResponse(
    (resp) => resp.request().method() === "GET" && /\/api\/v1\/notifications(\?|$)/.test(resp.url()) && resp.status() === 200,
  );
  await page.getByTestId("nav-notifications").click();
  await expect(page).toHaveURL(/\/notifications/);
  await notifListRespPromise;

  const findNotif = () => page.getByTestId("notif-item").filter({ hasText: mentionKey }).first();
  let notifItem = findNotif();
  for (let i = 0; i < 5; i++) {
    if ((await notifItem.count()) > 0) break;

    const refreshRespPromise = page.waitForResponse(
      (resp) => resp.request().method() === "GET" && /\/api\/v1\/notifications(\?|$)/.test(resp.url()) && resp.status() === 200,
    );
    await page.getByRole("button", { name: /刷新|Refresh/ }).click();
    await refreshRespPromise;
    notifItem = findNotif();
  }

  await expect(notifItem).toBeVisible();
  await expect(notifItem).toContainText(/mention/i);
  await expect(notifItem).toContainText(mentionKey);
  await expect(notifItem.getByText(/未读|Unread/)).toBeVisible();

  // 7) Click “Open share” and verify share page loads.
  await notifItem.getByRole("link", { name: /打开分享|Open share/ }).click();
  await expect(page).toHaveURL(/\/share\/?\?token=/);
  await expect(page.getByText(/^(Public Share|\u516c\u5f00\u5206\u4eab)$/)).toBeVisible();

  // 8) Go back and mark notification as read.
  await page.goBack();
  await expect(page).toHaveURL(/\/notifications/);

  notifItem = findNotif();
  await expect(notifItem).toBeVisible();

  const markReadRespPromise = page.waitForResponse(
    (resp) => resp.request().method() === "POST" && /\/api\/v1\/notifications\/.+\/read$/.test(resp.url()) && resp.status() === 200,
  );
  const markReadButton = notifItem.getByRole("button", { name: /标记已读|Mark read/ });
  await expect(markReadButton).toBeEnabled();
  await markReadButton.click();
  await markReadRespPromise;

  // The button label changes after marking read; assert the new "Read" state instead.
  await expect(notifItem.getByRole("button", { name: /已读|Read/ })).toBeDisabled();
  await expect(notifItem.getByText(/未读|Unread/)).toHaveCount(0);
});
