import { useEffect, useState } from "react";
import { adminApi } from "@/api/admin";
import type { AdminOverview, AdminEvent, TaskLogEntry } from "@/types";

type Tab = "overview" | "events" | "tasks";

const SEVERITY_COLORS: Record<string, string> = {
  critical: "#dc2626",
  high: "#ea580c",
  medium: "#d97706",
  low: "#65a30d",
};

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 8, padding: "16px 20px", minWidth: 140 }}>
      <p style={{ fontSize: 13, color: "#6b7280", marginBottom: 4 }}>{label}</p>
      <p style={{ fontSize: 24, fontWeight: 700, margin: 0 }}>{value}</p>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const color = status === "success" ? "#16a34a" : "#dc2626";
  return (
    <span style={{ fontSize: 12, fontWeight: 600, color, background: color + "18", padding: "2px 8px", borderRadius: 99 }}>
      {status}
    </span>
  );
}

function EventTypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = { alert: "#dc2626", gmail_connection: "#2563eb", task: "#7c3aed" };
  const c = colors[type] ?? "#6b7280";
  return (
    <span style={{ fontSize: 11, fontWeight: 600, color: c, background: c + "18", padding: "2px 8px", borderRadius: 99, whiteSpace: "nowrap" }}>
      {type}
    </span>
  );
}

// ── Overview Tab ──────────────────────────────────────────────────────────────

