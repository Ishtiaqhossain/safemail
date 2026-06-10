import { useEffect, useState } from "react";
import { adminApi } from "@/api/admin";
import type { AdminOverview, AdminEvent, TaskLogEntry } from "@/types";

type Tab = "overview" | "events" | "tasks";

const SEVERITY_COLOR: Record<string, string> = {
  critical: "#dc2626",
  high:     "#ea580c",
  medium:   "#d97706",
  low:      "#16a34a",
};

// ── Shared primitives ─────────────────────────────────────────────────────────

function Card({ children, style = {} }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, ...style }}>
      {children}
    </div>
  );
}

function StatCard({ label, value, warn }: { label: string; value: string | number; warn?: boolean }) {
  return (
    <div style={{
      background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10,
      padding: "14px 18px", minWidth: 130, flex: 1,
      borderTop: warn ? "3px solid #d97706" : undefined,
    }}>
      <p style={{ fontSize: 11, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>{label}</p>
      <p style={{ fontSize: 24, fontWeight: 700, color: "#0f172a" }}>{value}</p>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const ok = status === "success";
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 99,
      background: ok ? "#f0fdf4" : "#fef2f2",
      color: ok ? "#16a34a" : "#dc2626",
    }}>
      {status}
    </span>
  );
}

function TypeBadge({ type }: { type: string }) {
  const palette: Record<string, [string, string]> = {
    alert:            ["#fef2f2", "#dc2626"],
    gmail_connection: ["#eff6ff", "#2563eb"],
    task:             ["#f5f3ff", "#7c3aed"],
  };
  const [bg, color] = palette[type] ?? ["#f1f5f9", "#64748b"];
  return (
    <span style={{ fontSize: 11, fontWeight: 600, padding: "2px 8px", borderRadius: 99, background: bg, color, whiteSpace: "nowrap" }}>
      {type.replace("_", " ")}
    </span>
  );
}

function Pagination({ page, total, perPage, onChange }: { page: number; total: number; perPage: number; onChange: (p: number) => void }) {
  const pages = Math.ceil(total / perPage);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, paddingTop: 16 }}>
      <button
        onClick={() => onChange(Math.max(1, page - 1))} disabled={page === 1}
        style={{ padding: "5px 12px", background: "#fff", border: "1px solid #e2e8f0", color: "#374151", borderRadius: 6, fontSize: 13 }}
      >← Prev</button>
      <span style={{ fontSize: 13, color: "#64748b" }}>Page {page} of {pages} · {total} total</span>
      <button
        onClick={() => onChange(page + 1)} disabled={page >= pages}
        style={{ padding: "5px 12px", background: "#fff", border: "1px solid #e2e8f0", color: "#374151", borderRadius: 6, fontSize: 13 }}
      >Next →</button>
    </div>
  );
}

// ── Overview Tab ──────────────────────────────────────────────────────────────

