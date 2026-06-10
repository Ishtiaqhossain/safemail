import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { childrenApi } from "@/api/children";
import { alertsApi } from "@/api/alerts";
import { AlertBadge } from "@/components/AlertBadge";
import { getIsEmailVerified, setIsEmailVerified } from "@/api/client";
import api from "@/api/client";
import type { Child, Alert } from "@/types";

const CATEGORY_LABELS: Record<string, string> = {
  self_harm: "Self-Harm",
  grooming: "Grooming",
  bullying: "Bullying",
  drugs_alcohol: "Drugs / Alcohol",
  stranger_contact: "Stranger Contact",
  personal_info_sharing: "Personal Info",
};

function StatCard({ label, value, sub, accent }: { label: string; value: string | number; sub?: string; accent?: string }) {
  return (
    <div style={{
      background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10,
      padding: "16px 20px", flex: 1, minWidth: 140,
      borderTop: accent ? `3px solid ${accent}` : undefined,
    }}>
      <p style={{ fontSize: 12, fontWeight: 600, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>{label}</p>
      <p style={{ fontSize: 26, fontWeight: 700, color: "#0f172a", lineHeight: 1 }}>{value}</p>
      {sub && <p style={{ fontSize: 12, color: "#94a3b8", marginTop: 4 }}>{sub}</p>}
    </div>
  );
}

function ConnectionStatus({ status }: { status: "active" | "revoked" | "error" }) {
  const map: Record<string, { color: string; bg: string; label: string }> = {
    active:  { color: "#16a34a", bg: "#f0fdf4", label: "Active" },
    revoked: { color: "#64748b", bg: "#f1f5f9", label: "Revoked" },
    error:   { color: "#dc2626", bg: "#fef2f2", label: "Error" },
  };
  const { color, bg, label } = map[status] ?? map.error;
  return (
    <span style={{ fontSize: 11, fontWeight: 600, color, background: bg, padding: "2px 8px", borderRadius: 99 }}>
      {label}
    </span>
  );
}

export default function Dashboard() {
  const [searchParams] = useSearchParams();
  const justVerified = searchParams.get("verified") === "true";
  const [emailVerified, setEmailVerified] = useState(getIsEmailVerified());
  const [resendSent, setResendSent] = useState(false);
  const [children, setChildren] = useState<Child[]>([]);
  const [recentAlerts, setRecentAlerts] = useState<Alert[]>([]);
  const [unreviewedCount, setUnreviewedCount] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      childrenApi.list(),
      alertsApi.list({ per_page: 5 }),
      alertsApi.list({ per_page: 1, reviewed: false }),
    ]).then(([kids, alertResp, unreviewed]) => {
      setChildren(kids);
      setRecentAlerts(alertResp.data);
      setUnreviewedCount(unreviewed.meta.total);
      setLoading(false);
    });
  }, []);

  const resendVerification = async () => {
    await api.post("/auth/resend-verification");
    setResendSent(true);
  };

  const handleJustVerified = () => {
    setIsEmailVerified(true);
    setEmailVerified(true);
  };

  if (loading) {
    return <div style={{ padding: 40, textAlign: "center", color: "#94a3b8" }}>Loading…</div>;
  }

  const activeConns = children.flatMap((c) => c.gmail_connections).filter((g) => g.status === "active").length;

  return (
    <div style={{ padding: "28px 24px", maxWidth: 960, margin: "0 auto" }}>

      {/* Email verification banners */}
      {justVerified && emailVerified === false ? (() => { handleJustVerified(); return null; })() : null}
      {justVerified && (
        <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8, padding: "12px 16px", marginBottom: 20, display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 18 }}>✅</span>
          <span style={{ fontSize: 14, color: "#16a34a", fontWeight: 500 }}>Email verified — you're all set!</span>
        </div>
      )}
      {!emailVerified && !justVerified && (
        <div style={{ background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, padding: "12px 16px", marginBottom: 20, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontSize: 18 }}>📧</span>
          <span style={{ fontSize: 14, color: "#92400e", flex: 1 }}>
            Please verify your email address. Check your inbox for a verification link.
          </span>
          {resendSent ? (
            <span style={{ fontSize: 13, color: "#16a34a", fontWeight: 500 }}>Email sent!</span>
          ) : (
            <button
              onClick={resendVerification}
              style={{ background: "none", border: "1px solid #d97706", color: "#92400e", padding: "4px 12px", borderRadius: 5, fontSize: 13, fontWeight: 500 }}
            >
              Resend email
            </button>
          )}
        </div>
      )}

      {/* Page header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ marginBottom: 4 }}>Dashboard</h1>
        <p style={{ color: "#64748b", fontSize: 14 }}>Overview of your children's email activity.</p>
      </div>

      {/* Stat bar */}
      <div style={{ display: "flex", gap: 14, marginBottom: 28, flexWrap: "wrap" }}>
        <StatCard label="Children" value={children.length} sub="being monitored" accent="#2563eb" />
        <StatCard label="Active connections" value={activeConns} sub="Gmail accounts" accent="#16a34a" />
        <StatCard
          label="Unreviewed alerts"
          value={unreviewedCount}
          sub={unreviewedCount === 0 ? "all caught up" : "need attention"}
          accent={unreviewedCount > 0 ? "#dc2626" : "#16a34a"}
        />
      </div>

      {/* Children */}
      <section style={{ marginBottom: 32 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <h2>Children</h2>
          <Link to="/settings" style={{ fontSize: 13, color: "#2563eb", fontWeight: 500 }}>+ Add child</Link>
        </div>

        {children.length === 0 ? (
          <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: "32px 24px", textAlign: "center" }}>
            <p style={{ color: "#64748b", marginBottom: 12 }}>No children added yet.</p>
            <Link to="/settings" style={{ background: "#2563eb", color: "#fff", padding: "8px 18px", borderRadius: 7, fontWeight: 500, textDecoration: "none", fontSize: 14 }}>
              Add a child
            </Link>
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 14 }}>
            {children.map((child) => {
              const conn = child.gmail_connections[0];
              return (
                <div key={child.id} style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: "18px 20px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
                    <div>
                      <p style={{ fontWeight: 600, fontSize: 15, color: "#0f172a" }}>{child.display_name}</p>
                      {child.birth_year && (
                        <p style={{ fontSize: 12, color: "#94a3b8", marginTop: 1 }}>Born {child.birth_year}</p>
                      )}
                    </div>
                    <span style={{ fontSize: 20 }}>👦</span>
                  </div>
                  {conn ? (
                    <div style={{ background: "#f8fafc", borderRadius: 7, padding: "8px 10px" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                        <p style={{ fontSize: 11, fontWeight: 600, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.05em" }}>Gmail</p>
                        <ConnectionStatus status={conn.status} />
                      </div>
                      <p style={{ fontSize: 12, color: "#374151", wordBreak: "break-all" }}>{conn.gmail_address}</p>
                    </div>
                  ) : (
                    <button
                      onClick={() => childrenApi.connectGmail(child.id)}
                      style={{ width: "100%", padding: "7px 0", background: "#eff6ff", color: "#2563eb", border: "1px solid #bfdbfe", borderRadius: 7, fontSize: 13, fontWeight: 500, marginTop: 2 }}
                    >
                      + Connect Gmail
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Recent Alerts */}
      <section>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <h2>Recent Alerts</h2>
          <Link to="/alerts" style={{ fontSize: 13, color: "#2563eb", fontWeight: 500 }}>View all →</Link>
        </div>

        <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, overflow: "hidden" }}>
          {recentAlerts.length === 0 ? (
            <div style={{ padding: "32px 24px", textAlign: "center", color: "#94a3b8" }}>
              No alerts yet — great news!
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th style={{ paddingLeft: 20 }}>Severity</th>
                  <th>Child</th>
                  <th>Category</th>
                  <th>Summary</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {recentAlerts.map((alert) => (
                  <tr key={alert.id} style={{ background: alert.reviewed_at ? "#fff" : "#fffbf5" }}>
                    <td style={{ paddingLeft: 20 }}><AlertBadge severity={alert.severity} /></td>
                    <td style={{ color: "#374151" }}>{alert.child_name}</td>
                    <td style={{ color: "#64748b", fontSize: 13 }}>{CATEGORY_LABELS[alert.category] ?? alert.category}</td>
                    <td style={{ maxWidth: 280 }}>
                      <Link to={`/alerts/${alert.id}`} style={{ color: "#0f172a", fontWeight: alert.reviewed_at ? 400 : 500 }}>
                        <span style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {alert.ai_summary}
                        </span>
                      </Link>
                    </td>
                    <td style={{ color: "#94a3b8", fontSize: 13, whiteSpace: "nowrap" }}>
                      {new Date(alert.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}