function OverviewTab() {
  const [data, setData] = useState<AdminOverview | null>(null);

  useEffect(() => { adminApi.getOverview().then(setData); }, []);

  if (!data) return <p style={{ padding: 16, color: "#6b7280" }}>Loading…</p>;

  const { system, alerts, stale_connections, false_positive_rate, recent_failures } = data;
  const totalConns = Object.values(system.connections_by_status).reduce<number>((s, n) => s + (n ?? 0), 0);

  const alertRows = (bucket: typeof alerts.last_24h) =>
    Object.entries(bucket).map(([sev, n]) => (
      <span key={sev} style={{ marginRight: 12, color: SEVERITY_COLORS[sev] ?? "#374151" }}>
        {sev}: <strong>{n}</strong>
      </span>
    ));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
      {/* System counts */}
      <section>
        <h3 style={{ marginBottom: 12 }}>System</h3>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <StatCard label="Parents" value={system.total_parents} />
          <StatCard label="Children" value={system.total_children} />
          <StatCard label="Active connections" value={system.connections_by_status["active"] ?? 0 as number} />
          <StatCard label="Error connections" value={system.connections_by_status["error"] ?? 0 as number} />
          <StatCard label="Total connections" value={totalConns} />
          {false_positive_rate !== null && (
            <StatCard label="False positive rate" value={`${(false_positive_rate * 100).toFixed(1)}%`} />
          )}
        </div>
      </section>

      {/* Alert pipeline */}
      <section>
        <h3 style={{ marginBottom: 12 }}>Alert pipeline</h3>
        <table style={{ borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
              <th style={{ padding: "6px 16px 6px 0" }}>Period</th>
              <th style={{ padding: "6px 0" }}>By severity</th>
            </tr>
          </thead>
          <tbody>
            {([["Last 24 h", alerts.last_24h], ["Last 7 d", alerts.last_7d], ["Last 30 d", alerts.last_30d]] as const).map(([label, bucket]) => (
              <tr key={label} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={{ padding: "8px 16px 8px 0", color: "#6b7280", whiteSpace: "nowrap" }}>{label}</td>
                <td style={{ padding: "8px 0" }}>
                  {Object.keys(bucket).length ? alertRows(bucket) : <span style={{ color: "#9ca3af" }}>none</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* Stale connections */}
      {stale_connections.length > 0 && (
        <section>
          <h3 style={{ marginBottom: 12, color: "#d97706" }}>Stale connections (not synced &gt; 1 h)</h3>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
                <th style={{ padding: "6px 12px 6px 0" }}>Gmail</th>
                <th style={{ padding: "6px 12px" }}>Child</th>
                <th style={{ padding: "6px 0" }}>Last synced</th>
              </tr>
            </thead>
            <tbody>
              {stale_connections.map((c) => (
                <tr key={c.gmail_address} style={{ borderBottom: "1px solid #f3f4f6" }}>
                  <td style={{ padding: "7px 12px 7px 0" }}>{c.gmail_address}</td>
                  <td style={{ padding: "7px 12px" }}>{c.child_name}</td>
                  <td style={{ padding: "7px 0", color: "#6b7280" }}>
                    {c.last_synced_at ? new Date(c.last_synced_at).toLocaleString() : "never"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* Recent failures */}
      {recent_failures.length > 0 && (
        <section>
          <h3 style={{ marginBottom: 12, color: "#dc2626" }}>Recent task failures</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {recent_failures.map((f, i) => (
              <div key={i} style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 6, padding: "10px 14px", fontSize: 13 }}>
                <span style={{ fontWeight: 600 }}>{f.task_name}</span>
                <span style={{ color: "#6b7280", marginLeft: 8 }}>{new Date(f.created_at).toLocaleString()}</span>
                {f.error && <p style={{ margin: "4px 0 0", color: "#dc2626" }}>{f.error}</p>}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

// ── Events Tab ────────────────────────────────────────────────────────────────

function EventsTab() {
  const [items, setItems] = useState<AdminEvent[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    adminApi.getEvents(page).then((r) => {
      setItems(r.data);
      setTotal(r.meta.total);
      setLoading(false);
    });
  }, [page]);

  return (
    <div>
      {loading ? (
        <p style={{ color: "#6b7280" }}>Loading…</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
              <th style={{ padding: "6px 12px 6px 0", whiteSpace: "nowrap" }}>Time</th>
              <th style={{ padding: "6px 12px" }}>Type</th>
              <th style={{ padding: "6px 0" }}>Description</th>
            </tr>
          </thead>
          <tbody>
            {items.map((e, i) => (
              <tr key={i} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={{ padding: "8px 12px 8px 0", color: "#6b7280", whiteSpace: "nowrap" }}>
                  {new Date(e.ts).toLocaleString()}
                </td>
                <td style={{ padding: "8px 12px" }}><EventTypeBadge type={e.type} /></td>
                <td style={{ padding: "8px 0" }}>{e.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 16, fontSize: 14 }}>
        <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} style={{ cursor: "pointer" }}>← Prev</button>
        <span style={{ color: "#6b7280" }}>Page {page} · {total} total</span>
        <button onClick={() => setPage((p) => p + 1)} disabled={page * 50 >= total} style={{ cursor: "pointer" }}>Next →</button>
      </div>
    </div>
  );
}

// ── Tasks Tab ─────────────────────────────────────────────────────────────────

function TasksTab() {
  const [items, setItems] = useState<TaskLogEntry[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    adminApi.getTasks(page, filter).then((r) => {
      setItems(r.data);
      setTotal(r.meta.total);
      setLoading(false);
    });
  }, [page, filter]);

  const setFilterAndReset = (f: string | undefined) => { setFilter(f); setPage(1); };

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {(["All", "Failures"] as const).map((label) => {
          const val = label === "All" ? undefined : "failure";
          const active = filter === val;
          return (
            <button key={label} onClick={() => setFilterAndReset(val)}
              style={{ padding: "4px 14px", cursor: "pointer", borderRadius: 4,
                background: active ? "#2563eb" : "transparent",
                color: active ? "#fff" : "#374151",
                border: active ? "none" : "1px solid #d1d5db" }}>
              {label}
            </button>
          );
        })}
      </div>

      {loading ? (
        <p style={{ color: "#6b7280" }}>Loading…</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
              <th style={{ padding: "6px 12px 6px 0" }}>Task</th>
              <th style={{ padding: "6px 12px" }}>Status</th>
              <th style={{ padding: "6px 12px" }}>Duration</th>
              <th style={{ padding: "6px 12px" }}>Error</th>
              <th style={{ padding: "6px 0" }}>Time</th>
            </tr>
          </thead>
          <tbody>
            {items.map((t) => (
              <tr key={t.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={{ padding: "8px 12px 8px 0", fontFamily: "monospace" }}>{t.task_name}</td>
                <td style={{ padding: "8px 12px" }}><StatusBadge status={t.status} /></td>
                <td style={{ padding: "8px 12px", color: "#6b7280" }}>
                  {t.duration_ms != null ? `${t.duration_ms} ms` : "—"}
                </td>
                <td style={{ padding: "8px 12px", color: "#dc2626", maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {t.error ?? "—"}
                </td>
                <td style={{ padding: "8px 0", color: "#6b7280", whiteSpace: "nowrap" }}>
                  {new Date(t.created_at).toLocaleString()}
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={5} style={{ padding: 24, color: "#9ca3af", textAlign: "center" }}>No records</td></tr>
            )}
          </tbody>
        </table>
      )}
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 16, fontSize: 14 }}>
        <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} style={{ cursor: "pointer" }}>← Prev</button>
        <span style={{ color: "#6b7280" }}>Page {page} · {total} total</span>
        <button onClick={() => setPage((p) => p + 1)} disabled={page * 50 >= total} style={{ cursor: "pointer" }}>Next →</button>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Admin() {
  const [tab, setTab] = useState<Tab>("overview");

  const tabStyle = (t: Tab) => ({
    padding: "8px 18px",
    cursor: "pointer" as const,
    fontWeight: tab === t ? 600 : 400,
    color: tab === t ? "#2563eb" : "#374151",
    background: "none",
    border: "none",
    borderBottom: tab === t ? "2px solid #2563eb" : "2px solid transparent",
    fontSize: 14,
  });

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: "0 auto" }}>
      <h2 style={{ marginBottom: 20 }}>Admin</h2>

      <div style={{ display: "flex", borderBottom: "1px solid #e5e7eb", marginBottom: 24 }}>
        <button style={tabStyle("overview")} onClick={() => setTab("overview")}>Overview</button>
        <button style={tabStyle("events")} onClick={() => setTab("events")}>Events</button>
        <button style={tabStyle("tasks")} onClick={() => setTab("tasks")}>Tasks</button>
      </div>

      {tab === "overview" && <OverviewTab />}
      {tab === "events" && <EventsTab />}
      {tab === "tasks" && <TasksTab />}
    </div>
  );
}
