import { useEffect, useState } from "react";
import {
  monitoringApi,
  HealthSnapshot,
  Incident,
  AgentStatus,
  AgentRun,
} from "@/api/monitoring";

const SEVERITY_COLOR: Record<string, string> = {
  critical: "#b91c1c",
  warning: "#b45309",
  info: "#2563eb",
};
const STATUS_COLOR: Record<string, string> = {
  ok: "#16a34a",
  warning: "#b45309",
  critical: "#b91c1c",
};
const REM_STATUS_COLOR: Record<string, string> = {
  attempted: "#16a34a",
  escalated: "#7c3aed",
  diagnosed: "#2563eb",
  failed: "#b91c1c",
  none: "#64748b",
};

const wrap: React.CSSProperties = { maxWidth: 1000, margin: "0 auto", padding: 24 };
const card: React.CSSProperties = {
  background: "#fff",
  border: "1px solid #e2e8f0",
  borderRadius: 10,
  padding: 16,
};

function Badge({ text, color }: { text: string; color: string }) {
  return (
    <span style={{
      fontSize: 12, fontWeight: 700, padding: "2px 10px", borderRadius: 99,
      background: `${color}1a`, color, textTransform: "uppercase", letterSpacing: "0.02em",
    }}>
      {text}
    </span>
  );
}

function Btn({ children, onClick, disabled, tone = "default" }: {
  children: React.ReactNode; onClick: () => void; disabled?: boolean; tone?: "default" | "primary" | "danger";
}) {
  const bg = tone === "primary" ? "#2563eb" : tone === "danger" ? "#fff" : "#fff";
  const color = tone === "primary" ? "#fff" : tone === "danger" ? "#b91c1c" : "#334155";
  const border = tone === "primary" ? "none" : tone === "danger" ? "1px solid #fecaca" : "1px solid #e2e8f0";
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "6px 14px", borderRadius: 6, fontSize: 13, fontWeight: 600,
        cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.5 : 1,
        border, background: bg, color,
      }}
    >
      {children}
    </button>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ ...card, flex: 1, minWidth: 130 }}>
      <div style={{ fontSize: 12, color: "#64748b", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: "#0f172a" }}>{value}</div>
    </div>
  );
}

// ── Health tab ──────────────────────────────────────────────────────────────

