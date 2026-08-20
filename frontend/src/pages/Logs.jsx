import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth.jsx";

const NA = "N/A";

const CATEGORY_OPTIONS = [
  { value: "", label: "All categories" },
  { value: "ntp", label: "NTP" },
  { value: "email", label: "Email" },
  { value: "hold", label: "Hold" },
  { value: "delete_remove", label: "Delete/Remove" },
  { value: "login_auth", label: "Login/Auth" },
  { value: "case", label: "Matter" },
  { value: "custodian", label: "Custodian" },
  { value: "search", label: "Search" },
  { value: "consent", label: "Consent" },
  { value: "system", label: "System/Admin" },
];

const CATEGORY_META = {
  ntp: {
    label: "NTP",
    color: "#1d4ed8",
    background: "#eff6ff",
    border: "#bfdbfe",
  },
  email: {
    label: "Email",
    color: "#0f766e",
    background: "#ecfeff",
    border: "#99f6e4",
  },
  hold: {
    label: "Hold",
    color: "#9a3412",
    background: "#fff7ed",
    border: "#fed7aa",
  },
  delete_remove: {
    label: "Delete/Remove",
    color: "#991b1b",
    background: "#fef2f2",
    border: "#fecaca",
  },
  login_auth: {
    label: "Login/Auth",
    color: "#166534",
    background: "#f0fdf4",
    border: "#bbf7d0",
  },
  case: {
    label: "Matter",
    color: "#6d28d9",
    background: "#f5f3ff",
    border: "#ddd6fe",
  },
  custodian: {
    label: "Custodian",
    color: "#3730a3",
    background: "#eef2ff",
    border: "#c7d2fe",
  },
  search: {
    label: "Search",
    color: "#7e22ce",
    background: "#faf5ff",
    border: "#e9d5ff",
  },
  consent: {
    label: "Consent",
    color: "#9d174d",
    background: "#fdf2f8",
    border: "#fbcfe8",
  },
  system: {
    label: "System/Admin",
    color: "#334155",
    background: "#f8fafc",
    border: "#cbd5e1",
  },
  other: {
    label: "Other",
    color: "#111827",
    background: "#f3f4f6",
    border: "#d1d5db",
  },
};

const META_FIELDS = [
  { key: "case_name", label: "Matter" },
  { key: "custodian_name", label: "Custodian" },
  { key: "custodian_email", label: "Custodian Email" },
  { key: "target_username", label: "User" },
  { key: "target_email", label: "User Email" },
  { key: "target_first_name", label: "First Name" },
  { key: "target_last_name", label: "Last Name" },
  { key: "template_name", label: "Template" },
  { key: "template_id", label: "Template ID" },
  { key: "reminder_template_name", label: "Reminder Template" },
  { key: "reminder_template_id", label: "Reminder Template ID" },
  { key: "search_name", label: "Search" },
  { key: "note_id", label: "Note ID" },
  { key: "requestor", label: "Requestor" },
  { key: "requestor_email", label: "Requestor Email" },
  { key: "reason", label: "Reason" },
  { key: "file", label: "File" },
  { key: "logo_id", label: "Logo ID" },
];