function OverviewTab() {
  const [data, setData] = useState<AdminOverview | null>(null);
  useEffect(() => { adminApi.getOverview().then(setData); }, []);

  if (!data) return <div style={{ padding: 40, textAlign: "center", color: "#94a3b8" }}>Loading…</div>;

  const { system, alerts, stale_connections, false_positive_rate, recent_failures } = data;
  const totalConns = Object.values(system.connections_by_status).reduce<number>((s, n) => s + (n ?? 0), 0);

  const alertPeriods: [string, typeof alerts.last_24h][] = [
    ["Last 24 h", alerts.last_24h],
    ["Last 7 d",  alerts.last_7d],
    ["Last 30 d", alerts.last_30d],
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

      {/* Stats */}
      <section>
        <p style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>System</p>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <StatCard label="Parents"           value={system.total_parents} />
          <StatCard label="Children"          value={system.total_children} />
          <StatCard label="Active conn."      value={system.connections_by_status["active"] ?? 0} />
          <StatCard label="Error conn."       value={system.connections_by_status["error"] ?? 0} warn={(system.connections_by_status["error"] ?? 0) > 0} />
          <StatCard label="Total conn."       value={totalConns} />
          {false_positive_rate !== null && (
            <StatCard label="False pos. rate" value={`${(false_positive_rate * 100).toFixed(1)}%`} />
          )}
        </div>
      </section>

      {/* Alert pipeline */}
      <section>
        <p style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>Alert pipeline</p>
        <Card>
          <table>
            <thead>
              <tr>
                <th>Period</th>
                {["critical", "high", "medium", "low"].map((s) => (
                  <th key={s} style={{ color: SEVERITY_COLOR[s] }}>{s}</th>
                ))}
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {alertPeriods.map(([label, bucket]) => {
                const total = Object.values(bucket).reduce<number>((s, n) => s + (n ?? 0), 0);
                return (
                  <tr key={label}>
                    <td style={{ color: "#64748b", fontWeight: 500, fontSize: 13 }}>{label}</td>
                    {["critical", "high", "medium", "low"].map((sev) => (
                      <td key={sev} style={{ color: (bucket as Record<string, number>)[sev] ? SEVERITY_COLOR[sev] : "#d1d5db", fontWeight: 600, fontSize: 15 }}>
                        {(bucket as Record<string, number>)[sev] ?? 0}
                      </td>
                    ))}
                    <td style={{ fontWeight: 600, color: "#374151" }}>{total}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      </section>

      {/* Stale connections */}
      {stale_connections.length > 0 && (
        <section>
          <p style={{ fontSize: 11, fontWeight: 700, color: "#d97706", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>
            ⚠ Stale connections (not synced &gt;1 h)
          </p>
          <Card>
            <table>
              <thead>
                <tr>
                  <th>Gmail address</th>
                  <th>Child</th>
                  <th>Last synced</th>
                </tr>
              </thead>
              <tbody>
                {stale_connections.map((c) => (
                  <tr key={c.gmail_address}>
                    <td style={{ fontFamily: "monospace", fontSize: 13 }}>{c.gmail_address}</td>
                    <td>{c.child_name}</td>
                    <td style={{ color: "#94a3b8", fontSize: 13 }}>{c.last_synced_at ? new Date(c.last_synced_at).toLocaleString() : "never"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </section>
      )}

      {/* Recent failures */}
      {recent_failures.length > 0 && (
        <section>
          <p style={{ fontSize: 11, fontWeight: 700, color: "#dc2626", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>
            Recent task failures
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {recent_failures.map((f, i) => (
              <div key={i} style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, padding: "12px 16px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: f.error ? 6 : 0 }}>
                  <span style={{ fontWeight: 600, fontSize: 13, fontFamily: "monospace" }}>{f.task_name}</span>
                  <span style={{ fontSize: 12, color: "#94a3b8" }}>{new Date(f.created_at).toLocaleString()}</span>
                </div>
                {f.error && <p style={{ fontSize: 13, color: "#dc2626", margin: 0 }}>{f.error}</p>}
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
    adminApi.getEvents(page).then((r) => { setItems(r.data); setTotal(r.meta.total); setLoading(false); });
  }, [page]);

  return (
    <div>
      <Card>
        {loading ? (
          <div style={{ padding: 40, textAlign: "center", color: "#94a3b8" }}>Loading…</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Type</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr><td colSpan={3} style={{ textAlign: "center", color: "#94a3b8", padding: 32 }}>No events</td></tr>
              ) : items.map((e, i) => (
                <tr key={i}>
                  <td style={{ color: "#94a3b8", fontSize: 13, whiteSpace: "nowrap" }}>{new Date(e.ts).toLocaleString()}</td>
                  <td><TypeBadge type={e.type} /></td>
                  <td style={{ color: "#374151" }}>{e.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <Pagination page={page} total={total} perPage={50} onChange={setPage} />
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
    adminApi.getTasks(page, filter).then((r) => { setItems(r.data); setTotal(r.meta.total); setLoading(false); });
  }, [page, filter]);

  const setFilterAndReset = (f: string | undefined) => { setFilter(f); setPage(1); };

  return (
    <div>
      <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
        {([["All", undefined], ["Failures", "failure"]] as const).map(([label, val]) => (
          <button key={label} onClick={() => setFilterAndReset(val)}
            style={{
              padding: "5px 14px", borderRadius: 99, fontSize: 13,
              background: filter === val ? "#2563eb" : "#fff",
              color: filter === val ? "#fff" : "#64748b",
              border: filter === val ? "1px solid #2563eb" : "1px solid #e2e8f0",
              fontWeight: filter === val ? 600 : 400,
            }}>
            {label}
          </button>
        ))}
      </div>
      <Card>
        {loading ? (
          <div style={{ padding: 40, textAlign: "center", color: "#94a3b8" }}>Loading…</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Task</th>
                <th>Status</th>
                <th>Duration</th>
                <th>Error</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr><td colSpan={5} style={{ textAlign: "center", color: "#94a3b8", padding: 32 }}>No records</td></tr>
              ) : items.map((t) => (
                <tr key={t.id}>
                  <td style={{ fontFamily: "monospace", fontSize: 12, color: "#374151" }}>{t.task_name}</td>
                  <td><StatusBadge status={t.status} /></td>
                  <td style={{ color: "#94a3b8", fontSize: 13 }}>{t.duration_ms != null ? `${t.duration_ms} ms` : "—"}</td>
                  <td style={{ color: "#dc2626", fontSize: 12, maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {t.error ?? <span style={{ color: "#d1d5db" }}>—</span>}
                  </td>
                  <td style={{ color: "#94a3b8", fontSize: 13, whiteSpace: "nowrap" }}>{new Date(t.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <Pagination page={page} total={total} perPage={50} onChange={setPage} />
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Admin() {
  const [tab, setTab] = useState<Tab>("overview");

  return (
    <div style={{ padding: "28px 24px", maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ marginBottom: 4 }}>Admin</h1>
        <p style={{ color: "#64748b", fontSize: 14 }}>System health, events, and task logs.</p>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 0, borderBottom: "1px solid #e2e8f0", marginBottom: 24 }}>
        {(["overview", "events", "tasks"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: "10px 20px", background: "none", border: "none",
              borderBottom: tab === t ? "2px solid #2563eb" : "2px solid transparent",
              color: tab === t ? "#2563eb" : "#64748b",
              fontWeight: tab === t ? 600 : 400,
              fontSize: 14, cursor: "pointer",
              textTransform: "capitalize",
              marginBottom: -1,
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab />}
      {tab === "events"   && <EventsTab />}
      {tab === "tasks"    && <TasksTab />}
    </div>
  );
}
