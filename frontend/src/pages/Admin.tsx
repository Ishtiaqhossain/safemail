import { useEffect, useState } from "react";
import { adminApi } from "@/api/admin";
import type { AdminOverview, AdminEvent, TaskLogEntry, LlmStats, AllowedEmail, WaitlistEntry, FeedbackInsights } from "@/types";
import { analyticsApi } from "@/api/analytics";
import type { AnalyticsOverview, AnalyticsFunnel, AnalyticsEvents, FunnelStage } from "@/api/analytics";

type Tab = "overview" | "analytics" | "llm" | "feedback" | "allowlist" | "waitlist" | "events" | "tasks";

const fmtNum = (n: number) => n.toLocaleString();
const fmtCost = (n: number) => (n === 0 ? "$0.00" : n < 0.01 ? "< $0.01" : `$${n.toFixed(n >= 1 ? 2 : 4)}`);

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

// ── LLM Usage Tab ─────────────────────────────────────────────────────────────

function LlmUsageCard({ label, period }: { label: string; period: LlmStats["all_time"] }) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: "18px 22px", minWidth: 200, flex: 1 }}>
      <p style={{ fontSize: 11, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>{label}</p>
      <p style={{ fontSize: 28, fontWeight: 700, color: "#0f172a", marginBottom: 12 }}>{fmtCost(period.cost_usd)}</p>
      <div style={{ fontSize: 13, color: "#64748b", lineHeight: "1.7" }}>
        <div>{fmtNum(period.calls)} calls</div>
        <div>{fmtNum(period.input_tokens)} input tokens</div>
        <div>{fmtNum(period.output_tokens)} output tokens</div>
      </div>
    </div>
  );
}

function LlmTab() {
  const [data, setData] = useState<LlmStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminApi.getLlmStats()
      .then(setData)
      .catch((e) => setError(e?.response?.data?.detail ?? "Failed to load LLM stats"));
  }, []);

  if (error) return <div style={{ padding: 40, textAlign: "center", color: "#dc2626" }}>{error}</div>;
  if (!data) return <div style={{ padding: 40, textAlign: "center", color: "#94a3b8" }}>Loading…</div>;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <p style={{ fontSize: 13, color: "#64748b" }}>
        Model <code style={{ fontFamily: "monospace" }}>{data.model}</code> · ${data.pricing.input_per_million}/M input · ${data.pricing.output_per_million}/M output
      </p>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <LlmUsageCard label="Last 7 days"  period={data.last_7d} />
        <LlmUsageCard label="Last 30 days" period={data.last_30d} />
        <LlmUsageCard label="All time"     period={data.all_time} />
      </div>
      {data.all_time.calls === 0 && (
        <p style={{ fontSize: 13, color: "#94a3b8" }}>
          No emails scanned yet — usage will populate after the next Gmail sync runs.
        </p>
      )}
    </div>
  );
}

// ── Allowlist Tab ─────────────────────────────────────────────────────────────