function fmtPT(ts) {
  try {
    const s = new Date(ts).toLocaleString("en-CA", {
      timeZone: "America/Los_Angeles",
      hour12: false,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
    return s.replace(",", "");
  } catch {
    return ts || NA;
  }
}

function actionCategory(action = "") {
  const lower = String(action || "").trim().toLowerCase();
  if (!lower) return "other";
  if (lower.includes("delete") || lower.includes("remove")) return "delete_remove";
  if (lower.startsWith("ntp_") || lower.startsWith("system_ntp_")) return "ntp";
  if (lower.includes("hold")) return "hold";
  if (lower.includes("email_sent") || lower.includes("_email_") || lower === "email_test") return "email";
  if (lower.startsWith("login") || lower.startsWith("auth_login_") || lower.startsWith("password_reset_") || lower === "password_help_request") return "login_auth";
  if (lower.startsWith("custodian_")) return "custodian";
  if (lower.startsWith("case_")) return "case";
  if (lower.startsWith("search_")) return "search";
  if (lower.startsWith("consent_") || lower.startsWith("case_consent_")) return "consent";
  if (
    lower.startsWith("system_")
    || lower.startsWith("backup_")
    || lower.startsWith("logo_")
    || lower.startsWith("dashboard_")
    || lower.startsWith("tool_")
    || lower.startsWith("tls_")
    || lower.startsWith("log_ship_")
    || lower.startsWith("deprecated_")
    || lower.startsWith("registration_")
    || lower.startsWith("user_")
  ) {
    return "system";
  }
  return "other";
}

function ActionPill({ action }) {
  const category = actionCategory(action);
  const style = CATEGORY_META[category] || CATEGORY_META.other;
  return (
    <span
      className="log-pill"
      title={`Category: ${style.label}`}
      style={{
        color: style.color,
        background: style.background,
        borderColor: style.border,
      }}
    >
      {action || NA}
    </span>
  );
}

function truncate(text, max = 96) {
  if (!text) return NA;
  return text.length <= max ? text : `${text.slice(0, max - 3)}...`;
}

function parseMaybeJson(value) {
  if (typeof value !== "string") return value;
  const s = value.trim();
  if (!s) return value;
  if ((s.startsWith("{") && s.endsWith("}")) || (s.startsWith("[") && s.endsWith("]"))) {
    try {
      return JSON.parse(s);
    } catch {
      return value;
    }
  }
  return value;
}

function toInlineText(value, max = 180) {
  if (value == null) return NA;
  if (typeof value === "string") return value.length <= max ? value : `${value.slice(0, max - 3)}...`;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    const s = JSON.stringify(value);
    return s.length <= max ? s : `${s.slice(0, max - 3)}...`;
  } catch {
    return String(value);
  }
}

function previewAddresses(values, max = 3) {
  const list = Array.isArray(values) ? values.filter(Boolean).map((v) => String(v)) : [];
  if (!list.length) return null;
  const shown = list.slice(0, max).join("; ");
  const extra = list.length > max ? ` (+${list.length - max})` : "";
  return `${shown}${extra}`;
}

function summarizeEmailDetails(val) {
  const to = previewAddresses(val?.to);
  const cc = previewAddresses(val?.cc);
  const replyTo = previewAddresses(val?.reply_to);
  const subject = (val?.subject || "").trim() || "(no subject)";
  const from = (val?.from || val?.smtp_sender || "").trim();
  const recipientsTotal = Number(val?.recipients_total || 0);
  const bccCount = Number(val?.bcc_count || 0);
  const importance = (val?.importance || "").trim();
  const hasHtml = typeof val?.has_html === "boolean" ? val.has_html : null;

  return (
    <div style={{ display: "grid", gap: 2 }}>
      <div><strong>Subject:</strong> {subject}</div>
      {from ? <div><strong>From:</strong> {from}</div> : null}
      {to ? <div><strong>To:</strong> {to}</div> : null}
      {cc ? <div><strong>Cc:</strong> {cc}</div> : null}
      {replyTo ? <div><strong>Reply-To:</strong> {replyTo}</div> : null}
      <div>
        <strong>Recipients:</strong> {recipientsTotal || 0}
        {bccCount > 0 ? ` (bcc ${bccCount})` : ""}
        {importance ? ` | Importance: ${importance}` : ""}
        {hasHtml != null ? ` | HTML: ${hasHtml ? "yes" : "no"}` : ""}
      </div>
    </div>
  );
}

function HumanDetails({ details, action }) {
  const val = parseMaybeJson(details);
  const actionLower = String(action || "").toLowerCase();

  if (val && typeof val === "object" && !Array.isArray(val)) {
    if (typeof val.message === "string") {
      return <span>{val.message}</span>;
    }

    if (actionLower.includes("email_sent") && (val.subject || val.to || val.recipients_total != null)) {
      return summarizeEmailDetails(val);
    }

    const keys = Object.keys(val);
    if (keys.length === 1 && keys[0] === "value" && typeof val.value === "string") {
      return <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{val.value}</pre>;
    }

    const meta = META_FIELDS
      .map(({ key, label }) => (val[key] !== undefined && val[key] !== null ? { label, value: val[key] } : null))
      .filter(Boolean);

    const hasNote = typeof val.note === "string" && val.note.trim().length > 0;
    const hasChanges = val.changes && typeof val.changes === "object" && Object.keys(val.changes).length > 0;

    const summarizeChange = (field, change) => {
      if (Array.isArray(change?.old) || Array.isArray(change?.new)) {
        const oldLen = Array.isArray(change?.old) ? change.old.length : 0;
        const newLen = Array.isArray(change?.new) ? change.new.length : 0;
        if (field.includes("request_ticket_entries")) {
          return `Ticket entries updated (${oldLen} -> ${newLen})`;
        }
        return `${field} updated (${oldLen} -> ${newLen})`;
      }
      if (typeof change === "object" && ("old" in change || "new" in change)) {
        const oldV = change.old ?? NA;
        const newV = change.new ?? NA;
        return `${toInlineText(oldV)} -> ${toInlineText(newV)}`;
      }
      return toInlineText(change);
    };

    if (meta.length || hasNote || hasChanges) {
      return (
        <div style={{ display: "grid", gap: 4 }}>
          {meta.length > 0 && (
            <div style={{ display: "grid", gap: 2 }}>
              {meta.map(({ label, value }) => (
                <div key={label}>
                  <strong>{label}:</strong> {String(value)}
                </div>
              ))}
            </div>
          )}
          {hasNote && (
            <div>
              <strong>Note:</strong> {val.note}
            </div>
          )}
          {hasChanges && (
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {Object.entries(val.changes).map(([field, change]) => (
                <li key={field}>
                  <strong>{field}</strong>: {summarizeChange(field, change)}
                </li>
              ))}
            </ul>
          )}
        </div>
      );
    }

    if (keys.length && keys.length <= 6) {
      return (
        <ul style={{ margin: 0, paddingLeft: 16 }}>
          {keys.map((k) => (
            <li key={k}>
              <strong>{k}</strong>: {toInlineText(val[k])}
            </li>
          ))}
        </ul>
      );
    }

    let pretty = "";
    try {
      pretty = JSON.stringify(val, null, 2);
    } catch {
      pretty = String(val);
    }
    if (pretty.length > 3000) {
      pretty = `${pretty.slice(0, 2997)}...`;
    }
    return <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{pretty}</pre>;
  }

  if (Array.isArray(val)) {
    let pretty = "";
    try {
      pretty = JSON.stringify(val, null, 2);
    } catch {
      pretty = String(val);
    }
    if (pretty.length > 3000) {
      pretty = `${pretty.slice(0, 2997)}...`;
    }
    return <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{pretty}</pre>;
  }

  if (typeof val === "string") return <span>{val || NA}</span>;
  if (val == null) return <span>{NA}</span>;
  return <span>{toInlineText(val)}</span>;
}

export default function Logs({ apiBase = "/api", caseId = null, embedded = false }) {
  const { user } = useAuth();
  const role = user?.role || (user?.is_admin ? "sys_admin" : "analyst");
  const canSyncAudit = !embedded && role === "sys_admin";
  const [rows, setRows] = useState([]);
  const [page, setPage] = useState(1);
  const [perPage] = useState(50);
  const [total, setTotal] = useState(0);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [actionFilter, setActionFilter] = useState("");
  const [actorId, setActorId] = useState("");
  const [ipFilter, setIpFilter] = useState("");
  const [contains, setContains] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [syncStatus, setSyncStatus] = useState("");
  const pages = Math.max(1, Math.ceil((total || 0) / perPage));
  const [matterFilter, setMatterFilter] = useState("");

  const load = async (p = 1) => {
    setErr(null);
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(p),
        per_page: String(perPage),
      });
      if (categoryFilter) params.append("category", categoryFilter);
      if (actionFilter.trim()) params.append("action", actionFilter.trim());
      if (actorId && Number(actorId) > 0) params.append("actor_id", String(Number(actorId)));
      if (ipFilter.trim()) params.append("ip", ipFilter.trim());
      if (contains.trim()) params.append("contains", contains.trim());
      if (matterFilter.trim()) params.append("case_query", matterFilter.trim());

      const endpoint = caseId ? `${apiBase}/logs/matter/${caseId}` : `${apiBase}/logs`;
      const res = await fetch(`${endpoint}?${params.toString()}`, { credentials: "include" });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Unable to load logs.");
      setRows(data.items || []);
      setPage(p);
      setTotal(data.total || (data.items || []).length);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(1);
    // initial load only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const items = useMemo(
    () =>
      (rows || []).map((r) => {
        let details = r.details;
        try {
          details = parseMaybeJson(details);
        } catch {
          // no-op
        }
        return { ...r, details };
      }),
    [rows]
  );

  const syncAudit = async () => {
    if (!canSyncAudit || syncing) return;
    setErr(null);
    setSyncStatus("");
    setSyncing(true);
    try {
      const res = await fetch(`${apiBase}/logs/sync_audit`, {
        method: "POST",
        credentials: "include",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data?.detail || "Unable to sync audit log.");
      }
      setSyncStatus(`Audit sync complete. Scanned ${data?.scanned || 0}, inserted ${data?.inserted || 0}, skipped ${data?.skipped || 0}, failed ${data?.failed || 0}.`);
      await load(1);
    } catch (e) {
      setErr(String(e));
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div style={{ padding: embedded ? 0 : 24 }}>
      <h1 style={{ fontSize: embedded ? 22 : 28, fontWeight: 700, marginBottom: 12 }}>{embedded ? 'Matter Logs' : 'Logs'}</h1>
      {err && <div style={{ color: "#b91c1c", marginBottom: 8 }}>{err}</div>}
      {syncStatus && <div style={{ color: "#166534", marginBottom: 8 }}>{syncStatus}</div>}

      <div className="logs-toolbar" style={{ alignItems: "flex-end", gap: 12, flexWrap: "wrap" }}>
        <label style={{ display: "grid", gap: 4, flex: "1 1 180px" }}>
          <span style={{ color: "#6b7280", fontSize: 12 }}>Category</span>
          <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
            {CATEGORY_OPTIONS.map((opt) => (
              <option key={opt.value || "all"} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </label>
        <label style={{ display: "grid", gap: 4, flex: "1 1 180px" }}>
          <span style={{ color: "#6b7280", fontSize: 12 }}>Action contains</span>
          <input value={actionFilter} onChange={(e) => setActionFilter(e.target.value)} placeholder="e.g. login" />
        </label>
        <label style={{ display: "grid", gap: 4, flex: "1 1 160px" }}>
          <span style={{ color: "#6b7280", fontSize: 12 }}>Actor ID</span>
          <input value={actorId} onChange={(e) => setActorId(e.target.value)} type="number" min="0" inputMode="numeric" />
        </label>
        <label style={{ display: "grid", gap: 4, flex: "1 1 160px" }}>
          <span style={{ color: "#6b7280", fontSize: 12 }}>IP contains</span>
          <input value={ipFilter} onChange={(e) => setIpFilter(e.target.value)} placeholder="10.0." />
        </label>
        <label style={{ display: "grid", gap: 4, flex: "2 1 200px" }}>
          <span style={{ color: "#6b7280", fontSize: 12 }}>Details/username contains</span>
          <input value={contains} onChange={(e) => setContains(e.target.value)} placeholder="search string" />
        </label>
        {!embedded && <label style={{ display: "grid", gap: 4, flex: "1 1 180px" }}>
          <span style={{ color: "#6b7280", fontSize: 12 }}>Matter</span>
          <input value={matterFilter} onChange={(e) => setMatterFilter(e.target.value)} placeholder="Matter name or ID" />
        </label>}
      </div>
      <div className="logs-toolbar" style={{ alignItems: "center", gap: 12, flexWrap: "wrap", justifyContent: "space-between" }}>
        <div style={{ color: "#4b5563" }}>
          {total > 0 ? (
            <>Showing {(page - 1) * perPage + 1} - {(page - 1) * perPage + items.length} of {total}</>
          ) : (
            "No log entries yet"
          )}
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
          <button className="btn secondary" type="button" onClick={() => load(page)} disabled={loading}>Refresh</button>
          {canSyncAudit && <button className="btn secondary" type="button" onClick={syncAudit} disabled={loading || syncing}>{syncing ? "Syncing audit" : "Sync Audit Log"}</button>}
          <button
            className="btn secondary"
            type="button"
            onClick={() => {
              setCategoryFilter("");
              setActionFilter("");
              setActorId("");
              setIpFilter("");
              setContains("");
              setMatterFilter("");
              load(1);
            }}
            disabled={loading}
          >
            Clear
          </button>
          <button className="btn" type="button" onClick={() => load(1)} disabled={loading}>Apply filters</button>
          <button className="btn" onClick={() => load(Math.max(1, page - 1))} disabled={page <= 1 || loading}>Prev</button>
          <button className="btn" onClick={() => load(Math.min(pages, page + 1))} disabled={page >= pages || loading}>Next</button>
          <button className="btn" onClick={() => load(1)} disabled={loading && page === 1}>Reload first page</button>
        </div>
      </div>

      <div className="card">
        <table className="table logs-table">
          <thead>
            <tr>
              <th style={{ minWidth: 160 }}>Time (PT)</th>
              {!embedded && <th style={{ minWidth: 150 }}>Matter</th>}
              <th style={{ minWidth: 160 }}>User</th>
              <th>Action</th>
              <th style={{ minWidth: 200 }}>Network</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={embedded ? 5 : 6} style={{ textAlign: "center", color: "#6b7280", padding: 16 }}>
                  {loading ? "Loading..." : "No log entries yet."}
                </td>
              </tr>
            )}
            {items.map((r) => (
              <tr key={r.id || `${r.created_at}-${r.actor_id}-${r.action}`}>
                <td>
                  <div style={{ fontWeight: 600 }}>{fmtPT(r.created_at || r.timestamp)}</div>
                </td>
                {!embedded && <td>{r.details?.case_name || (r.details?.case_id ? `Matter #${r.details.case_id}` : NA)}</td>}
                <td>
                  <div style={{ fontWeight: 600 }}>{r.username || (r.actor_id ? `User #${r.actor_id}` : NA)}</div>
                </td>
                <td><ActionPill action={r.action} /></td>
                <td>
                  <div style={{ fontWeight: 600, wordBreak: "break-word" }}>{r.request_ip || NA}</div>
                  {r.user_agent && <div className="log-ua">{truncate(r.user_agent)}</div>}
                </td>
                <td className="log-details"><HumanDetails details={r.details} action={r.action} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginTop: 8 }}>
        <div style={{ color: "#6b7280", fontSize: 12 }}>
          Page {page} / {pages}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn" onClick={() => load(Math.max(1, page - 1))} disabled={page <= 1 || loading}>Prev</button>
          <button className="btn" onClick={() => load(Math.min(pages, page + 1))} disabled={page >= pages || loading}>Next</button>
        </div>
      </div>
    </div>
  );
}



