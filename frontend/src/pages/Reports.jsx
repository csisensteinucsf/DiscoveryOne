import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchSystemSettings } from "../lib/systemSettingsClient.js";
import { holdMetaFromPreservationSources } from "./preservationCatalog.js";

const ExportLink = ({ href, children = "Export CSV", ...rest }) => (
  <a
    href={href}
    className="btn btn-sm"
    target="_blank"
    rel="noopener noreferrer"
    {...rest}
  >
    {children}
  </a>
);

function Section({ title, right, children }) {
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>{title}</h3>
        {right}
      </div>
      {children}
    </div>
  );
}

function Table({ columns, rows, keyFn }) {
  if (!rows?.length) return <div style={{ color: "#6b7280" }}>No rows.</div>;
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead style={{ background: "rgba(0,0,0,.03)" }}>
          <tr>
            {columns.map((c) => (
              <th key={c.key} style={{ textAlign: "left", padding: 8 }}>{c.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={keyFn ? keyFn(r, i) : i}>
              {columns.map((c) => (
                <td key={c.key} style={{ padding: 8 }}>
                  {c.render ? c.render(r) : r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const yesNo = (value) => (value ? "Yes" : "No");

const REPORT_SECTIONS = [
  {
    title: "Analyst Summary",
    exportUrl: "/api/reports/analysts/export",
    description: "Shows how many open and closed cases are assigned to each analyst so leads can balance workloads and staffing."
  },
  {
    title: "Consent Status",
    exportUrl: "/api/reports/consents_by_case/export",
    description: "Breaks down consent letters per case, highlighting where notices are unsent, pending, or fully received."
  },
  {
    title: "Hold Status",
    exportUrl: "/api/reports/holds/export",
    description: "Buckets all cases by whether any custodian holds are in place, giving a quick view into preservation coverage."
  },
  {
    title: "Per-Case Summary (Open Cases Only)",
    exportUrl: "/api/reports/cases_summary/export?open_only=1",
    description: "Provides per-case counts of custodians, search/export/delivery progress, and NTP/consent milestones for active matters."
  },
  {
    title: "Case Aging",
    exportUrl: "/api/reports/case_aging/export",
    description: "Lists each case with its analyst, status, and days open so you can spot matters that may be stalled."
  },
  {
    title: "NTP & Consent Summary",
    exportUrl: "/api/reports/ntp_consent_summary/export",
    description: "Summarizes NTP and consent statuses across all custodians to highlight where reminders or follow-ups are needed."
  },
  {
    title: "Custodian Gaps",
    exportUrl: "/api/reports/custodian_gaps/export",
    description: "Flags cases where custodians lack holds, NTPs, or completed consents so gaps can be resolved quickly."
  },
  {
    title: "Cases By Year",
    exportUrl: "/api/reports/cases_by_year/export",
    description: "Counts cases created per calendar year to track workload trends and historical volumes."
  },
  {
    title: "Search Execution Status",
    exportUrl: "/api/reports/searches_by_status/export",
    description: "Shows overall counts of completed vs pending searches/exports/deliveries for all cases."
  },
];

export default function Reports() {
  const [custQuery, setCustQuery] = useState("");
  const [cust, setCust] = useState({ matches: [], items: [], error: null, loading: false });
  const [timelineCaseId, setTimelineCaseId] = useState("");
  const [timelineCaseQuery, setTimelineCaseQuery] = useState("");
  const [timelineCases, setTimelineCases] = useState({ items: [], loading: false, error: null });
  const [timeline, setTimeline] = useState({ items: [], error: null, loading: false });
  const [reportHoldMeta, setReportHoldMeta] = useState(() => holdMetaFromPreservationSources(null));

  useEffect(() => {
    let alive = true;
    fetchSystemSettings("/api")
      .then((settings) => {
        if (alive) setReportHoldMeta(holdMetaFromPreservationSources(settings?.preservation_sources));
      })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  const holdReportColumns = reportHoldMeta.map((item) => {
    const sourceKey = item.source_key || String(item.key || "").replace(/^holds_/, "").replace(/^custom:/, "");
    return {
      key: `holds.${sourceKey}`,
      header: `Hold: ${item.label}`,
      render: (row) => yesNo(row.custodian?.holds?.[sourceKey]),
    };
  });

  const runCustodian = async (runAll = false) => {
    const q = custQuery.trim();
    if (!q && !runAll) {
      setCust({ matches: [], items: [], error: null, loading: false });
      return;
    }
    setCust((c) => ({ ...c, loading: true, error: null }));
    try {
      const url = runAll || !q ? "/api/reports/custodian" : `/api/reports/custodian?q=${encodeURIComponent(q)}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const json = await res.json();
      setCust({ matches: json.matches || [], items: json.items || [], error: null, loading: false });
    } catch (e) {
      setCust({ matches: [], items: [], error: String(e), loading: false });
    }
  };

  const custodianExportUrl = custQuery.trim()
    ? `/api/reports/custodian/export?q=${encodeURIComponent(custQuery.trim())}`
    : "/api/reports/custodian/export";

  const ensureCaseOptions = async () => {
    if (timelineCases.items.length || timelineCases.loading) return;
    setTimelineCases((c) => ({ ...c, loading: true, error: null }));
    try {
      const res = await fetch("/api/cases");
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "Unable to load cases");
      setTimelineCases({ items: Array.isArray(data) ? data : [], loading: false, error: null });
    } catch (e) {
      setTimelineCases({ items: [], loading: false, error: String(e) });
    }
  };

  const resolveCaseId = (query) => {
    const q = (query || "").trim().toLowerCase();
    if (!q) return null;
    const match = timelineCases.items.find((c) => {
      const name = (c.name || "").toLowerCase();
      const legal = (c.legal_case_name || "").toLowerCase();
      return name === q || legal === q;
    });
    if (match) return match.id;
    const partial = timelineCases.items.find((c) => {
      const name = (c.name || "").toLowerCase();
      const legal = (c.legal_case_name || "").toLowerCase();
      return name.includes(q) || (legal && legal.includes(q));
    });
    return partial ? partial.id : null;
  };

  const loadTimeline = async () => {
    const resolvedId = resolveCaseId(timelineCaseQuery);
    if (!resolvedId) {
      setTimeline({ items: [], error: "Pick a case from the list", loading: false });
      return;
    }
    setTimelineCaseId(String(resolvedId));
    setTimeline((c) => ({ ...c, loading: true, error: null }));
    try {
      const res = await fetch(`/api/reports/case_timeline?case_id=${resolvedId}`);
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail || "Unable to load timeline");
      }
      setTimeline({ items: data?.items || [], error: null, loading: false });
    } catch (e) {
      setTimeline({ items: [], error: String(e), loading: false });
    }
  };

  return (
    <div>
      <h2 style={{ marginBottom: 12 }}>Reports</h2>
      {REPORT_SECTIONS.map((section) => (
        <Section
          key={section.title}
          title={section.title}
          right={<ExportLink href={section.exportUrl} />}
        >
          <p style={{ margin: 0, color: "var(--muted,#6b7280)" }}>{section.description}</p>
        </Section>
      ))}

      <Section
        title="Custodian Report (by name/email)"
        right={<ExportLink href={custodianExportUrl} />}
      >
        <div style={{ display: "flex", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
          <input
            type="text"
            placeholder="Type name or email..."
            value={custQuery}
            onChange={(e) => setCustQuery(e.target.value)}
            style={{ flex: 1 }}
          />
          <button className="btn" onClick={() => runCustodian()} disabled={cust.loading}>
            {cust.loading ? "Searching..." : "Run"}
          </button>
          <button className="btn secondary" onClick={() => runCustodian(true)} disabled={cust.loading}>
            {cust.loading ? "Working..." : "Run for All Custodians"}
          </button>
          <button
            className="btn ghost"
            type="button"
            onClick={() => {
              setCustQuery("");
              setCust({ matches: [], items: [], error: null, loading: false });
            }}
            disabled={cust.loading}
          >
            Clear
          </button>
        </div>
        {cust.error ? <div style={{ color: "#b91c1c" }}>{cust.error}</div> : null}
        {!cust.items?.length ? (
          <div style={{ color: "#6b7280" }}>No rows.</div>
        ) : (
          <Table
            columns={[
              { key: "custodian", header: "Custodian", render: (r) => r.custodian?.name || r.custodian?.email || "-" },
              { key: "custodian.email", header: "Email", render: (r) => r.custodian?.email || "-" },
              { key: "case", header: "Case", render: (r) => <Link to={`/cases/${r.case?.id}`}>{r.case?.name}</Link> },
              ...holdReportColumns,
              { key: "searches.total", header: "Searches", render: (r) => r.searches?.total ?? 0 },
              { key: "searches.search_done", header: "Search Performed", render: (r) => r.searches?.search_done ?? 0 },
              { key: "searches.export_done", header: "Export Performed", render: (r) => r.searches?.export_done ?? 0 },
              { key: "searches.delivered", header: "Delivered", render: (r) => r.searches?.delivered ?? 0 },
            ]}
            rows={cust.items}
          />
        )}
      </Section>

      <Section
        title="Case Timeline"
        right={
          Number.isFinite(Number(timelineCaseId)) && timelineCaseId
            ? <ExportLink href={`/api/reports/case_timeline/export?case_id=${Number(timelineCaseId)}`} />
            : null
        }
      >
        <div style={{ display: "flex", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
          <input
            type="text"
            placeholder="Type case name or legal name"
            value={timelineCaseQuery}
            onFocus={ensureCaseOptions}
            onChange={(e) => setTimelineCaseQuery(e.target.value)}
            list="timeline-cases"
            style={{ minWidth: 240 }}
          />
          <datalist id="timeline-cases">
            {timelineCases.items.map((c) => (
              <option key={`case-${c.id}`} value={c.legal_case_name || c.name || ""}>
                {c.name}
              </option>
            ))}
            {timelineCases.items.map((c) => (
              <option key={`case-name-${c.id}`} value={c.name || ""}>
                {c.legal_case_name || c.name}
              </option>
            ))}
          </datalist>
          <button className="btn" onClick={loadTimeline} disabled={timeline.loading}>
            {timeline.loading ? "Loading..." : "Load timeline"}
          </button>
          <button
            className="btn ghost"
            type="button"
            onClick={() => setTimeline({ items: [], error: null, loading: false })}
            disabled={timeline.loading}
          >
            Clear
          </button>
        </div>
        {timelineCases.error ? <div style={{ color: "#b91c1c" }}>{timelineCases.error}</div> : null}
        {timeline.error ? <div style={{ color: "#b91c1c" }}>{timeline.error}</div> : null}
        {!timeline.items?.length ? (
          <div style={{ color: "#6b7280" }}>No rows.</div>
        ) : (
          <Table
            columns={[
              { key: "created_at", header: "When" },
              { key: "action", header: "Action" },
              { key: "username", header: "Actor" },
              { key: "target_type", header: "Target", render: (r) => `${r.target_type || "-"} ${r.target_id || ""}` },
              { key: "details", header: "Details", render: (r) => (typeof r.details === "string" ? r.details : JSON.stringify(r.details || {})) },
            ]}
            rows={timeline.items}
            keyFn={(r) => r.id}
          />
        )}
      </Section>
    </div>
  );
}
