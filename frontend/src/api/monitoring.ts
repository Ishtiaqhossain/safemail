import api from "./client";

export interface HealthSnapshot {
  overall_status: "ok" | "warning" | "critical";
  checked_at: string;
  monitoring_enabled: boolean;
  auto_remediation_enabled: boolean;
  redis_ok: boolean;
  queue_depth: number | null;
  connections_by_status: Record<string, number>;
  open_incidents_by_severity: Record<string, number>;
  last_cycle: { status: string; created_at: string; meta: Record<string, unknown> | null; error: string | null } | null;
}

export interface RemediationAction {
  tool: string;
  input: Record<string, unknown>;
  result: Record<string, unknown>;
}

export interface Remediation {
  mode?: string;
  status?: string;
  diagnosis?: string;
  actions?: RemediationAction[];
  model?: string;
  turns?: number;
  cost_usd?: number;
}

export interface Incident {
  id: string;
  fingerprint: string;
  check_name: string;
  severity: string;
  status: string;
  title: string;
  detail: string;
  metrics: Record<string, unknown> | null;
  diagnosis: string | null;
  remediation_status: string | null;
  remediation: Remediation | null;
  times_seen: number;
  alerted_at: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface IncidentList {
  data: Incident[];
  meta: { total: number; page: number; per_page: number };
}

export interface AgentRun {
  incident_id: string;
  title: string;
  check_name: string;
  severity: string;
  incident_status: string;
  mode: string | null;
  remediation_status: string | null;
  turns: number | null;
  cost_usd: number | null;
  diagnosis: string | null;
  actions: RemediationAction[];
  created_at: string;
}

export interface AgentStatus {
  monitoring_enabled: boolean;
  monitoring_interval_minutes: number;
  model: string;
  auto_remediation: { effective: boolean; override: boolean | null; env_default: boolean };
  last_cycle: { status: string; created_at: string; meta: Record<string, unknown> | null; error: string | null } | null;
  stats: {
    total_runs: number;
    by_status: Record<string, number>;
    by_mode: Record<string, number>;
    total_fix_actions: number;
    total_cost_usd: number;
  };
  runs: AgentRun[];
}

export const monitoringApi = {
  getHealth: () => api.get<HealthSnapshot>("/monitoring/health").then((r) => r.data),

  getIncidents: (status?: string, page = 1) =>
    api
      .get<IncidentList>("/monitoring/incidents", { params: { status, page, per_page: 50 } })
      .then((r) => r.data),

  getIncident: (id: string) =>
    api.get<Incident>(`/monitoring/incidents/${id}`).then((r) => r.data),

  runNow: () => api.post<{ status: string }>("/monitoring/run").then((r) => r.data),

  setStatus: (id: string, status: string) =>
    api.post<Incident>(`/monitoring/incidents/${id}/status`, { status }).then((r) => r.data),

  getAgent: () => api.get<AgentStatus>("/monitoring/agent").then((r) => r.data),

  setAutoRemediation: (enabled: boolean | null) =>
    api
      .post<AgentStatus["auto_remediation"]>("/monitoring/agent/auto-remediation", { enabled })
      .then((r) => r.data),
};
