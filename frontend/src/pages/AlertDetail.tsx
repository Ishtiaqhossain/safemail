import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { alertsApi } from "@/api/alerts";
import type { Alert, Severity } from "@/types";
import { track } from "@/analytics";

// ─── constants ────────────────────────────────────────────────────────────────

const SEVERITY_COLOR: Record<Severity, string> = {
  critical: "#dc2626",
  high:     "#ea580c",
  medium:   "#d97706",
  low:      "#16a34a",
};

const SEVERITY_BG: Record<Severity, string> = {
  critical: "#fef2f2",
  high:     "#fff7ed",
  medium:   "#fffbeb",
  low:      "#f0fdf4",
};

const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "Critical",
  high:     "High",
  medium:   "Medium",
  low:      "Low",
};

const CATEGORY_LABEL: Record<string, string> = {
  self_harm:            "Self-Harm",
  grooming:             "Grooming",
  bullying:             "Bullying",
  drugs_alcohol:        "Drugs & Alcohol",
  stranger_contact:     "Stranger Contact",
  personal_info_sharing:"Personal Info",
};

const CATEGORY_ICON: Record<string, string> = {
  self_harm:            "🆘",
  grooming:             "⚠️",
  bullying:             "😔",
  drugs_alcohol:        "🚫",
  stranger_contact:     "👤",
  personal_info_sharing:"🔒",
};

function confidenceLabel(c: number): string {
  if (c >= 0.9) return "Very high";
  if (c >= 0.75) return "High";
  if (c >= 0.6) return "Moderate";
  return "Low";
}

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    weekday: "short", month: "short", day: "numeric",
    year: "numeric", hour: "numeric", minute: "2-digit",
  });
}

// ─── subcomponents ────────────────────────────────────────────────────────────

function Card({ children, style = {} }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: "#fff",
      border: "1px solid #e5e7eb",
      borderRadius: 10,
      padding: "18px 20px",
      ...style,
    }}>
      {children}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "#9ca3af", margin: "0 0 8px" }}>
      {children}
    </p>
  );
}

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: "flex", gap: 12, padding: "6px 0", borderBottom: "1px solid #f3f4f6", alignItems: "flex-start" }}>
      <span style={{ fontSize: 13, color: "#9ca3af", minWidth: 80, flexShrink: 0 }}>{label}</span>
      <span style={{ fontSize: 13, color: "#111827", wordBreak: "break-word" }}>{value}</span>
    </div>
  );
}

// ─── page ─────────────────────────────────────────────────────────────────────

