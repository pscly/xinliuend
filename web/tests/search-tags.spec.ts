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

function expectNonNull<T>(v: T | null | undefined, message: string): asserts v is T {
  expect(v, message).not.toBeNull();
  expect(v, message).not.toBeUndefined();
}

test("search: query + tag across notes(v1) and todos(v1)", async ({ page }) => {
  const username = makeUniqueUsername();
  const password = "pass1234";
  const query = "Work";

  const noteTitle = makeUniqueLabel(`pw-${query}-note`);
  const todoTitle = makeUniqueLabel(`pw-${query}-todo`);
  const listName = makeUniqueLabel("pw-list");

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

  // 3) Create a note via UI at /notes (click New, get note id from ?id=).
  await page.goto("/notes");
  await expect(page).toHaveURL(/\/notes/);
  const newButton = page.getByRole("button", { name: /^New$/ });
  const saveButton = page.getByRole("button", { name: /^Save$/ });
  const editor = page.locator("textarea");

  await expect(newButton).toBeVisible();
  await newButton.click();
  await expect(page).toHaveURL(/\/notes\/?\?id=/);

  const noteId = await page.evaluate(() => new URLSearchParams(window.location.search).get("id"));
  if (!noteId) throw new Error("Expected note id in location.search (?id=...)");

  // Ensure the note exists server-side before patching via API.
  await expect(editor).toBeVisible();
  await editor.fill(["# Seed", `user: ${username}`, `ts: ${Date.now()}`].join("\n"));
  await expect(saveButton).toBeEnabled();
  await saveButton.click();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();

  // 4) Patch note via browser fetch using CSRF from /api/v1/me.
  const patchNoteResult = await page.evaluate(async ({ noteId, noteTitle, query }) => {
    const meResp = await fetch("/api/v1/me", { method: "GET", credentials: "include" });
    const meJson: unknown = await meResp.json().catch(() => null);
    const csrfToken: string | null =
      typeof meJson === "object" &&
      meJson !== null &&
      "csrf_token" in meJson &&
      typeof (meJson as { csrf_token?: unknown }).csrf_token === "string"
        ? (meJson as { csrf_token: string }).csrf_token
        : null;

    const patchResp = await fetch(`/api/v1/notes/${noteId}`, {
      method: "PATCH",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
      },
      body: JSON.stringify({ title: noteTitle, tags: [query], client_updated_at_ms: Date.now() }),
    });
    const patchJson: unknown = await patchResp.json().catch(() => null);

    return {
      meStatus: meResp.status,
      patchStatus: patchResp.status,
      patchJson,
    };
  }, { noteId, noteTitle, query });

  expect(patchNoteResult.meStatus, `me status=${patchNoteResult.meStatus}`).toBe(200);
  expect(
    patchNoteResult.patchStatus,
    `note patch status=${patchNoteResult.patchStatus} body=${JSON.stringify(patchNoteResult.patchJson)}`,
  ).toBe(200);

  // 5) Create a todo list via UI at /todos and capture its list_id.
  await page.goto("/todos");
  await expect(page).toHaveURL(/\/todos/);
  const todoListSelect = page.getByLabel("Todo list");
  await expect(todoListSelect).toBeVisible();
  await page.getByLabel("New list name").fill(listName);
  await page.getByRole("button", { name: /^Create list$/ }).click();

  const listOption = page.getByRole("option", { name: listName });
  await expect(listOption).toHaveCount(1);
  const listId = await listOption.getAttribute("value");
  expectNonNull(listId, "created list option has value");
  await expect(todoListSelect).toHaveValue(listId);

  // 6) Create a todo item via browser fetch using CSRF token.
  const createTodoResult = await page.evaluate(async ({ listId, todoTitle, query }) => {
    const meResp = await fetch("/api/v1/me", { method: "GET", credentials: "include" });
    const meJson: unknown = await meResp.json().catch(() => null);
    const csrfToken: string | null =
      typeof meJson === "object" &&
      meJson !== null &&
      "csrf_token" in meJson &&
      typeof (meJson as { csrf_token?: unknown }).csrf_token === "string"
        ? (meJson as { csrf_token: string }).csrf_token
        : null;

    const resp = await fetch("/api/v1/todo/items", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
      },
      body: JSON.stringify({
        list_id: listId,
        title: todoTitle,
        note: query,
        tags: [query],
        client_updated_at_ms: Date.now(),
      }),
    });
    const json: unknown = await resp.json().catch(() => null);
    return { meStatus: meResp.status, status: resp.status, json };
  }, { listId, todoTitle, query });

  expect(createTodoResult.meStatus, `me status=${createTodoResult.meStatus}`).toBe(200);
  expect(
    createTodoResult.status,
    `create todo status=${createTodoResult.status} body=${JSON.stringify(createTodoResult.json)}`,
  ).toBe(200);

  // 7) Go to /search and query Work; wait for notes+todo fetches.
  await page.goto("/search");
  await expect(page).toHaveURL(/\/search/);

  const searchInput = page.getByPlaceholder("Search notes + todos");
  await expect(searchInput).toBeVisible();

  const notesQueryRespPromise = page.waitForResponse(
    (resp) =>
      resp.request().method() === "GET" &&
      /\/api\/v1\/notes\?/.test(resp.url()) &&
      resp.url().includes(`q=${encodeURIComponent(query)}`) &&
      resp.status() === 200,
  );
  const todosQueryRespPromise = page.waitForResponse(
    (resp) =>
      resp.request().method() === "GET" &&
      /\/api\/v1\/todo\/items\b/.test(resp.url()) &&
      !resp.url().includes("tag=") &&
      resp.status() === 200,
  );

  await searchInput.fill(query);
  await Promise.all([notesQueryRespPromise, todosQueryRespPromise]);

  // 8) Assert both the note title and todo title appear.
  const noteLink = page.getByRole("link", { name: noteTitle });
  await expect(noteLink).toBeVisible();
  await expect(page.getByText(todoTitle, { exact: true })).toBeVisible();

  // 9) Click the tag chip #Work from the notes result; assert both still appear.
  const notesTagChip = noteLink
    .first()
    // Link -> title row -> note card.
    .locator("..")
    .locator("..")
    .getByRole("button", { name: `#${query}` })
    .first();
  await expect(notesTagChip).toBeVisible();

  const notesTagRespPromise = page.waitForResponse(
    (resp) =>
      resp.request().method() === "GET" &&
      /\/api\/v1\/notes\?/.test(resp.url()) &&
      resp.url().includes(`tag=${encodeURIComponent(query)}`) &&
      resp.status() === 200,
  );
  const todosTagRespPromise = page.waitForResponse(
    (resp) =>
      resp.request().method() === "GET" &&
      /\/api\/v1\/todo\/items\b/.test(resp.url()) &&
      resp.url().includes(`tag=${encodeURIComponent(query)}`) &&
      resp.status() === 200,
  );

  await notesTagChip.click();
  await Promise.all([notesTagRespPromise, todosTagRespPromise]);

  await expect(page.getByRole("link", { name: noteTitle })).toBeVisible();
  await expect(page.getByText(todoTitle, { exact: true })).toBeVisible();
});
