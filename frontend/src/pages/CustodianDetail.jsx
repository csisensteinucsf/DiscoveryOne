import { useEffect, useState, useMemo } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { personLookupDepartment, personLookupExternalId, personLookupTitle } from "./caseDetailPersonLookupFields.js";
import { consentStatusLabel, normalizeConsentStatus } from "./custodianStatusCatalog.js";

const Chip = ({ kind = "default", children, title }) => {
  const base = {
    display: "inline-block",
    padding: "2px 8px",
    borderRadius: 999,
    fontSize: 12,
    lineHeight: "18px",
    border: "1px solid #e5e7eb",
    background: "#f8fafc",
    color: "#334155",
    whiteSpace: "nowrap",
  };
  const theme =
    kind === "red"
      ? { borderColor: "#fecaca", background: "#fee2e2", color: "#991b1b" }
      : kind === "green"
      ? { borderColor: "#bbf7d0", background: "#dcfce7", color: "#065f46" }
      : kind === "blue"
      ? { borderColor: "#bfdbfe", background: "#dbeafe", color: "#1e3a8a" }
      : kind === "yellow"
      ? { borderColor: "#fde68a", background: "#fef3c7", color: "#92400e" }
      : {};
  const compact =
    kind === "blue-letter" || kind === "yellow-letter"
      ? {
          minWidth: 18,
          height: 18,
          lineHeight: "16px",
          textAlign: "center",
          padding: "0 5px",
          fontWeight: 700,
        }
      : {};
  const letterTheme =
    kind === "blue-letter"
      ? { borderColor: "#bfdbfe", background: "#dbeafe", color: "#1e3a8a" }
      : kind === "yellow-letter"
      ? { borderColor: "#fde68a", background: "#fef3c7", color: "#92400e" }
      : {};
  return (
    <span title={title} style={{ ...base, ...theme, ...compact, ...letterTheme }}>
      {children}
    </span>
  );
};

function consentChipKind(status) {
  const value = normalizeConsentStatus(status);
  if (["completed", "received", "signed"].includes(value)) return "green";
  if (["sent", "delivered"].includes(value)) return "blue";
  if (["declined", "voided"].includes(value)) return "red";
  if (["implied", "awoc"].includes(value)) return "yellow";
  return "default";
}

function ConsentStatusChip({ consent }) {
  if (!consent?.status) return null;
  const titleParts = [];
  if (consent.source) titleParts.push(`Source: ${consent.source}`);
  if (consent.sent_at) titleParts.push(`Sent: ${new Date(consent.sent_at).toLocaleString()}`);
  if (consent.completed_at) titleParts.push(`Completed: ${new Date(consent.completed_at).toLocaleString()}`);
  return (
    <Chip kind={consentChipKind(consent.status)} title={titleParts.join("\n") || "Consent status"}>
      {consentStatusLabel(consent.status)}
    </Chip>
  );
}

function HeaderCard({ data }) {
  const initials = useMemo(() => {
    const n = (data?.name || "").trim();
    if (!n) return "--";
    const parts = n.split(/\s+/).slice(0, 2);
    return parts.map(p => p[0]?.toUpperCase() || "").join("");
  }, [data?.name]);
  const openCount = (data?.cases || []).filter(c => !c.closed).length;
  const closedCount = (data?.cases || []).filter(c => c.closed).length;

  return (
    <div className="card" style={{ padding: 16, marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <div
          aria-hidden
          style={{
            width: 44,
            height: 44,
            borderRadius: "50%",
            background: "#E5EEF3",
            color: "#0b3b5c",
            fontWeight: 700,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            letterSpacing: 0.5,
          }}
        >
          {initials}
        </div>
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ fontSize: 20, fontWeight: 700, color: "var(--sidebar-fg, #0f172a)" }}>{data?.name || "?"}</div>
          <div style={{ marginTop: 2 }}>
            {data?.email ? (
              <a href={`mailto:${data.email}`} style={{ color: "#0b3b5c" }}>
                {data.email}
              </a>
            ) : (
              <span style={{ color: "#64748b" }}>no email</span>
            )}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <Chip kind={data?.active_holds ? "red" : "green"}>{data?.active_holds ? "Active preservation" : "No preservation"}</Chip>
          {data?.is_separated ? <Chip kind="yellow-letter">S</Chip> : null}
          <Chip kind="blue">{openCount} open</Chip>
          <Chip>{closedCount} closed</Chip>
        </div>
      </div>
    </div>
  );
}

