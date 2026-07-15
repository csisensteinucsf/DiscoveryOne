export const API_BASE = import.meta.env?.VITE_API_BASE || "/api";
export const CURRENT_USERNAME = "Current user";
export const ATTACH_ACCEPT = "image/png,image/jpeg,image/gif,image/webp,application/pdf,.pdf,application/msword,.doc,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.docx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,.xlsx,application/vnd.ms-excel,.xls";
export const NOTE_ATTACHMENT_MAX_MB = 5;
export const NOTE_ATTACHMENT_HELP_TEXT = `Attach up to ${NOTE_ATTACHMENT_MAX_MB} MB per file (PNG, JPEG, GIF, WebP, PDF, DOC, DOCX, XLSX, or XLS).`;

/** Parse various timestamp shapes safely.
 * - Accepts Date, epoch ms, ISO strings.
 * - If no timezone in string, assume UTC (append 'Z').
 * - Converts "YYYY-MM-DD HH:MM:SS" to "YYYY-MM-DDTHH:MM:SS".
 */
export const parseUTCish = (value) => {
  if (!value) return null;
  if (value instanceof Date) return value;
  if (typeof value === "number") {
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  let s = String(value).trim();
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/.test(s)) s = s.replace(" ", "T");
  // If no explicit timezone (Z or +hh:mm), treat as UTC
  if (!/[zZ]|[+\-]\d{2}:?\d{2}$/.test(s)) s += "Z";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
};

/** Pacific timestamp formatter (handles UTC inputs + DST) */
export const pacificStamp = (value, opts = { showTZ: true }) => {
  const dt = parseUTCish(value);
  if (!dt) return "â€”";
  const base = {
    timeZone: "America/Los_Angeles",
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  };
  if (opts.showTZ) base.timeZoneName = "short"; // e.g., PDT/PST
  return new Intl.DateTimeFormat("en-US", base).format(dt);
};

export const attachmentUrl = (caseId, noteId, attachmentId) =>
  `${API_BASE}/cases/${caseId}/notes/${noteId}/attachments/${attachmentId}/download`;

export const notesBaseUrl = (caseId, apiSuffix) =>
  `${API_BASE}/cases/${caseId}/${(apiSuffix || "notes").replace(/^\/+/, "")}`;

