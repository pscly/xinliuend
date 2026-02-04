"use client";

import type { CSSProperties, FormEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import { apiFetch } from "@/lib/api/client";

type SharedNote = {
  id: string;
  title: string | null;
  body_md: string;
  tags: string[];
  created_at?: string;
  updated_at?: string;
};

type SharedAttachment = {
  id: string;
  filename: string;
  content_type: string | null;
  size_bytes: number;
};

type SharedNoteResponse = {
  note: SharedNote;
  attachments: SharedAttachment[];
};

type PublicShareComment = {
  id: string;
  body: string;
  author_name: string | null;
  attachment_ids: string[];
  is_folded: boolean;
  folded_reason: string | null;
  created_at: string;
};

type PublicShareCommentListResponse = {
  comments: PublicShareComment[];
};

type PublicShareCommentCreateRequest = {
  body: string;
  author_name?: string;
  attachment_ids?: string[];
  captcha_token?: string;
};

type ApiErrorPayload = {
  error?: string;
  message?: string;
  detail?: unknown;
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function toStringOrEmpty(v: unknown): string {
  return typeof v === "string" ? v : "";
}

function toStringArray(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  const out: string[] = [];
  for (const item of v) {
    if (typeof item === "string") out.push(item);
  }
  return out;
}

function parseSharedAttachment(v: unknown): SharedAttachment | null {
  if (!isRecord(v)) return null;
  const id = toStringOrEmpty(v.id);
  const filename = toStringOrEmpty(v.filename);
  const contentType = typeof v.content_type === "string" ? v.content_type : null;
  const sizeBytes = typeof v.size_bytes === "number" ? v.size_bytes : 0;
  if (!id || !filename) return null;
  return { id, filename, content_type: contentType, size_bytes: sizeBytes };
}

function parseSharedNoteResponse(v: unknown): SharedNoteResponse | null {
  if (!isRecord(v)) return null;
  if (!isRecord(v.note)) return null;
  const note = v.note;
  const id = toStringOrEmpty(note.id);
  const title = typeof note.title === "string" ? note.title : null;
  const bodyMd = toStringOrEmpty(note.body_md);
  const tags = toStringArray(note.tags);
  const createdAt = typeof note.created_at === "string" ? note.created_at : undefined;
  const updatedAt = typeof note.updated_at === "string" ? note.updated_at : undefined;
  if (!id) return null;

  const atts: SharedAttachment[] = [];
  if (Array.isArray(v.attachments)) {
    for (const a of v.attachments) {
      const parsed = parseSharedAttachment(a);
      if (parsed) atts.push(parsed);
    }
  }

  return {
    note: { id, title, body_md: bodyMd, tags, created_at: createdAt, updated_at: updatedAt },
    attachments: atts,
  };
}

function parseComment(v: unknown): PublicShareComment | null {
  if (!isRecord(v)) return null;
  const id = toStringOrEmpty(v.id);
  const body = toStringOrEmpty(v.body);
  const authorName = typeof v.author_name === "string" ? v.author_name : null;
  const attachmentIds = toStringArray(v.attachment_ids);
  const isFolded = typeof v.is_folded === "boolean" ? v.is_folded : false;
  const foldedReason = typeof v.folded_reason === "string" ? v.folded_reason : null;
  const createdAt = toStringOrEmpty(v.created_at);
  if (!id || !createdAt) return null;
  return {
    id,
    body,
    author_name: authorName,
    attachment_ids: attachmentIds,
    is_folded: isFolded,
    folded_reason: foldedReason,
    created_at: createdAt,
  };
}

function parseCommentListResponse(v: unknown): PublicShareCommentListResponse {
  if (isRecord(v) && Array.isArray(v.comments)) {
    const out: PublicShareComment[] = [];
    for (const c of v.comments) {
      const parsed = parseComment(c);
      if (parsed) out.push(parsed);
    }
    return { comments: out };
  }
  return { comments: [] };
}

async function readApiErrorPayload(res: Response): Promise<ApiErrorPayload> {
  const clone = res.clone();
  try {
    const json = (await res.json()) as unknown;
    if (!isRecord(json)) return {};
    return {
      error: typeof json.error === "string" ? json.error : undefined,
      message: typeof json.message === "string" ? json.message : undefined,
      detail: json.detail,
    };
  } catch {
    const text = await clone.text().catch(() => "");
    return text ? { message: text } : {};
  }
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  const digits = i === 0 ? 0 : v < 10 ? 2 : 1;
  return `${v.toFixed(digits)} ${units[i]}`;
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function buildPublicShareBase(token: string): string {
  return `/api/v2/public/shares/${encodeURIComponent(token)}`;
}

function maybeCaptchaHeader(captchaToken: string): Record<string, string> {
  const t = captchaToken.trim();
  return t ? { "X-Captcha-Token": t } : {};
}

function noteDisplayTitle(note: SharedNote): string {
  const t = (note.title ?? "").trim();
  if (t) return t;
  const firstLine = note.body_md.split("\n")[0]?.trim() ?? "";
  if (firstLine) return firstLine.slice(0, 80);
  return "Untitled";
}

export default function ShareClient() {
  const searchParams = useSearchParams();
  const token = useMemo(() => (searchParams.get("token") ?? "").trim(), [searchParams]);

  const [shareLoading, setShareLoading] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);
  const [share, setShare] = useState<SharedNoteResponse | null>(null);

  const [commentsLoading, setCommentsLoading] = useState(false);
  const [commentsError, setCommentsError] = useState<string | null>(null);
  const [commentsDisabledHint, setCommentsDisabledHint] = useState(false);
  const [captchaRequiredHint, setCaptchaRequiredHint] = useState(false);
  const [comments, setComments] = useState<PublicShareComment[]>([]);

  const [captchaToken, setCaptchaToken] = useState("");
  const [authorName, setAuthorName] = useState("");
  const [commentBody, setCommentBody] = useState("");
  const [commentSubmitting, setCommentSubmitting] = useState(false);
  const [commentActionError, setCommentActionError] = useState<string | null>(null);

  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadedAttachments, setUploadedAttachments] = useState<SharedAttachment[]>([]);
  const [selectedAttachmentIds, setSelectedAttachmentIds] = useState<string[]>([]);

  // Prevent stale request writes when switching token quickly.
  const loadTokenRef = useRef(0);

  const refreshShare = useCallback(async () => {
    if (!token) return;

    const loadId = ++loadTokenRef.current;
    setShareLoading(true);
    setShareError(null);
    try {
      const res = await apiFetch(buildPublicShareBase(token), { method: "GET" });
      if (!res.ok) {
        const err = await readApiErrorPayload(res);
        if (res.status === 404) {
          throw new Error("This share link is invalid or has been revoked.");
        }
        if (res.status === 410) {
          throw new Error("This share link has expired.");
        }
        throw new Error(err.message ? `Failed to load share: ${err.message}` : `Failed to load share (${res.status})`);
      }

      const json = (await res.json()) as unknown;
      const parsed = parseSharedNoteResponse(json);
      if (!parsed) throw new Error("Invalid share response");
      if (loadTokenRef.current !== loadId) return;
      setShare(parsed);
    } catch (e) {
      if (loadTokenRef.current !== loadId) return;
      setShare(null);
      setShareError(e instanceof Error ? e.message : "Failed to load share");
    } finally {
      if (loadTokenRef.current === loadId) setShareLoading(false);
    }
  }, [token]);

  const refreshComments = useCallback(async () => {
    if (!token) return;

    setCommentsLoading(true);
    setCommentsError(null);
    try {
      const res = await apiFetch(`${buildPublicShareBase(token)}/comments`, { method: "GET" });
      if (!res.ok) {
        const err = await readApiErrorPayload(res);
        if (res.status === 403) {
          setCommentsDisabledHint(true);
        }
        throw new Error(err.message ? `Failed to load comments: ${err.message}` : `Failed to load comments (${res.status})`);
      }
      const json = (await res.json()) as unknown;
      const parsed = parseCommentListResponse(json);
      setComments(parsed.comments);
    } catch (e) {
      setCommentsError(e instanceof Error ? e.message : "Failed to load comments");
      setComments([]);
    } finally {
      setCommentsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    // Reset page state whenever token changes.
    setShare(null);
    setShareError(null);
    setComments([]);
    setCommentsError(null);
    setCommentsDisabledHint(false);
    setCaptchaRequiredHint(false);
    setCommentActionError(null);
    setUploadedAttachments([]);
    setSelectedAttachmentIds([]);
    setUploadError(null);

    if (!token) return;
    void refreshShare();
    void refreshComments();
  }, [refreshComments, refreshShare, token]);

  const shareTitle = useMemo(() => {
    if (!share?.note) return "Shared note";
    return noteDisplayTitle(share.note);
  }, [share]);

  const tokenHint = useMemo(() => {
    if (!token) return "";
    const prefix = token.length > 8 ? `${token.slice(0, 6)}...${token.slice(-4)}` : token;
    return prefix;
  }, [token]);

  const attachmentIdSet = useMemo(() => new Set(share?.attachments.map((a) => a.id) ?? []), [share]);

  async function onSubmitComment(e: FormEvent) {
    e.preventDefault();
    if (!token || commentSubmitting) return;

    const body = commentBody.trim();
    if (!body) return;

    setCommentSubmitting(true);
    setCommentActionError(null);

    const payload: PublicShareCommentCreateRequest = { body };
    const name = authorName.trim();
    if (name) payload.author_name = name;
    if (selectedAttachmentIds.length > 0) payload.attachment_ids = selectedAttachmentIds;
    const cap = captchaToken.trim();
    if (cap) payload.captcha_token = cap;

    try {
      const res = await apiFetch(`${buildPublicShareBase(token)}/comments`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...maybeCaptchaHeader(captchaToken),
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await readApiErrorPayload(res);
        if (res.status === 403) {
          setCommentsDisabledHint(true);
          throw new Error("Anonymous comments are disabled for this share.");
        }
        if (res.status === 400 && (err.message ?? "").toLowerCase().includes("captcha")) {
          setCaptchaRequiredHint(true);
          throw new Error("Captcha token required. Paste it in the field above and retry.");
        }
        throw new Error(err.message ? `Failed to post comment: ${err.message}` : `Failed to post comment (${res.status})`);
      }

      setCommentBody("");
      setCaptchaRequiredHint(false);
      await refreshComments();
      // Newly posted comment may reference newly uploaded attachments; refresh share to surface them.
      await refreshShare();
    } catch (err) {
      setCommentActionError(err instanceof Error ? err.message : "Failed to post comment");
    } finally {
      setCommentSubmitting(false);
    }
  }

  async function onUploadAttachment() {
    if (!token || uploading || !uploadFile) return;

    setUploading(true);
    setUploadError(null);

    try {
      const fd = new FormData();
      fd.append("file", uploadFile);

      const res = await apiFetch(`${buildPublicShareBase(token)}/attachments`, {
        method: "POST",
        headers: {
          ...maybeCaptchaHeader(captchaToken),
        },
        body: fd,
      });

      if (!res.ok) {
        const err = await readApiErrorPayload(res);
        if (res.status === 403) {
          setCommentsDisabledHint(true);
          throw new Error("Anonymous comments are disabled for this share.");
        }
        if (res.status === 400 && (err.message ?? "").toLowerCase().includes("captcha")) {
          setCaptchaRequiredHint(true);
          throw new Error("Captcha token required. Paste it in the field above and retry.");
        }
        throw new Error(err.message ? `Upload failed: ${err.message}` : `Upload failed (${res.status})`);
      }

      const json = (await res.json()) as unknown;
      const parsed = parseSharedAttachment(json);
      if (!parsed) throw new Error("Upload succeeded but response is invalid");

      setUploadedAttachments((prev) => {
        const exists = prev.some((a) => a.id === parsed.id);
        return exists ? prev : [parsed, ...prev];
      });
      setSelectedAttachmentIds((prev) => (prev.includes(parsed.id) ? prev : [parsed.id, ...prev]));
      setUploadFile(null);
      setCaptchaRequiredHint(false);
      await refreshShare();
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function onReportComment(commentId: string) {
    if (!token) return;
    setCommentActionError(null);

    try {
      const res = await apiFetch(`${buildPublicShareBase(token)}/comments/${encodeURIComponent(commentId)}/report`, {
        method: "POST",
        headers: {
          ...maybeCaptchaHeader(captchaToken),
        },
      });

      if (!res.ok) {
        const err = await readApiErrorPayload(res);
        throw new Error(err.message ? `Failed to report: ${err.message}` : `Failed to report (${res.status})`);
      }

      await refreshComments();
    } catch (e) {
      setCommentActionError(e instanceof Error ? e.message : "Failed to report comment");
    }
  }

  const styles = useMemo(() => {
    const card: CSSProperties = {
      border: "1px solid var(--color-border)",
      borderRadius: "var(--radius-2)",
      background: "linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02)), var(--color-surface)",
      boxShadow: "var(--shadow-1)",
    };
    const button: CSSProperties = {
      border: "1px solid var(--color-border)",
      borderRadius: 999,
      padding: "10px 14px",
      background: "var(--color-surface-2)",
      color: "var(--color-text)",
      cursor: "pointer",
      font: "inherit",
    };
    const primaryButton: CSSProperties = {
      ...button,
      borderColor: "rgba(0,0,0,0)",
      background: "linear-gradient(135deg, var(--color-accent), var(--color-accent-2))",
      color: "var(--color-accent-contrast)",
    };
    const input: CSSProperties = {
      width: "100%",
      border: "1px solid var(--color-border)",
      borderRadius: 12,
      padding: "10px 12px",
      background: "var(--color-surface)",
      color: "var(--color-text)",
      font: "inherit",
    };
    const label: CSSProperties = {
      display: "block",
      fontSize: 13,
      color: "var(--color-text-muted)",
      marginBottom: 6,
    };
    return { card, button, primaryButton, input, label };
  }, []);

  return (
    <div
      style={{
        minHeight: "100vh",
        padding: "28px 16px 60px",
      }}
    >
      <div
        style={{
          maxWidth: "var(--page-max)",
          margin: "0 auto",
          display: "grid",
          gap: 16,
        }}
      >
        <header
          style={{
            ...styles.card,
            padding: 18,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div
              style={{
                fontFamily: "var(--font-display)",
                letterSpacing: "0.01em",
                fontSize: 18,
              }}
            >
              Public Share
            </div>
            <div style={{ color: "var(--color-text-muted)", fontSize: 13, marginTop: 4 }}>
              {token ? `Token: ${tokenHint}` : "Open a share link to view a note."}
            </div>
          </div>

          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "flex-end" }}>
            <button
              type="button"
              onClick={() => {
                void refreshShare();
                void refreshComments();
              }}
              style={styles.button}
              disabled={!token || shareLoading || commentsLoading}
            >
              Refresh
            </button>
          </div>
        </header>

        {!token ? (
          <section style={{ ...styles.card, padding: 18 }}>
            <h1 style={{ margin: 0, fontFamily: "var(--font-display)", fontSize: 26, letterSpacing: "0.01em" }}>
              Missing token
            </h1>
            <p style={{ margin: "10px 0 0", color: "var(--color-text-muted)", lineHeight: 1.6 }}>
              This page expects a share token in the URL. Example:
            </p>
            <pre
              style={{
                margin: "12px 0 0",
                padding: 12,
                borderRadius: 12,
                border: "1px solid var(--color-border)",
                background: "var(--color-surface-2)",
                overflowX: "auto",
              }}
            >
              /share?token=...your-token...
            </pre>
          </section>
        ) : null}

        {token ? (
          <section style={{ ...styles.card, padding: 18 }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
              <h1
                style={{
                  margin: 0,
                  fontFamily: "var(--font-display)",
                  fontSize: 26,
                  letterSpacing: "0.01em",
                }}
              >
                {shareTitle}
              </h1>
              {share?.note?.updated_at ? (
                <div style={{ color: "var(--color-text-muted)", fontSize: 13 }}>
                  Updated: {formatDateTime(share.note.updated_at)}
                </div>
              ) : null}
            </div>

            {shareLoading ? (
              <div style={{ marginTop: 12, color: "var(--color-text-muted)" }}>Loading...</div>
            ) : null}
            {shareError ? (
              <div
                style={{
                  marginTop: 12,
                  padding: 12,
                  borderRadius: 12,
                  border: "1px solid rgba(199, 72, 74, 0.45)",
                  background: "rgba(199, 72, 74, 0.10)",
                }}
              >
                {shareError}
              </div>
            ) : null}

            {share ? (
              <>
                {share.note.tags.length > 0 ? (
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
                    {share.note.tags.map((t) => (
                      <span
                        key={t}
                        style={{
                          border: "1px solid var(--color-border)",
                          background: "var(--color-surface-2)",
                          padding: "6px 10px",
                          borderRadius: 999,
                          fontSize: 12,
                          color: "var(--color-text-muted)",
                        }}
                      >
                        #{t}
                      </span>
                    ))}
                  </div>
                ) : null}

                <div style={{ marginTop: 14 }}>
                  <div style={{ color: "var(--color-text-muted)", fontSize: 13, marginBottom: 8 }}>Body</div>
                  <pre
                    style={{
                      margin: 0,
                      padding: 14,
                      borderRadius: 14,
                      border: "1px solid var(--color-border)",
                      background: "var(--color-surface-2)",
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                      lineHeight: 1.65,
                      fontSize: 14,
                    }}
                  >
                    {share.note.body_md}
                  </pre>
                </div>

                <div style={{ marginTop: 16 }}>
                  <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
                    <div style={{ color: "var(--color-text-muted)", fontSize: 13 }}>Attachments</div>
                    <div style={{ color: "var(--color-text-muted)", fontSize: 13 }}>
                      {share.attachments.length}
                    </div>
                  </div>

                  {share.attachments.length === 0 ? (
                    <div style={{ marginTop: 10, color: "var(--color-text-muted)", fontSize: 14 }}>
                      No attachments.
                    </div>
                  ) : (
                    <div style={{ marginTop: 10, display: "grid", gap: 10 }}>
                      {share.attachments.map((a) => (
                        <div
                          key={a.id}
                          style={{
                            border: "1px solid var(--color-border)",
                            borderRadius: 14,
                            background: "var(--color-surface)",
                            padding: 12,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: 12,
                          }}
                        >
                          <div style={{ minWidth: 0 }}>
                            <div style={{ fontSize: 14, overflow: "hidden", textOverflow: "ellipsis" }}>
                              {a.filename}
                            </div>
                            <div style={{ color: "var(--color-text-muted)", fontSize: 12, marginTop: 4 }}>
                              {a.content_type ?? "application/octet-stream"} | {formatBytes(a.size_bytes)} | {a.id}
                            </div>
                          </div>
                          <a
                            href={`${buildPublicShareBase(token)}/attachments/${encodeURIComponent(a.id)}`}
                            style={{
                              ...styles.button,
                              textDecoration: "none",
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 8,
                              whiteSpace: "nowrap",
                            }}
                          >
                            Download
                          </a>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            ) : null}
          </section>
        ) : null}

        {token ? (
          <section style={{ ...styles.card, padding: 18 }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
              <h2 style={{ margin: 0, fontFamily: "var(--font-display)", letterSpacing: "0.01em" }}>Comments</h2>
              <div style={{ color: "var(--color-text-muted)", fontSize: 13 }}>{comments.length}</div>
            </div>

            {commentsDisabledHint ? (
              <div
                style={{
                  marginTop: 12,
                  padding: 12,
                  borderRadius: 12,
                  border: "1px solid var(--color-border)",
                  background: "var(--color-surface-2)",
                  color: "var(--color-text-muted)",
                  lineHeight: 1.6,
                }}
              >
                Posting comments (and uploading attachments) is disabled for this share.
              </div>
            ) : null}

            {captchaRequiredHint ? (
              <div
                style={{
                  marginTop: 12,
                  padding: 12,
                  borderRadius: 12,
                  border: "1px solid rgba(199, 163, 74, 0.40)",
                  background: "rgba(199, 163, 74, 0.10)",
                  lineHeight: 1.6,
                }}
              >
                Captcha required. Fill in a captcha token and retry.
              </div>
            ) : null}

            <div style={{ marginTop: 14, display: "grid", gap: 12 }}>
              <label>
                <span style={styles.label}>Captcha token (if required)</span>
                <input
                  value={captchaToken}
                  onChange={(e) => setCaptchaToken(e.target.value)}
                  placeholder="Paste captcha token"
                  style={styles.input}
                  inputMode="text"
                  autoComplete="off"
                />
              </label>

              <div
                style={{
                  border: "1px solid var(--color-border)",
                  borderRadius: 16,
                  padding: 12,
                  background: "var(--color-surface)",
                }}
              >
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
                  <div style={{ fontFamily: "var(--font-display)", letterSpacing: "0.01em" }}>Upload (optional)</div>
                  <div style={{ color: "var(--color-text-muted)", fontSize: 12 }}>POST /attachments</div>
                </div>

                <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                  <input
                    type="file"
                    onChange={(e) => {
                      const f = e.target.files?.item(0) ?? null;
                      setUploadFile(f);
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => void onUploadAttachment()}
                    style={styles.button}
                    disabled={uploading || !uploadFile}
                  >
                    {uploading ? "Uploading..." : "Upload"}
                  </button>
                </div>

                {uploadError ? (
                  <div
                    style={{
                      marginTop: 10,
                      padding: 10,
                      borderRadius: 12,
                      border: "1px solid rgba(199, 72, 74, 0.45)",
                      background: "rgba(199, 72, 74, 0.10)",
                    }}
                  >
                    {uploadError}
                  </div>
                ) : null}

                {uploadedAttachments.length > 0 ? (
                  <div style={{ marginTop: 12 }}>
                    <div style={{ color: "var(--color-text-muted)", fontSize: 13, marginBottom: 8 }}>
                      Uploaded (select to attach in next comment)
                    </div>
                    <div style={{ display: "grid", gap: 8 }}>
                      {uploadedAttachments.map((a) => {
                        const checked = selectedAttachmentIds.includes(a.id);
                        const known = attachmentIdSet.has(a.id);
                        return (
                          <label
                            key={a.id}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "space-between",
                              gap: 12,
                              border: "1px solid var(--color-border)",
                              borderRadius: 14,
                              padding: 10,
                              background: "var(--color-surface-2)",
                            }}
                          >
                            <span style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={(e) => {
                                  const nextChecked = e.target.checked;
                                  setSelectedAttachmentIds((prev) => {
                                    if (nextChecked) {
                                      return prev.includes(a.id) ? prev : [a.id, ...prev];
                                    }
                                    return prev.filter((id) => id !== a.id);
                                  });
                                }}
                              />
                              <span style={{ minWidth: 0 }}>
                                <div style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis" }}>
                                  {a.filename}
                                </div>
                                <div style={{ color: "var(--color-text-muted)", fontSize: 12, marginTop: 2 }}>
                                  {a.id}
                                  {known ? "" : " (refresh note to see metadata)"}
                                </div>
                              </span>
                            </span>
                            <a
                              href={`${buildPublicShareBase(token)}/attachments/${encodeURIComponent(a.id)}`}
                              style={{
                                ...styles.button,
                                textDecoration: "none",
                                whiteSpace: "nowrap",
                              }}
                            >
                              Download
                            </a>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                ) : null}
              </div>

              <form
                onSubmit={(e) => {
                  void onSubmitComment(e);
                }}
                style={{
                  border: "1px solid var(--color-border)",
                  borderRadius: 16,
                  padding: 12,
                  background: "var(--color-surface)",
                }}
              >
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
                  <div style={{ fontFamily: "var(--font-display)", letterSpacing: "0.01em" }}>Write a comment</div>
                  <div style={{ color: "var(--color-text-muted)", fontSize: 12 }}>POST /comments</div>
                </div>

                <div style={{ marginTop: 10, display: "grid", gap: 10 }}>
                  <label>
                    <span style={styles.label}>Name (optional)</span>
                    <input
                      value={authorName}
                      onChange={(e) => setAuthorName(e.target.value)}
                      placeholder="Anonymous"
                      style={styles.input}
                      inputMode="text"
                      autoComplete="name"
                      maxLength={64}
                    />
                  </label>

                  <label>
                    <span style={styles.label}>Message</span>
                    <textarea
                      value={commentBody}
                      onChange={(e) => setCommentBody(e.target.value)}
                      placeholder="Be kind. No HTML is rendered."
                      style={{ ...styles.input, minHeight: 120, resize: "vertical", whiteSpace: "pre-wrap" }}
                      maxLength={4000}
                    />
                  </label>

                  {selectedAttachmentIds.length > 0 ? (
                    <div style={{ color: "var(--color-text-muted)", fontSize: 13 }}>
                      Attaching {selectedAttachmentIds.length} file(s) to this comment.
                    </div>
                  ) : null}

                  {commentActionError ? (
                    <div
                      style={{
                        padding: 10,
                        borderRadius: 12,
                        border: "1px solid rgba(199, 72, 74, 0.45)",
                        background: "rgba(199, 72, 74, 0.10)",
                      }}
                    >
                      {commentActionError}
                    </div>
                  ) : null}

                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                    <button
                      type="submit"
                      style={styles.primaryButton}
                      disabled={commentSubmitting || commentBody.trim().length < 1}
                    >
                      {commentSubmitting ? "Posting..." : "Post comment"}
                    </button>
                    <button
                      type="button"
                      style={styles.button}
                      onClick={() => void refreshComments()}
                      disabled={commentsLoading}
                    >
                      Reload comments
                    </button>
                  </div>
                </div>
              </form>
            </div>

            <div style={{ marginTop: 16 }}>
              {commentsLoading ? <div style={{ color: "var(--color-text-muted)" }}>Loading...</div> : null}
              {commentsError ? (
                <div
                  style={{
                    marginTop: 10,
                    padding: 12,
                    borderRadius: 12,
                    border: "1px solid rgba(199, 72, 74, 0.45)",
                    background: "rgba(199, 72, 74, 0.10)",
                  }}
                >
                  {commentsError}
                </div>
              ) : null}

              {comments.length === 0 && !commentsLoading && !commentsError ? (
                <div style={{ marginTop: 10, color: "var(--color-text-muted)", fontSize: 14 }}>
                  No comments yet.
                </div>
              ) : null}

              {comments.length > 0 ? (
                <div style={{ marginTop: 10, display: "grid", gap: 10 }}>
                  {comments.map((c) => {
                    const hasAttachments = c.attachment_ids.length > 0;
                    return (
                      <article
                        key={c.id}
                        style={{
                          border: "1px solid var(--color-border)",
                          borderRadius: 16,
                          background: "var(--color-surface)",
                          padding: 12,
                          opacity: c.is_folded ? 0.72 : 1,
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                            <span style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
                              {c.author_name?.trim() ? c.author_name : "Anonymous"}
                            </span>
                            <span style={{ fontSize: 13, color: "var(--color-text-muted)" }}>{formatDateTime(c.created_at)}</span>
                            {c.is_folded ? (
                              <span
                                style={{
                                  fontSize: 12,
                                  border: "1px solid rgba(199, 163, 74, 0.45)",
                                  background: "rgba(199, 163, 74, 0.10)",
                                  padding: "4px 8px",
                                  borderRadius: 999,
                                }}
                              >
                                Folded
                              </span>
                            ) : null}
                          </div>

                          <button type="button" style={styles.button} onClick={() => void onReportComment(c.id)}>
                            Report
                          </button>
                        </div>

                        {c.folded_reason ? (
                          <div style={{ marginTop: 8, color: "var(--color-text-muted)", fontSize: 13 }}>
                            Reason: {c.folded_reason}
                          </div>
                        ) : null}

                        <pre
                          style={{
                            margin: "10px 0 0",
                            padding: 12,
                            borderRadius: 14,
                            border: "1px solid var(--color-border)",
                            background: "var(--color-surface-2)",
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-word",
                            lineHeight: 1.6,
                            fontSize: 14,
                          }}
                        >
                          {c.body}
                        </pre>

                        {hasAttachments ? (
                          <div style={{ marginTop: 10, display: "grid", gap: 6 }}>
                            <div style={{ color: "var(--color-text-muted)", fontSize: 13 }}>Attachments</div>
                            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                              {c.attachment_ids.map((id) => (
                                <a
                                  key={id}
                                  href={`${buildPublicShareBase(token)}/attachments/${encodeURIComponent(id)}`}
                                  style={{
                                    border: "1px solid var(--color-border)",
                                    background: "var(--color-surface-2)",
                                    padding: "6px 10px",
                                    borderRadius: 999,
                                    fontSize: 12,
                                    textDecoration: "none",
                                  }}
                                >
                                  {id}
                                </a>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </article>
                    );
                  })}
                </div>
              ) : null}
            </div>
          </section>
        ) : null}
      </div>
    </div>
  );
}