function IncidentCard({ inc, onChange }: { inc: Incident; onChange: () => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const setStatus = async (status: string) => {
    setBusy(true);
    try {
      await monitoringApi.setStatus(inc.id, status);
      onChange();
    } finally {
      setBusy(false);
    }
  };

  const sevColor = SEVERITY_COLOR[inc.severity] || "#64748b";
  const actions = inc.remediation?.actions || [];

  return (
    <div style={{ ...card, padding: 0, overflow: "hidden" }}>
      <div
        onClick={() => setOpen((o) => !o)}
        style={{ display: "flex", alignItems: "center", gap: 12, padding: 16, cursor: "pointer" }}
      >
        <Badge text={inc.severity} color={sevColor} />
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, color: "#0f172a" }}>{inc.title}</div>
          <div style={{ fontSize: 12, color: "#64748b" }}>
            {inc.check_name} · seen {inc.times_seen}× · {new Date(inc.created_at).toLocaleString()}
          </div>
        </div>
        <Badge
          text={inc.status}
          color={inc.status === "resolved" ? "#16a34a" : inc.status === "acknowledged" ? "#2563eb" : "#b45309"}
        />
      </div>

      {open && (
        <div style={{ borderTop: "1px solid #f1f5f9", padding: 16, background: "#f8fafc" }}>
          <p style={{ margin: "0 0 12px", color: "#334155", fontSize: 14 }}>{inc.detail}</p>

          {inc.diagnosis && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#64748b", marginBottom: 4 }}>
                AGENT DIAGNOSIS {inc.remediation?.mode ? `(${inc.remediation.mode})` : ""}
              </div>
              <p style={{ margin: 0, color: "#0f172a", fontSize: 14, whiteSpace: "pre-wrap" }}>{inc.diagnosis}</p>
            </div>
          )}

          <div style={{ fontSize: 13, color: "#475569", marginBottom: 8 }}>
            Remediation status: <strong>{inc.remediation_status || "none"}</strong>
            {inc.remediation?.cost_usd != null && ` · $${inc.remediation.cost_usd.toFixed(4)}`}
          </div>

          {actions.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#64748b", marginBottom: 4 }}>
                ACTIONS TAKEN
              </div>
              {actions.map((a, i) => (
                <div key={i} style={{ fontSize: 12, fontFamily: "monospace", color: "#334155", marginBottom: 2 }}>
                  {a.tool}({JSON.stringify(a.input)}) → {JSON.stringify(a.result)}
                </div>
              ))}
            </div>
          )}

          {inc.metrics && (
            <details style={{ marginBottom: 12 }}>
              <summary style={{ fontSize: 12, color: "#64748b", cursor: "pointer" }}>Metrics</summary>
              <pre style={{ fontSize: 11, background: "#0f172a", color: "#e2e8f0", padding: 10, borderRadius: 6, overflow: "auto" }}>
                {JSON.stringify(inc.metrics, null, 2)}
              </pre>
            </details>
          )}

          <div style={{ display: "flex", gap: 8 }}>
            {inc.status !== "acknowledged" && inc.status !== "resolved" && (
              <Btn onClick={() => setStatus("acknowledged")} disabled={busy}>Acknowledge</Btn>
            )}
            {inc.status !== "resolved" && (
              <Btn onClick={() => setStatus("resolved")} disabled={busy} tone="primary">Resolve</Btn>
            )}
            {inc.status === "resolved" && (
              <Btn onClick={() => setStatus("open")} disabled={busy}>Reopen</Btn>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function HealthTab() {
  const [health, setHealth] = useState<HealthSnapshot | null>(null);
  const [incidents, setIncidents] = useState<Incident[] | null>(null);
  const [filter, setFilter] = useState<"open" | "all" | "resolved">("open");
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () => {
    monitoringApi.getHealth().then(setHealth);
    const status = filter === "all" ? undefined : filter;
    monitoringApi.getIncidents(status).then((r) => setIncidents(r.data));
  };

  useEffect(() => { load(); }, [filter]);

  const runNow = async () => {
    setRunning(true);
    setMsg(null);
    try {
      await monitoringApi.runNow();
      setMsg("Monitoring cycle enqueued — refresh in a few seconds.");
    } finally {
      setRunning(false);
    }
  };

  if (!health) return <div>Loading…</div>;

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
        <Badge text={health.overall_status} color={STATUS_COLOR[health.overall_status] || "#64748b"} />
        <div style={{ flex: 1 }} />
        <Btn onClick={runNow} disabled={running} tone="primary">
          {running ? "Running…" : "Run check now"}
        </Btn>
      </div>

      {msg && (
        <div style={{ ...card, marginBottom: 16, background: "#eff6ff", borderColor: "#bfdbfe", color: "#1d4ed8", fontSize: 14 }}>
          {msg}
        </div>
      )}

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
        <Stat label="Monitoring" value={health.monitoring_enabled ? "On" : "Off"} />
        <Stat label="Auto-remediation" value={health.auto_remediation_enabled ? "On" : "Advisory"} />
        <Stat label="Redis" value={health.redis_ok ? "OK" : "DOWN"} />
        <Stat label="Queue depth" value={health.queue_depth ?? "—"} />
        <Stat
          label="Open incidents"
          value={Object.values(health.open_incidents_by_severity).reduce((a, b) => a + b, 0)}
        />
      </div>

      <div style={{ ...card, marginBottom: 24 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: "#64748b", marginBottom: 8 }}>
          GMAIL CONNECTIONS
        </div>
        <div style={{ display: "flex", gap: 16, fontSize: 14, color: "#334155" }}>
          {Object.keys(health.connections_by_status).length === 0 && <span>No connections.</span>}
          {Object.entries(health.connections_by_status).map(([s, n]) => (
            <span key={s}><strong>{n}</strong> {s}</span>
          ))}
        </div>
        {health.last_cycle && (
          <div style={{ marginTop: 12, fontSize: 12, color: "#94a3b8" }}>
            Last cycle: {health.last_cycle.status} at {new Date(health.last_cycle.created_at).toLocaleString()}
          </div>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, color: "#0f172a", margin: 0, flex: 1 }}>Incidents</h2>
        {(["open", "all", "resolved"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              padding: "4px 12px", borderRadius: 6, fontSize: 13, fontWeight: 600,
              border: "1px solid #e2e8f0", cursor: "pointer",
              background: filter === f ? "#2563eb" : "#fff",
              color: filter === f ? "#fff" : "#64748b", textTransform: "capitalize",
            }}
          >
            {f}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {incidents === null && <div>Loading incidents…</div>}
        {incidents?.length === 0 && (
          <div style={{ ...card, color: "#64748b", textAlign: "center" }}>
            No {filter === "all" ? "" : filter} incidents. 🎉
          </div>
        )}
        {incidents?.map((inc) => (
          <IncidentCard key={inc.id} inc={inc} onChange={load} />
        ))}
      </div>
    </>
  );
}

// ── Agent tab ───────────────────────────────────────────────────────────────

function AgentRunCard({ run }: { run: AgentRun }) {
  const [open, setOpen] = useState(false);
  const remColor = REM_STATUS_COLOR[run.remediation_status || "none"] || "#64748b";
  return (
    <div style={{ ...card, padding: 0, overflow: "hidden" }}>
      <div
        onClick={() => setOpen((o) => !o)}
        style={{ display: "flex", alignItems: "center", gap: 12, padding: 14, cursor: "pointer" }}
      >
        <Badge text={run.remediation_status || "—"} color={remColor} />
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, color: "#0f172a", fontSize: 14 }}>{run.title}</div>
          <div style={{ fontSize: 12, color: "#64748b" }}>
            {run.check_name} · {run.mode || "?"} · {run.turns ?? "?"} turns
            {run.cost_usd != null && ` · $${run.cost_usd.toFixed(4)}`} · {new Date(run.created_at).toLocaleString()}
          </div>
        </div>
        {run.actions.length > 0 && <span style={{ fontSize: 12, color: "#64748b" }}>{run.actions.length} action(s)</span>}
      </div>
      {open && (
        <div style={{ borderTop: "1px solid #f1f5f9", padding: 14, background: "#f8fafc" }}>
          {run.diagnosis && (
            <p style={{ margin: "0 0 10px", color: "#0f172a", fontSize: 14, whiteSpace: "pre-wrap" }}>{run.diagnosis}</p>
          )}
          {run.actions.length > 0 ? (
            run.actions.map((a, i) => (
              <div key={i} style={{ fontSize: 12, fontFamily: "monospace", color: "#334155", marginBottom: 2 }}>
                {a.tool}({JSON.stringify(a.input)}) → {JSON.stringify(a.result)}
              </div>
            ))
          ) : (
            <div style={{ fontSize: 13, color: "#94a3b8" }}>No actions taken (investigated only).</div>
          )}
        </div>
      )}
    </div>
  );
}

function AgentTab() {
  const [agent, setAgent] = useState<AgentStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () => monitoringApi.getAgent().then(setAgent);
  useEffect(() => { load(); }, []);

  if (!agent) return <div>Loading…</div>;

  const auto = agent.auto_remediation;

  const toggleAuto = async () => {
    const turningOn = !auto.effective;
    if (turningOn && !window.confirm(
      "Enable automated remediation?\n\nThe agent will start taking bounded fix actions " +
      "(re-enqueue polling, nudge a connection) on new incidents."
    )) return;
    setBusy(true);
    setMsg(null);
    try {
      await monitoringApi.setAutoRemediation(turningOn);
      await load();
      setMsg(turningOn ? "Automated remediation is ON." : "Automated remediation is OFF (advisory only).");
    } finally {
      setBusy(false);
    }
  };

  const runNow = async () => {
    setBusy(true);
    try {
      await monitoringApi.runNow();
      setMsg("Monitoring cycle enqueued — refresh in a few seconds.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {/* Control card */}
      <div style={{ ...card, marginBottom: 16, display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 240 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#64748b", marginBottom: 4 }}>
            AUTOMATED REMEDIATION
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Badge
              text={auto.effective ? "On" : "Advisory"}
              color={auto.effective ? "#16a34a" : "#64748b"}
            />
            <span style={{ fontSize: 12, color: "#94a3b8" }}>
              {auto.override === null
                ? `following env default (${auto.env_default ? "on" : "off"})`
                : "overridden from this console"}
            </span>
          </div>
          <p style={{ margin: "8px 0 0", fontSize: 13, color: "#64748b" }}>
            {auto.effective
              ? "The agent will take bounded, idempotent fix actions on new incidents."
              : "The agent investigates and recommends only — it will not act until enabled."}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Btn onClick={toggleAuto} disabled={busy} tone={auto.effective ? "danger" : "primary"}>
            {auto.effective ? "Turn off" : "Turn on"}
          </Btn>
          <Btn onClick={runNow} disabled={busy}>Run cycle now</Btn>
        </div>
      </div>

      {msg && (
        <div style={{ ...card, marginBottom: 16, background: "#eff6ff", borderColor: "#bfdbfe", color: "#1d4ed8", fontSize: 14 }}>
          {msg}
        </div>
      )}

      {/* Stats */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
        <Stat label="Agent runs" value={agent.stats.total_runs} />
        <Stat label="Fixes attempted" value={agent.stats.by_status.attempted ?? 0} />
        <Stat label="Escalated" value={agent.stats.by_status.escalated ?? 0} />
        <Stat label="Fix actions taken" value={agent.stats.total_fix_actions} />
        <Stat label="Total LLM cost" value={`$${agent.stats.total_cost_usd.toFixed(4)}`} />
      </div>

      <div style={{ ...card, marginBottom: 24, fontSize: 13, color: "#475569" }}>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <span>Model: <strong>{agent.model}</strong></span>
          <span>Interval: every <strong>{agent.monitoring_interval_minutes} min</strong></span>
          <span>By status: {Object.entries(agent.stats.by_status).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"}</span>
          <span>By mode: {Object.entries(agent.stats.by_mode).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"}</span>
        </div>
        {agent.last_cycle && (
          <div style={{ marginTop: 10, fontSize: 12, color: "#94a3b8" }}>
            Last cycle: {agent.last_cycle.status} at {new Date(agent.last_cycle.created_at).toLocaleString()}
            {agent.last_cycle.error ? ` — ${agent.last_cycle.error}` : ""}
          </div>
        )}
      </div>

      <h2 style={{ fontSize: 18, fontWeight: 700, color: "#0f172a", margin: "0 0 12px" }}>Recent agent runs</h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {agent.runs.length === 0 && (
          <div style={{ ...card, color: "#64748b", textAlign: "center" }}>
            The agent hasn't run yet. It activates when a probe opens a new incident.
          </div>
        )}
        {agent.runs.map((run) => (
          <AgentRunCard key={run.incident_id} run={run} />
        ))}
      </div>
    </>
  );
}

// ── Page shell with tabs ──────────────────────────────────────────────────────

export default function Monitoring() {
  const [tab, setTab] = useState<"health" | "agent">("health");

  return (
    <div style={wrap}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 20 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: "#0f172a", margin: 0, flex: 1 }}>
          Monitoring
        </h1>
        {(["health", "agent"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: "6px 16px", borderRadius: 6, fontSize: 14, fontWeight: 600,
              border: "1px solid #e2e8f0", cursor: "pointer",
              background: tab === t ? "#2563eb" : "#fff",
              color: tab === t ? "#fff" : "#64748b", textTransform: "capitalize",
            }}
          >
            {t === "health" ? "Health" : "Agent"}
          </button>
        ))}
      </div>

      {tab === "health" ? <HealthTab /> : <AgentTab />}
    </div>
  );
}