export const absoluteUrl = (url) => {
  if (!url) return "#";
  if (/^https?:\/\//i.test(url)) return url;
  if (url.startsWith("/")) return url;
  const base = (API_BASE || "").replace(/\/$/, "");
  const suffix = String(url).replace(/^\//, "");
  return `${base}/${suffix}`;
};

export const isImageAttachment = (attachment) => {
  const contentType = String(attachment?.content_type || "").toLowerCase();
  return contentType.startsWith("image/");
};

export const canPreviewAttachment = (attachment) => {
  const kind = attachmentKind(attachment);
  return kind === "image" || kind === "pdf";
};

export const attachmentKind = (attachment) => {
  const contentType = String(attachment?.content_type || "").toLowerCase();
  const name = String(attachment?.filename || "").toLowerCase();
  if (contentType.startsWith("image/")) return "image";
  if (contentType === "application/pdf" || name.endsWith(".pdf")) return "pdf";
  if (contentType === "application/msword" || name.endsWith(".doc")) return "doc";
  if (contentType.includes("wordprocessingml.document") || name.endsWith(".docx")) return "docx";
  if (contentType.includes("spreadsheetml.sheet") || contentType === "application/vnd.ms-excel" || name.endsWith(".xlsx") || name.endsWith(".xls")) return "xls";
  return "file";
};

export const fileLabelForAttachment = (attachment) => {
  const kind = attachmentKind(attachment);
  if (kind === "pdf") return "PDF";
  if (kind === "doc") return "DOC";
  if (kind === "docx") return "DOCX";
  if (kind === "xls") return "XLS";
  return "FILE";
};

export const fileToneForAttachment = (attachment) => {
  const kind = attachmentKind(attachment);
  if (kind === "pdf") return { bg: "#fef2f2", border: "#fecaca", color: "#b91c1c", accent: "#ef4444" };
  if (kind === "doc" || kind === "docx") return { bg: "#eff6ff", border: "#bfdbfe", color: "#1d4ed8", accent: "#3b82f6" };
  if (kind === "xls") return { bg: "#ecfdf5", border: "#bbf7d0", color: "#047857", accent: "#10b981" };
  return { bg: "#f8fafc", border: "#e5e7eb", color: "#334155", accent: "#64748b" };
};

export const formatAttachmentSize = (size) => {
  const bytes = Number(size || 0);
  if (!Number.isFinite(bytes) || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)} MB`;
};

export function mapAttachment(att, caseId, noteId) {
  if (!att) return null;
  const id = att.id || att.attachment_id;
  const url = att.url || att.download_url || attachmentUrl(caseId, noteId, id);
  return {
    id,
    filename: att.filename || att.original_filename || att.name || "attachment",
    content_type: att.content_type || "",
    size: att.size || 0,
    uploaded_by: att.uploaded_by || null,
    uploaded_at: att.uploaded_at || null,
    url,
  };
}

export function mapNote(n, caseId) {
  const id = n.id || n.note_id || n.uuid || crypto?.randomUUID?.() || ("id_"+Math.random().toString(36).slice(2));
  const attachments = (Array.isArray(n.attachments) && caseId && id)
    ? n.attachments.map(att => mapAttachment(att, caseId, id)).filter(Boolean)
    : [];
  return {
    id,
    body: String(n.body ?? n.text ?? "").trim(),
    format: n.format || "plain",
    author: n.author || n.author_name || n.user_name || n.username || CURRENT_USERNAME,
    created_at: n.created_at || n.createdAt || new Date().toISOString(),
    updated_at: n.updated_at || n.updatedAt || n.created_at || new Date().toISOString(),
    is_pinned: !!(n.is_pinned || n.pinned),
    attachments,
  };
}

export async function tryJson(url, options) {
  try {
    const r = await fetch(url, { credentials: "include", ...options });
    if (!r.ok) return null;
    if (r.status === 204) return {};
    const ct = r.headers.get("content-type") || "";
    return ct.includes("application/json") ? await r.json() : {};
  } catch { return null; }
}

// --- server calls (optional; fallbacks to local if unavailable) ---
export async function serverLoadNotes(caseId, apiSuffix) {
  const data = await tryJson(notesBaseUrl(caseId, apiSuffix));
  return Array.isArray(data) ? data.map(n => mapNote(n, caseId)) : null;
}
export async function serverCreateNote(caseId, apiSuffix, note) {
  const body = JSON.stringify({ body: note.body, format: note.format || "plain", is_pinned: !!note.is_pinned });
  const created = await tryJson(notesBaseUrl(caseId, apiSuffix), {
    method: "POST", headers: { "Content-Type": "application/json" }, body
  });
  return created ? mapNote(created, caseId) : null;
}
export async function serverUpdateNote(caseId, apiSuffix, id, patch) {
  const body = JSON.stringify(patch || {});
  const updated = await tryJson(`${notesBaseUrl(caseId, apiSuffix)}/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body
  });
  return updated ? mapNote(updated, caseId) : null;
}
export async function serverDeleteNote(caseId, apiSuffix, id) {
  try {
    const res = await fetch(`${notesBaseUrl(caseId, apiSuffix)}/${id}`, {
      method: 'DELETE',
      credentials: 'include',
    });
    return res.ok;
  } catch (e) {
    console.error('serverDeleteNote failed:', e);
    return false;
  }
}

export async function serverUploadAttachment(caseId, noteId, file) {
  const fd = new FormData();
  fd.append('file', file, file.name);
  const res = await fetch(`${API_BASE}/cases/${caseId}/notes/${noteId}/attachments`, {
    method: 'POST',
    body: fd,
    credentials: 'include',
  });
  if (!res.ok) {
    let msg = 'Unable to upload attachment.';
    try {
      const data = await res.json();
      if (data?.detail) msg = data.detail;
    } catch {
      msg = await res.text().catch(() => msg);
    }
    throw new Error(msg);
  }
  const data = await res.json();
  return mapAttachment(data, caseId, noteId);
}

export async function serverDeleteAttachment(caseId, noteId, attachmentId) {
  const res = await fetch(`${API_BASE}/cases/${caseId}/notes/${noteId}/attachments/${attachmentId}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!res.ok) {
    let msg = 'Unable to delete attachment.';
    try {
      const data = await res.json();
      if (data?.detail) msg = data.detail;
    } catch {
      msg = await res.text().catch(() => msg);
    }
    throw new Error(msg);
  }
  return true;
}

export function appendStatusDetail(message, suffix) {
  const text = String(message || '').trim();
  if (!text) return suffix;
  return /[.!?]$/.test(text) ? `${text} ${suffix}` : `${text}. ${suffix}`;
}

