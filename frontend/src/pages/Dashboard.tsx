import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { childrenApi } from "@/api/children";
import { alertsApi } from "@/api/alerts";
import { AlertBadge } from "@/components/AlertBadge";
import type { Child, Alert } from "@/types";

export default function Dashboard() {
  const [children, setChildren] = useState<Child[]>([]);
  const [recentAlerts, setRecentAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      childrenApi.list(),
      alertsApi.list({ per_page: 5 }),
    ]).then(([kids, alertResp]) => {
      setChildren(kids);
      setRecentAlerts(alertResp.data);
      setLoading(false);
    });
  }, []);

  if (loading) return <p style={{ padding: 24 }}>Loading...</p>;

  return (
    <div style={{ padding: 24, maxWidth: 900, margin: "0 auto" }}>
      <h2>Dashboard</h2>

      <section style={{ marginBottom: 32 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3>Children</h3>
          <Link to="/settings">+ Add child</Link>
        </div>
        {children.length === 0 ? (
          <p>No children added yet. <Link to="/settings">Add one</Link> to get started.</p>
        ) : (
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            {children.map((child) => (
              <div key={child.id} style={{ border: "1px solid #e5e7eb", borderRadius: 8, padding: 16, minWidth: 200 }}>
                <p style={{ fontWeight: 600, marginBottom: 4 }}>{child.display_name}</p>
                <p style={{ fontSize: 13, color: "#6b7280" }}>
                  {child.gmail_connections.length > 0
                    ? `Gmail: ${child.gmail_connections[0].gmail_address}`
                    : "No Gmail connected"}
                </p>
                {child.gmail_connections.length === 0 && (
                  <button
                    onClick={() => childrenApi.connectGmail(child.id)}
                    style={{ marginTop: 8, fontSize: 12, cursor: "pointer" }}
                  >
                    Connect Gmail
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3>Recent Alerts</h3>
          <Link to="/alerts">View all</Link>
        </div>
        {recentAlerts.length === 0 ? (
          <p style={{ color: "#6b7280" }}>No alerts yet.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
                <th style={{ padding: "8px 12px" }}>Severity</th>
                <th style={{ padding: "8px 12px" }}>Child</th>
                <th style={{ padding: "8px 12px" }}>Summary</th>
                <th style={{ padding: "8px 12px" }}>Date</th>
              </tr>
            </thead>
            <tbody>
              {recentAlerts.map((alert) => (
                <tr key={alert.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                  <td style={{ padding: "8px 12px" }}><AlertBadge severity={alert.severity} /></td>
                  <td style={{ padding: "8px 12px" }}>{alert.child_name}</td>
                  <td style={{ padding: "8px 12px", maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    <Link to={`/alerts/${alert.id}`}>{alert.ai_summary}</Link>
                  </td>
                  <td style={{ padding: "8px 12px", fontSize: 13, color: "#6b7280" }}>
                    {new Date(alert.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
