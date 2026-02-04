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

test("share: anonymous comments + captcha + attachment + report", async ({ page, browser }) => {
  const username = makeUniqueUsername();
  const password = "pass1234";

  // Establish an origin for relative fetch() calls.
  await page.goto("/login");

  // 1) Register unique user via browser fetch, then clear cookies.
  const registerResult = await page.evaluate(async ({ username, password }) => {
    const resp = await fetch("/api/v1/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ username, password }),
    });

    type RegisterJson = null | { code?: unknown; [key: string]: unknown };
    let json: RegisterJson = null;
    try {
      json = (await resp.json()) as RegisterJson;
    } catch {
      // ignore
    }
    return { status: resp.status, json };
  }, { username, password });

  expect(registerResult.status, `register status=${registerResult.status}`).toBe(200);
  expect(registerResult.json?.code, `register response=${JSON.stringify(registerResult.json)}`).toBe(200);
  await page.context().clearCookies();

  // 2) Login via UI at /login (wait for /api/v1/auth/login and /api/v1/me).
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

  // 3) Create a note via UI at /notes.
  await page.goto("/notes");
  await expect(page).toHaveURL(/\/notes/);
  const newButton = page.getByRole("button", { name: /^New$/ });
  const saveButton = page.getByRole("button", { name: /^Save$/ });
  const editor = page.locator("textarea");

  await expect(newButton).toBeVisible();
  await newButton.click();
  await expect(page).toHaveURL(/\/notes\/?\?id=/);
  await expect(editor).toBeVisible();

  const noteId = await page.evaluate(() => new URLSearchParams(window.location.search).get("id"));
  if (!noteId) throw new Error("Expected note id in location.search (?id=...)");

  // Save once to ensure the note exists server-side.
  await editor.fill(["# Share seed", `user: ${username}`, `ts: ${Date.now()}`].join("\n"));
  await expect(saveButton).toBeEnabled();
  await saveButton.click();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();

  // 4) Create share link via Notes UI and capture share_id/share_url from the API response.
  const shareCreateRespPromise = page.waitForResponse(
    (resp) =>
      resp.request().method() === "POST" &&
      resp.url().includes(`/api/v2/notes/${noteId}/shares`) &&
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

  // 5) Enable anonymous comments + require captcha via authenticated API.
  const patchConfigResult = await page.evaluate(async ({ shareId }) => {
    const meResp = await fetch("/api/v1/me", { method: "GET", credentials: "include" });
    const meJson: unknown = await meResp.json().catch(() => null);
    const csrfToken: string | null =
      typeof meJson === "object" &&
      meJson !== null &&
      "data" in meJson &&
      typeof (meJson as { data?: unknown }).data === "object" &&
      (meJson as { data?: { csrf_token?: unknown } }).data !== null &&
      typeof (meJson as { data?: { csrf_token?: unknown } }).data?.csrf_token === "string"
        ? (meJson as { data: { csrf_token: string } }).data.csrf_token
        : null;

    const resp = await fetch(`/api/v2/shares/${shareId}/comment-config`, {
      method: "PATCH",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
      },
      body: JSON.stringify({ allow_anonymous_comments: true, anonymous_comments_require_captcha: true }),
    });
    const json: unknown = await resp.json().catch(() => null);
    return { meStatus: meResp.status, status: resp.status, json };
  }, { shareId: shareId as string });

  expect(patchConfigResult.meStatus, `me status=${patchConfigResult.meStatus}`).toBe(200);
  expect(
    patchConfigResult.status,
    `comment-config status=${patchConfigResult.status} body=${JSON.stringify(patchConfigResult.json)}`,
  ).toBe(200);

  // 6) Open share URL in a fresh (anonymous) context.
  const shareUrlAbs = (shareUrl as string).startsWith("http")
    ? (shareUrl as string)
    : new URL(shareUrl as string, page.url()).toString();
  const token = new URL(shareUrlAbs).searchParams.get("token");
  if (!token) throw new Error(`Expected share token in URL: ${shareUrlAbs}`);

  const anonContext = await browser.newContext();
  const anonPage = await anonContext.newPage();
  await anonPage.goto(shareUrlAbs);
  await expect(anonPage.getByText("Public Share", { exact: true })).toBeVisible();

  // 7) Fill captcha token and post first anonymous comment.
  const captchaInput = anonPage.getByPlaceholder("Paste captcha token");
  await expect(captchaInput).toBeVisible();
  await captchaInput.fill("test-pass");

  const commentBox = anonPage.getByPlaceholder("Be kind. No HTML is rendered.");
  await expect(commentBox).toBeVisible();

  const comment1 = `hello from playwright ${Date.now()}`;
  const postCommentRespPromise1 = anonPage.waitForResponse(
    (resp) => resp.request().method() === "POST" && /\/api\/v2\/public\/shares\/.+\/comments$/.test(resp.url()),
  );
  await commentBox.fill(comment1);
  await anonPage.getByRole("button", { name: /^Post comment$/ }).click();
  const postResp1 = await postCommentRespPromise1;
  expect([200, 201], `post comment status=${postResp1.status()}`).toContain(postResp1.status());
  await expect(anonPage.getByText(comment1, { exact: true })).toBeVisible();

  // 8) Upload an attachment and post a second comment with it attached.
  const fileName = `pw-attachment-${Date.now()}.txt`;
  await anonPage.locator('input[type="file"]').setInputFiles({
    name: fileName,
    mimeType: "text/plain",
    buffer: Buffer.from("hello from playwright"),
  });

  const uploadRespPromise = anonPage.waitForResponse(
    (resp) => resp.request().method() === "POST" && /\/api\/v2\/public\/shares\/.+\/attachments$/.test(resp.url()),
  );
  await anonPage.getByRole("button", { name: /^Upload$/ }).click();
  const uploadResp = await uploadRespPromise;
  expect([200, 201], `upload status=${uploadResp.status()}`).toContain(uploadResp.status());
  await expect(anonPage.getByText(fileName)).toBeVisible();

  const uploadedRow = anonPage.locator("label", { hasText: fileName }).first();
  await expect(uploadedRow.locator('input[type="checkbox"]')).toBeChecked();

  const comment2 = `attachment comment ${Date.now()}`;
  const postCommentRespPromise2 = anonPage.waitForResponse(
    (resp) => resp.request().method() === "POST" && /\/api\/v2\/public\/shares\/.+\/comments$/.test(resp.url()),
  );
  await commentBox.fill(comment2);
  await anonPage.getByRole("button", { name: /^Post comment$/ }).click();
  const postResp2 = await postCommentRespPromise2;
  expect([200, 201], `post comment 2 status=${postResp2.status()}`).toContain(postResp2.status());
  await expect(anonPage.getByText(comment2, { exact: true })).toBeVisible();

  // 9) Download attachment should return 200.
  await expect(anonPage.getByRole("link", { name: /^Download$/ }).first()).toBeVisible();
  const downloadStatus = await anonPage.evaluate(async ({ token }) => {
    const base = `/api/v2/public/shares/${encodeURIComponent(token)}`;
    const shareResp = await fetch(base, { method: "GET" });
    const shareJson: unknown = await shareResp.json().catch(() => null);
    const attachmentId: string | null =
      typeof shareJson === "object" &&
      shareJson !== null &&
      "attachments" in shareJson &&
      Array.isArray((shareJson as { attachments?: unknown }).attachments) &&
      (shareJson as { attachments: unknown[] }).attachments.length > 0 &&
      typeof (shareJson as { attachments: unknown[] }).attachments[0] === "object" &&
      (shareJson as { attachments: Array<{ id?: unknown }> }).attachments[0] !== null &&
      typeof (shareJson as { attachments: Array<{ id?: unknown }> }).attachments[0].id === "string"
        ? (shareJson as { attachments: Array<{ id: string }> }).attachments[0].id
        : null;
    if (!attachmentId) return { shareStatus: shareResp.status, downloadStatus: 0, attachmentId: null };
    const downloadResp = await fetch(`${base}/attachments/${encodeURIComponent(attachmentId)}`, { method: "GET" });
    return { shareStatus: shareResp.status, downloadStatus: downloadResp.status, attachmentId };
  }, { token });

  expect(downloadStatus.shareStatus, `public share status=${downloadStatus.shareStatus}`).toBe(200);
  expect(downloadStatus.downloadStatus, `download status=${downloadStatus.downloadStatus}`).toBe(200);
  expectNonNull(downloadStatus.attachmentId, "attachment id should be present");

  const comment2Card = anonPage.locator("article", { hasText: comment2 }).first();
  await expect(comment2Card).toBeVisible();
  await expect(comment2Card.getByText(downloadStatus.attachmentId)).toBeVisible();

  // 10) Report the first comment and assert it becomes folded with a reason.
  const comment1Card = anonPage.locator("article", { hasText: comment1 }).first();
  await expect(comment1Card).toBeVisible();

  const reportRespPromise = anonPage.waitForResponse(
    (resp) => resp.request().method() === "POST" && /\/api\/v2\/public\/shares\/.+\/comments\/.+\/report$/.test(resp.url()),
  );
  await comment1Card.getByRole("button", { name: /^Report$/ }).click();
  const reportResp = await reportRespPromise;
  expect([200, 201], `report status=${reportResp.status()}`).toContain(reportResp.status());

  await expect(comment1Card.getByText(/^Folded$/)).toBeVisible();
  await expect(comment1Card.getByText(/^Reason:/)).toBeVisible();

  await anonContext.close();
});
