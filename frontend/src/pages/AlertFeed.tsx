import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { alertsApi } from "@/api/alerts";
import { AlertBadge } from "@/components/AlertBadge";
import type { Alert, AlertListResponse } from "@/types";

const SEVERITIES = ["critical", "high", "medium", "low"];

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

  const markReviewed = async (id: string) => {
    await alertsApi.markReviewed(id);
    load();
  };

  return (
    <div style={{ padding: 24, maxWidth: 1000, margin: "0 auto" }}>
      <h2>Alerts</h2>

      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        <select value={severity} onChange={(e) => { setSeverity(e.target.value); setPage(1); }}>
          <option value="">All severities</option>
          {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={reviewed} onChange={(e) => { setReviewed(e.target.value); setPage(1); }}>
          <option value="">All</option>
          <option value="false">Unreviewed</option>
          <option value="true">Reviewed</option>
        </select>
      </div>

      {!response ? (
        <p>Loading...</p>
      ) : response.data.length === 0 ? (
        <p style={{ color: "#6b7280" }}>No alerts found.</p>
      ) : (
        <>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "2px solid #e5e7eb" }}>
                <th style={{ padding: "8px 12px" }}>Severity</th>
                <th style={{ padding: "8px 12px" }}>Child</th>
                <th style={{ padding: "8px 12px" }}>Summary</th>
                <th style={{ padding: "8px 12px" }}>Date</th>
                <th style={{ padding: "8px 12px" }}>Status</th>
                <th style={{ padding: "8px 12px" }}></th>
              </tr>
            </thead>
            <tbody>
              {response.data.map((alert: Alert) => (
                <tr key={alert.id} style={{ borderBottom: "1px solid #f3f4f6", background: alert.reviewed_at ? "#f9fafb" : "#fff" }}>
                  <td style={{ padding: "8px 12px" }}><AlertBadge severity={alert.severity} /></td>
                  <td style={{ padding: "8px 12px" }}>{alert.child_name}</td>
                  <td style={{ padding: "8px 12px", maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    <Link to={`/alerts/${alert.id}`}>{alert.ai_summary}</Link>
                  </td>
                  <td style={{ padding: "8px 12px", fontSize: 13 }}>{new Date(alert.created_at).toLocaleDateString()}</td>
                  <td style={{ padding: "8px 12px", fontSize: 13, color: alert.reviewed_at ? "#6b7280" : "#2563eb" }}>
                    {alert.reviewed_at ? "Reviewed" : "New"}
                  </td>
                  <td style={{ padding: "8px 12px" }}>
                    {!alert.reviewed_at && (
                      <button onClick={() => markReviewed(alert.id)} style={{ fontSize: 12, cursor: "pointer" }}>
                        Mark reviewed
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div style={{ display: "flex", gap: 8, marginTop: 16, alignItems: "center" }}>
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>Prev</button>
            <span>Page {page} of {Math.ceil(response.meta.total / response.meta.per_page)}</span>
            <button onClick={() => setPage((p) => p + 1)} disabled={page * 25 >= response.meta.total}>Next</button>
          </div>
        </>
      )}
    </div>
  );
}