function AllowlistTab() {
  const [items, setItems] = useState<AllowedEmail[] | null>(null);
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => adminApi.getAllowlist().then(setItems).catch(() => setItems([]));
  useEffect(() => { load(); }, []);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;
    setAdding(true); setError(null);
    try {
      await adminApi.addAllowedEmail(email.trim(), note.trim() || undefined);
      setEmail(""); setNote("");
      await load();
    } catch (err: unknown) {
      setError((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to add email");
    } finally { setAdding(false); }
  };

  const remove = async (entry: AllowedEmail) => {
    if (!confirm(`Remove ${entry.email} from the allowlist? They will no longer be able to log in.`)) return;
    await adminApi.removeAllowedEmail(entry.id);
    await load();
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <p style={{ fontSize: 13, color: "#64748b", margin: 0 }}>
        While invite-only mode is on, only these emails can register or log in (admins are always exempt).
      </p>

      <Card style={{ padding: "16px 18px" }}>
        <form onSubmit={add} style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
          <div style={{ flex: "1 1 220px" }}>
            <label style={{ fontSize: 12, fontWeight: 600, display: "block", color: "#374151", marginBottom: 4 }}>Email</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                   placeholder="alpha-user@example.com" style={{ width: "100%" }} required />
          </div>
          <div style={{ flex: "1 1 180px" }}>
            <label style={{ fontSize: 12, fontWeight: 600, display: "block", color: "#374151", marginBottom: 4 }}>Note (optional)</label>
            <input value={note} onChange={(e) => setNote(e.target.value)}
                   placeholder="e.g. cohort 1 / referred by Jane" style={{ width: "100%" }} />
          </div>
          <button type="submit" disabled={adding}
                  style={{ padding: "8px 18px", background: "#2563eb", color: "#fff", border: "none",
                           borderRadius: 6, fontSize: 14, fontWeight: 600, cursor: "pointer" }}>
            {adding ? "Adding…" : "Add"}
          </button>
        </form>
        {error && <p style={{ color: "#dc2626", fontSize: 13, margin: "8px 0 0" }}>{error}</p>}
      </Card>

      <Card>
        {items === null ? (
          <div style={{ padding: 40, textAlign: "center", color: "#94a3b8" }}>Loading…</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Email</th>
                <th>Note</th>
                <th>Added</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr><td colSpan={4} style={{ textAlign: "center", color: "#94a3b8", padding: 32 }}>No emails on the allowlist yet</td></tr>
              ) : items.map((it) => (
                <tr key={it.id}>
                  <td style={{ fontFamily: "monospace", fontSize: 13 }}>{it.email}</td>
                  <td style={{ color: "#64748b", fontSize: 13 }}>{it.note ?? "—"}</td>
                  <td style={{ color: "#94a3b8", fontSize: 13, whiteSpace: "nowrap" }}>{new Date(it.created_at).toLocaleDateString()}</td>
                  <td style={{ textAlign: "right" }}>
                    <button onClick={() => remove(it)}
                            style={{ padding: "4px 10px", background: "#fff", border: "1px solid #fecaca",
                                     color: "#dc2626", borderRadius: 6, fontSize: 12, cursor: "pointer" }}>
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

// ── Feedback Insights Tab ─────────────────────────────────────────────────────

function FeedbackTab() {
  const [data, setData] = useState<FeedbackInsights | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminApi.getFeedbackInsights().then(setData).catch(() => setError("Failed to load feedback insights"));
  }, []);

  if (error) return <Card><p style={{ color: "#dc2626", margin: 0 }}>{error}</p></Card>;
  if (!data) return <Card><div style={{ padding: 40, textAlign: "center", color: "#94a3b8" }}>Loading…</div></Card>;

  const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(0)}%`);
  const conf = (v: number | null) => (v === null ? "—" : v.toFixed(2));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <p style={{ fontSize: 13, color: "#64748b", margin: 0 }}>
        Real-world classifier calibration from parent feedback. Use the per-category false-positive
        rate and the confidence gap (avg confidence on false positives vs. correct alerts) to tune the
        confidence threshold — globally or per category.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12 }}>
        <StatCard label="Labeled alerts" value={data.overall.labeled} />
        <StatCard label="Precision" value={pct(data.overall.precision)} />
        <StatCard label="False positives" value={data.overall.false_positive} warn={data.overall.false_positive > 0} />
        <StatCard label={`FPs ≥ threshold (${data.confidence_threshold})`} value={data.overall.false_positives_above_threshold} warn={data.overall.false_positives_above_threshold > 0} />
      </div>

      <Card>
        {data.by_category.length === 0 ? (
          <div style={{ padding: 32, textAlign: "center", color: "#94a3b8" }}>
            No parent feedback yet — insights appear once parents mark alerts correct or false-positive.
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Category</th>
                <th>Labeled</th>
                <th>Correct</th>
                <th>False pos.</th>
                <th>FP rate</th>
                <th>Avg conf. (FP)</th>
                <th>Avg conf. (correct)</th>
              </tr>
            </thead>
            <tbody>
              {data.by_category.map((c) => (
                <tr key={c.category}>
                  <td style={{ fontWeight: 500 }}>{c.category}</td>
                  <td>{c.labeled}</td>
                  <td>{c.correct}</td>
                  <td style={{ color: c.false_positive > 0 ? "#dc2626" : undefined }}>{c.false_positive}</td>
                  <td>{pct(c.fp_rate)}</td>
                  <td>{conf(c.avg_fp_confidence)}</td>
                  <td>{conf(c.avg_correct_confidence)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

// ── Waitlist Tab ──────────────────────────────────────────────────────────────

function WaitlistTab() {
  const [items, setItems] = useState<WaitlistEntry[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = () => adminApi.getWaitlist().then(setItems).catch(() => setItems([]));
  useEffect(() => { load(); }, []);

  const approve = async (entry: WaitlistEntry) => {
    if (!confirm(`Approve ${entry.email}? They'll be added to the allowlist and can register.`)) return;
    setBusy(entry.id);
    try { await adminApi.approveWaitlistEntry(entry.id); await load(); }
    finally { setBusy(null); }
  };

  const remove = async (entry: WaitlistEntry) => {
    if (!confirm(`Remove ${entry.email} from the waitlist?`)) return;
    setBusy(entry.id);
    try { await adminApi.removeWaitlistEntry(entry.id); await load(); }
    finally { setBusy(null); }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <p style={{ fontSize: 13, color: "#64748b", margin: 0 }}>
        Invite requests from the public landing page. Approving an entry adds it to the allowlist (so they can register) and removes it from the waitlist.
      </p>

      <Card>
        {items === null ? (
          <div style={{ padding: 40, textAlign: "center", color: "#94a3b8" }}>Loading…</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Email</th>
                <th>Source</th>
                <th>Requested</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr><td colSpan={4} style={{ textAlign: "center", color: "#94a3b8", padding: 32 }}>No invite requests yet</td></tr>
              ) : items.map((it) => (
                <tr key={it.id}>
                  <td style={{ fontFamily: "monospace", fontSize: 13 }}>{it.email}</td>
                  <td style={{ color: "#64748b", fontSize: 13 }}>{it.source ?? "—"}</td>
                  <td style={{ color: "#94a3b8", fontSize: 13, whiteSpace: "nowrap" }}>{new Date(it.created_at).toLocaleDateString()}</td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <button onClick={() => approve(it)} disabled={busy === it.id}
                            style={{ padding: "4px 10px", background: "#2563eb", border: "none",
                                     color: "#fff", borderRadius: 6, fontSize: 12, cursor: "pointer", marginRight: 8 }}>
                      Approve
                    </button>
                    <button onClick={() => remove(it)} disabled={busy === it.id}
                            style={{ padding: "4px 10px", background: "#fff", border: "1px solid #fecaca",
                                     color: "#dc2626", borderRadius: 6, fontSize: 12, cursor: "pointer" }}>
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

// ── Analytics tab ───────────────────────────────────────────────────────────────

const pct = (x: number | null | undefined) => (x == null ? "—" : `${(x * 100).toFixed(1)}%`);

function fmtDuration(secs: number | null): string {
  if (secs == null) return "—";
  if (secs < 90) return `${Math.round(secs)}s`;
  if (secs < 5400) return `${Math.round(secs / 60)}m`;
  if (secs < 172800) return `${(secs / 3600).toFixed(1)}h`;
  return `${(secs / 86400).toFixed(1)}d`;
}

function FunnelView({ stages }: { stages: FunnelStage[] }) {
  const top = stages[0]?.count || 0;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {stages.map((s, i) => {
        const widthPct = top ? Math.max((s.count / top) * 100, 2) : 0;
        return (
          <div key={s.key}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 3 }}>
              <span style={{ fontWeight: 600, color: "#0f172a" }}>{s.label}</span>
              <span style={{ color: "#64748b" }}>
                {fmtNum(s.count)}
                {i > 0 && s.step_conversion != null && (
                  <>
                    {" · "}<span style={{ color: "#16a34a" }}>{pct(s.step_conversion)}</span>
                    {" "}<span style={{ color: "#dc2626" }}>(−{pct(s.drop_off)})</span>
                  </>
                )}
              </span>
            </div>
            <div style={{ background: "#f1f5f9", borderRadius: 6, height: 22, overflow: "hidden" }}>
              <div style={{ width: `${widthPct}%`, height: "100%", background: "#2563eb" }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function AnalyticsTab() {
  const [days, setDays] = useState(30);
  const [ov, setOv] = useState<AnalyticsOverview | null>(null);
  const [fn, setFn] = useState<AnalyticsFunnel | null>(null);
  const [ev, setEv] = useState<AnalyticsEvents | null>(null);

  useEffect(() => {
    analyticsApi.overview(days).then(setOv);
    analyticsApi.funnel(days).then(setFn);
    analyticsApi.events(days).then(setEv);
  }, [days]);

  if (!ov || !fn || !ev) return <p style={{ color: "#64748b" }}>Loading…</p>;

  const listRow = (label: string, count: number, mono = false) => (
    <div key={label} style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 13, padding: "3px 0" }}>
      <span style={{ color: "#475569", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                     fontFamily: mono ? "monospace" : undefined, fontSize: mono ? 12 : 13 }}>{label}</span>
      <span style={{ fontWeight: 600 }}>{fmtNum(count)}</span>
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", gap: 8 }}>
        {[7, 30, 90].map((d) => (
          <button key={d} onClick={() => setDays(d)} style={{
            padding: "4px 12px", borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: "pointer",
            border: "1px solid #e2e8f0",
            background: days === d ? "#2563eb" : "#fff", color: days === d ? "#fff" : "#64748b",
          }}>{d}d</button>
        ))}
      </div>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <StatCard label="Unique visitors" value={fmtNum(ov.unique_visitors)} />
        <StatCard label="Page views" value={fmtNum(ov.page_views)} />
        <StatCard label="Waitlist" value={fmtNum(ov.waitlist_joined)} />
        <StatCard label="Signups" value={fmtNum(ov.signups)} />
        <StatCard label="Activated" value={fmtNum(ov.activated)} />
        <StatCard label="Activation rate" value={pct(ov.activation_rate)} />
        <StatCard label="Logins" value={fmtNum(ov.logins)} />
        <StatCard label="Deletions" value={fmtNum(ov.account_deletions)} warn={ov.account_deletions > 0} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <Card style={{ padding: 18 }}>
          <h3 style={{ fontSize: 15, marginBottom: 2 }}>Acquisition</h3>
          <p style={{ fontSize: 12, color: "#94a3b8", marginBottom: 14 }}>By event time, last {days}d</p>
          <FunnelView stages={fn.acquisition} />
        </Card>
        <Card style={{ padding: 18 }}>
          <h3 style={{ fontSize: 15, marginBottom: 2 }}>Activation (signup cohort)</h3>
          <p style={{ fontSize: 12, color: "#94a3b8", marginBottom: 14 }}>
            Signed up in last {days}d · time-to-value {fmtDuration(fn.activation.time_to_value_seconds)} · activation {pct(fn.activation.activation_rate)}
          </p>
          <FunnelView stages={fn.activation.stages} />
        </Card>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
        <Card style={{ padding: 18 }}>
          <h3 style={{ fontSize: 15, marginBottom: 12 }}>Events</h3>
          {ev.by_name.length === 0
            ? <p style={{ color: "#94a3b8", fontSize: 13 }}>No events yet.</p>
            : ev.by_name.map((r) => listRow(r.event, r.count, true))}
        </Card>
        <Card style={{ padding: 18 }}>
          <h3 style={{ fontSize: 15, marginBottom: 12 }}>Top pages</h3>
          {ev.top_paths.length === 0
            ? <p style={{ color: "#94a3b8", fontSize: 13 }}>No page views yet.</p>
            : ev.top_paths.map((r) => listRow(r.path, r.count))}
        </Card>
        <Card style={{ padding: 18 }}>
          <h3 style={{ fontSize: 15, marginBottom: 12 }}>Top referrers</h3>
          {ev.top_referrers.length === 0
            ? <p style={{ color: "#94a3b8", fontSize: 13 }}>Direct / none.</p>
            : ev.top_referrers.map((r) => listRow(r.referrer, r.count))}
        </Card>
      </div>
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
        {(["overview", "analytics", "llm", "feedback", "allowlist", "waitlist", "events", "tasks"] as Tab[]).map((t) => (
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
            {t === "llm" ? "LLM Usage" : t}
          </button>
        ))}
      </div>

      {tab === "overview"  && <OverviewTab />}
      {tab === "analytics" && <AnalyticsTab />}
      {tab === "llm"       && <LlmTab />}
      {tab === "feedback"  && <FeedbackTab />}
      {tab === "allowlist" && <AllowlistTab />}
      {tab === "waitlist"  && <WaitlistTab />}
      {tab === "events"    && <EventsTab />}
      {tab === "tasks"     && <TasksTab />}
    </div>
  );
}
