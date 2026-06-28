import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { alertsApi } from "@/api/alerts";
import { AlertBadge } from "@/components/AlertBadge";
import type { Alert, AlertListResponse } from "@/types";
import { track } from "@/analytics";

const SEVERITIES = ["critical", "high", "medium", "low"];

const CATEGORY_LABELS: Record<string, string> = {
  self_harm: "Self-Harm",
  grooming: "Grooming",
  bullying: "Bullying",
  drugs_alcohol: "Drugs & Alcohol",
  stranger_contact: "Stranger Contact",
  personal_info_sharing: "Personal Info",
};

function FilterChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "5px 14px", borderRadius: 99,
        background: active ? "#2563eb" : "#fff",
        color: active ? "#fff" : "#64748b",
        border: active ? "1px solid #2563eb" : "1px solid #e2e8f0",
        fontSize: 13, fontWeight: active ? 600 : 400,
        cursor: "pointer",
      }}
    >
      {label}
    </button>
  );
}

export default function AlertFeed() {
  const [response, setResponse] = useState<AlertListResponse | null>(null);
  const [page, setPage] = useState(1);
  const [severity, setSeverity] = useState("");
  const [reviewed, setReviewed] = useState<string>("");

  const load = () => {
    alertsApi.list({
      page,
      per_page: 25,
      severity: severity || undefined,
      reviewed: reviewed === "" ? undefined : reviewed === "true",
    }).then(setResponse);
  };

  useEffect(() => { load(); }, [page, severity, reviewed]);
  useEffect(() => { track("alerts_viewed"); }, []);

  const markReviewed = async (id: string) => {
    await alertsApi.markReviewed(id);
    load();
  };

  const totalPages = response ? Math.ceil(response.meta.total / 25) : 1;

  return (
    <div style={{ padding: "28px 24px", maxWidth: 1040, margin: "0 auto" }}>

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <h1 style={{ marginBottom: 4 }}>Alerts</h1>
          <p style={{ color: "#64748b", fontSize: 14 }}>
            {response ? `${response.meta.total} alert${response.meta.total !== 1 ? "s" : ""} found` : "Loading…"}
          </p>
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20, flexWrap: "wrap", alignItems: "center" }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginRight: 4 }}>
          Severity
        </span>
        <FilterChip label="All" active={severity === ""} onClick={() => { setSeverity(""); setPage(1); }} />
        {SEVERITIES.map((s) => (
          <FilterChip key={s} label={s.charAt(0).toUpperCase() + s.slice(1)} active={severity === s} onClick={() => { setSeverity(s); setPage(1); }} />
        ))}
        <div style={{ width: 1, height: 20, background: "#e2e8f0", margin: "0 6px" }} />
        <span style={{ fontSize: 12, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginRight: 4 }}>
          Status
        </span>
        <FilterChip label="All" active={reviewed === ""} onClick={() => { setReviewed(""); setPage(1); }} />
        <FilterChip label="Unreviewed" active={reviewed === "false"} onClick={() => { setReviewed("false"); setPage(1); }} />
        <FilterChip label="Reviewed" active={reviewed === "true"} onClick={() => { setReviewed("true"); setPage(1); }} />
      </div>

      {/* Table */}
      <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, overflow: "hidden" }}>
        {!response ? (
          <div style={{ padding: 40, textAlign: "center", color: "#94a3b8" }}>Loading…</div>
        ) : response.data.length === 0 ? (
          <div style={{ padding: "40px 24px", textAlign: "center", color: "#94a3b8" }}>
            No alerts match your filters.
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th style={{ width: 16, padding: 0 }}></th>
                <th>Severity</th>
                <th>Child</th>
                <th>Category</th>
                <th>Summary</th>
                <th>Date</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {response.data.map((alert: Alert) => (
                <tr
                  key={alert.id}
                  style={{ background: alert.reviewed_at ? "#fff" : "#fffbf5" }}
                >
                  {/* Severity color bar */}
                  <td style={{
                    width: 4, padding: 0,
                    background: {
                      critical: "#dc2626", high: "#ea580c", medium: "#d97706", low: "#16a34a"
                    }[alert.severity],
                  }} />
                  <td><AlertBadge severity={alert.severity} /></td>
                  <td style={{ fontWeight: 500 }}>{alert.child_name}</td>
                  <td style={{ color: "#64748b", fontSize: 13 }}>
                    {CATEGORY_LABELS[alert.category] ?? alert.category}
                  </td>
                  <td style={{ maxWidth: 300 }}>
                    <Link to={`/alerts/${alert.id}`} style={{ color: "#0f172a", fontWeight: alert.reviewed_at ? 400 : 500 }}>
                      <span style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {alert.ai_summary}
                      </span>
                    </Link>
                  </td>
                  <td style={{ color: "#94a3b8", fontSize: 13, whiteSpace: "nowrap" }}>
                    {new Date(alert.created_at).toLocaleDateString()}
                  </td>
                  <td>
                    <span style={{
                      fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 99,
                      background: alert.reviewed_at ? "#f1f5f9" : "#fff7ed",
                      color: alert.reviewed_at ? "#64748b" : "#c2410c",
                    }}>
                      {alert.reviewed_at ? "Reviewed" : "New"}
                    </span>
                  </td>
                  <td>
                    {!alert.reviewed_at && (
                      <button
                        onClick={() => markReviewed(alert.id)}
                        style={{ fontSize: 12, color: "#64748b", background: "#f1f5f9", border: "none", padding: "4px 10px", borderRadius: 5, cursor: "pointer" }}
                      >
                        Mark reviewed
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {response && response.meta.total > 25 && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 16, justifyContent: "center" }}>
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            style={{ padding: "6px 14px", background: "#fff", border: "1px solid #e2e8f0", color: "#374151", borderRadius: 7 }}
          >
            ← Prev
          </button>
          <span style={{ color: "#64748b", fontSize: 13 }}>Page {page} of {totalPages}</span>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={page >= totalPages}
            style={{ padding: "6px 14px", background: "#fff", border: "1px solid #e2e8f0", color: "#374151", borderRadius: 7 }}
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