function CasesCard({ cases }) {
  const open = (cases || []).filter(c => !c.closed);
  const closed = (cases || []).filter(c => c.closed);
  const sectionLabelStyle = { fontSize: 12, color: "#64748b", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.4 };
  const listStyle = { display: "grid", gap: 8, margin: 0, padding: 0, listStyle: "none" };
  const rowStyle = {
    display: "grid",
    gridTemplateColumns: "minmax(180px, 1fr) auto",
    alignItems: "center",
    gap: 12,
    padding: "8px 10px",
    border: "1px solid #e5e7eb",
    borderRadius: 10,
    background: "#fff",
  };
  const statusStyle = { display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" };

  const renderCase = (c) => (
    <li key={c.id} style={rowStyle}>
      <div style={{ minWidth: 0 }}>
        <Link to={`/cases/${c.id}`} style={{ fontWeight: 600, overflowWrap: "anywhere" }}>{c.name}</Link>
      </div>
      <div style={statusStyle}>
        {c.is_claimant ? <Chip kind="blue-letter" title="Claimant in this matter">C</Chip> : null}
        {c.closed ? <Chip>closed</Chip> : <Chip kind="green">open</Chip>}
        {c.consent ? (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span style={{ color: "#64748b", fontSize: 12 }}>Consent</span>
            <ConsentStatusChip consent={c.consent} />
          </span>
        ) : null}
      </div>
    </li>
  )

  return (
    <div className="card" style={{ padding: 16 }}>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>Matters</div>
      {(!cases || cases.length === 0) && <div>—</div>}
      {!!open.length && (
        <div style={{ marginBottom: 14 }}>
          <div style={sectionLabelStyle}>Open</div>
          <ul style={listStyle}>
            {open.map(renderCase)}
          </ul>
        </div>
      )}
      {!!closed.length && (
        <div>
          <div style={sectionLabelStyle}>Closed</div>
          <ul style={listStyle}>
            {closed.map(renderCase)}
          </ul>
        </div>
      )}
    </div>
  );
}

function HoldsCard({ holds = {} }) {
  const matrix = [
    { key: "email", label: "Email" },
    { key: "onedrive", label: "OneDrive" },
    { key: "box", label: "Box" },
    { key: "slack", label: "Slack" },
    { key: "rubrik_restore", label: "Rubrik restore" },
  ];

  return (
    <div className="card" style={{ padding: 16 }}>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>Preservation</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 8 }}>
        {matrix.map(m => {
          const on = !!holds?.[m.key];
          return (
            <div key={m.key} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{ width: 12, height: 12, borderRadius: "50%", background: on ? "#16a34a" : "#9ca3af" }} />
              <div style={{ flex: 1 }}>{m.label}</div>
              <Chip kind={on ? "green" : "default"}>{on ? "on" : "off"}</Chip>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ProfileCard({ data, employeeIdLabel = "Employee ID" }) {
  const rowStyle = { display: 'grid', gridTemplateColumns: '160px 1fr', gap: 8, marginBottom: 6 }
  const valueStyle = { color: 'var(--text,#0f172a)' }
  const muted = { color: '#6b7280' }
  return (
    <div className="card" style={{ padding: 16 }}>
      <div style={{ fontWeight: 700, marginBottom: 10 }}>Details</div>
      <div style={rowStyle}><div style={muted}>First Name</div><div style={valueStyle}>{data?.first_name || '-'}</div></div>
      <div style={rowStyle}><div style={muted}>Last Name</div><div style={valueStyle}>{data?.last_name || '-'}</div></div>
      <div style={rowStyle}><div style={muted}>Email</div><div style={valueStyle}>{data?.email || '-'}</div></div>
      <div style={rowStyle}><div style={muted}>Campus</div><div style={valueStyle}>{data?.campus || '-'}</div></div>
      <div style={rowStyle}><div style={muted}>{employeeIdLabel}</div><div style={valueStyle}>{personLookupExternalId(data) || '-'}</div></div>
      <div style={rowStyle}><div style={muted}>Department</div><div style={valueStyle}>{personLookupDepartment(data) || '-'}</div></div>
      <div style={rowStyle}><div style={muted}>Job Title</div><div style={valueStyle}>{personLookupTitle(data) || '-'}</div></div>
      <div style={rowStyle}><div style={muted}>Employment Status</div><div style={valueStyle}>{data?.employment_status || '-'}</div></div>
    </div>
  )
}

export default function CustodianDetail({ apiBase = "/api" }) {
  const { authConfig } = useAuth();
  const { search } = useLocation();
  const nav = useNavigate();
  const params = new URLSearchParams(search);
  const email = (params.get("email") || "").trim();
  const name = (params.get("name") || "").trim();

  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const hasKey = !!email || !!name;
  const employeeIdLabel = authConfig?.institution?.employee_id_label || "Employee ID";

  useEffect(() => {
    if (!hasKey) return;
    let cancel = false;
    (async () => {
      setLoading(true);
      setErr(null);
      try {
        const q = email ? `email=${encodeURIComponent(email)}` : `name=${encodeURIComponent(name)}`;
        const r = await fetch(`${apiBase}/custodians/detail?${q}`, { credentials: "include" });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const json = await r.json();
        if (!cancel) setData(json);
      } catch (e) {
        if (!cancel) setErr(String(e));
      } finally {
        if (!cancel) setLoading(false);
      }
    })();
    return () => {
      cancel = true;
    };
  }, [email, name, apiBase, hasKey]);

  return (
    <div className="wrap">
      <div className="page-header" style={{ marginBottom: "1rem", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h2 style={{ margin: 0, color: "var(--sidebar-fg, #0f172a)" }}>Custodian Detail</h2>
        <button className="btn" onClick={() => nav(-1)} style={{ background: "#E5EEF3", color: "#0b3b5c", border: "1px solid #C9D7E2" }}>
          {'\u2190'} Back
        </button>
      </div>

      {!hasKey && <div className="card">No custodian specified.</div>}
      {hasKey && loading && <div className="card">Loading...</div>}
      {hasKey && err && <div className="card alert error">Error: {err}</div>}

      {hasKey && data && (
        <>
          <HeaderCard data={data} />
          <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 16 }}>
            <CasesCard cases={data.cases} />
            <HoldsCard holds={data.holds} />
          </div>
          <div style={{ marginTop: 16 }}>
            <ProfileCard data={data} employeeIdLabel={employeeIdLabel} />
          </div>
        </>
      )}
    </div>
  );
}