export default function AlertDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [alert, setAlert] = useState<Alert | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [feedbackSaved, setFeedbackSaved] = useState(false);

  useEffect(() => {
    if (!id) return;
    alertsApi.list({ per_page: 100 }).then((r) => {
      const found = r.data.find((a) => a.id === id);
      if (found) {
        setAlert(found);
        setFeedback(found.parent_feedback);
        track("alert_viewed", { severity: found.severity, category: found.category });
        if (!found.reviewed_at) alertsApi.markReviewed(found.id);
      }
    });
  }, [id]);

  const submitFeedback = async (value: "correct" | "false_positive") => {
    if (!alert) return;
    await alertsApi.submitFeedback(alert.id, value);
    setFeedback(value);
    setFeedbackSaved(true);
  };

  if (!alert) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "#9ca3af" }}>
        Loading alert…
      </div>
    );
  }

  const color  = SEVERITY_COLOR[alert.severity];
  const bgTint = SEVERITY_BG[alert.severity];

  return (
    <div style={{ padding: "24px 20px", maxWidth: 680, margin: "0 auto" }}>

      {/* Back */}
      <button
        onClick={() => navigate(-1)}
        style={{ display: "flex", alignItems: "center", gap: 4, background: "none", border: "none", cursor: "pointer", color: "#6b7280", fontSize: 14, padding: 0, marginBottom: 20 }}
      >
        ← Back to alerts
      </button>

      {/* ── Hero severity banner ───────────────────────────────────────────── */}
      <div style={{
        background: bgTint,
        border: `1px solid ${color}30`,
        borderLeft: `4px solid ${color}`,
        borderRadius: 10,
        padding: "16px 20px",
        marginBottom: 16,
        display: "flex",
        alignItems: "flex-start",
        gap: 14,
      }}>
        <span style={{ fontSize: 28, lineHeight: 1, marginTop: 2 }}>
          {CATEGORY_ICON[alert.category] ?? "⚠️"}
        </span>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 4 }}>
            <span style={{
              fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase",
              color, background: `${color}18`, padding: "2px 8px", borderRadius: 4,
            }}>
              {SEVERITY_LABEL[alert.severity]}
            </span>
            <span style={{ fontSize: 13, color: "#6b7280" }}>
              {CATEGORY_LABEL[alert.category] ?? alert.category}
            </span>
            <span style={{ fontSize: 13, color: "#9ca3af" }}>·</span>
            <span style={{ fontSize: 13, color: "#6b7280" }}>
              {alert.direction === "inbound" ? "Received" : "Sent"} by {alert.child_name}
            </span>
          </div>
          <p style={{ margin: 0, fontSize: 15, color: "#111827", lineHeight: 1.5 }}>
            {alert.ai_summary}
          </p>
          <p style={{ margin: "6px 0 0", fontSize: 12, color: "#9ca3af" }}>
            Detected {formatDateTime(alert.received_at)} · AI confidence: {confidenceLabel(alert.confidence)} ({Math.round(alert.confidence * 100)}%)
          </p>
        </div>
      </div>

      {/* ── Email metadata ─────────────────────────────────────────────────── */}
      <Card style={{ marginBottom: 14 }}>
        <SectionLabel>Email details</SectionLabel>
        <MetaRow label="From"    value={alert.sender_address} />
        <MetaRow label="To"      value={alert.recipient_addresses.join(", ")} />
        {alert.subject_snippet && (
          <MetaRow label="Subject" value={<em style={{ color: "#374151" }}>{alert.subject_snippet}</em>} />
        )}
        <MetaRow label="Date"    value={formatDateTime(alert.received_at)} />
        <MetaRow label="Child"   value={alert.child_name} />
        <div style={{ borderBottom: "none", padding: "6px 0 0", display: "flex", gap: 6 }}>
          <span style={{ fontSize: 13, color: "#9ca3af", minWidth: 80 }}>Direction</span>
          <span style={{
            fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em",
            padding: "1px 7px", borderRadius: 4,
            background: alert.direction === "inbound" ? "#eff6ff" : "#f0fdf4",
            color: alert.direction === "inbound" ? "#2563eb" : "#16a34a",
          }}>
            {alert.direction === "inbound" ? "↓ Inbound" : "↑ Outbound"}
          </span>
        </div>
      </Card>

      {/* ── Conversation guide ─────────────────────────────────────────────── */}
      {alert.ai_response_script && (
        <Card style={{ marginBottom: 14, borderLeft: "3px solid #2563eb", background: "#f8faff" }}>
          <SectionLabel>How to talk to your child</SectionLabel>
          <p style={{ margin: 0, fontSize: 14, color: "#1e3a5f", lineHeight: 1.6 }}>
            {alert.ai_response_script}
          </p>
        </Card>
      )}

      {/* ── Feedback ───────────────────────────────────────────────────────── */}
      <Card>
        <SectionLabel>Was this alert accurate?</SectionLabel>
        <p style={{ fontSize: 13, color: "#6b7280", margin: "0 0 12px" }}>
          Your feedback helps improve detection for all families.
        </p>
        <div style={{ display: "flex", gap: 10 }}>
          <button
            onClick={() => submitFeedback("correct")}
            disabled={feedbackSaved}
            style={{
              flex: 1, padding: "10px 12px", borderRadius: 6, cursor: feedbackSaved ? "default" : "pointer",
              border: feedback === "correct" ? "2px solid #16a34a" : "2px solid #e5e7eb",
              background: feedback === "correct" ? "#f0fdf4" : "#fff",
              color: feedback === "correct" ? "#16a34a" : "#374151",
              fontWeight: 600, fontSize: 14, transition: "all 0.15s",
            }}
          >
            {feedback === "correct" ? "✓ " : ""}Yes, this is real
          </button>
          <button
            onClick={() => submitFeedback("false_positive")}
            disabled={feedbackSaved}
            style={{
              flex: 1, padding: "10px 12px", borderRadius: 6, cursor: feedbackSaved ? "default" : "pointer",
              border: feedback === "false_positive" ? "2px solid #d97706" : "2px solid #e5e7eb",
              background: feedback === "false_positive" ? "#fffbeb" : "#fff",
              color: feedback === "false_positive" ? "#92400e" : "#374151",
              fontWeight: 600, fontSize: 14, transition: "all 0.15s",
            }}
          >
            {feedback === "false_positive" ? "✓ " : ""}Not a concern
          </button>
        </div>
        {feedbackSaved && (
          <p style={{ marginTop: 10, fontSize: 13, color: "#6b7280" }}>
            Thanks — feedback recorded.
          </p>
        )}
      </Card>

    </div>
  );
}
