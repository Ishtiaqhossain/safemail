import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { alertsApi } from "@/api/alerts";
import { AlertBadge } from "@/components/AlertBadge";
import type { Alert } from "@/types";

const CATEGORY_LABELS: Record<string, string> = {
  self_harm: "Self-Harm",
  grooming: "Grooming",
  bullying: "Bullying / Harassment",
  drugs_alcohol: "Drugs / Alcohol",
  stranger_contact: "Stranger Contact",
  personal_info_sharing: "Personal Information Sharing",
};

export default function AlertDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [alert, setAlert] = useState<Alert | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    alertsApi.list({ per_page: 1 }).then(() => {});
    // Fetch single alert by listing with high specificity — replace with dedicated endpoint if added
    alertsApi.list({ per_page: 100 }).then((r) => {
      const found = r.data.find((a) => a.id === id);
      if (found) {
        setAlert(found);
        setFeedback(found.parent_feedback);
        if (!found.reviewed_at) alertsApi.markReviewed(found.id);
      }
    });
  }, [id]);

  const submitFeedback = async (value: "correct" | "false_positive") => {
    if (!alert) return;
    await alertsApi.submitFeedback(alert.id, value);
    setFeedback(value);
  };

  if (!alert) return <p style={{ padding: 24 }}>Loading...</p>;

  return (
    <div style={{ padding: 24, maxWidth: 700, margin: "0 auto" }}>
      <button onClick={() => navigate(-1)} style={{ marginBottom: 16, cursor: "pointer" }}>← Back</button>

      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
        <AlertBadge severity={alert.severity} />
        <span style={{ color: "#6b7280", fontSize: 14 }}>{CATEGORY_LABELS[alert.category] ?? alert.category}</span>
      </div>

      <h2 style={{ marginBottom: 4 }}>Alert for {alert.child_name}</h2>
      <p style={{ color: "#6b7280", fontSize: 13, marginBottom: 24 }}>
        {new Date(alert.received_at).toLocaleString()} · {alert.direction === "inbound" ? "Received from" : "Sent to"} {alert.sender_address}
      </p>

      <section style={{ background: "#f9fafb", borderRadius: 8, padding: 16, marginBottom: 20 }}>
        <h4 style={{ marginBottom: 8 }}>What we found</h4>
        <p>{alert.ai_summary}</p>
      </section>

      {alert.ai_response_script && (
        <section style={{ background: "#eff6ff", borderRadius: 8, padding: 16, marginBottom: 20 }}>
          <h4 style={{ marginBottom: 8 }}>Suggested next step</h4>
          <p>{alert.ai_response_script}</p>
        </section>
      )}

      <section style={{ borderTop: "1px solid #e5e7eb", paddingTop: 16 }}>
        <h4 style={{ marginBottom: 8 }}>Was this alert helpful?</h4>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={() => submitFeedback("correct")}
            style={{ padding: "6px 16px", background: feedback === "correct" ? "#16a34a" : "#e5e7eb", color: feedback === "correct" ? "#fff" : "#111", borderRadius: 4, border: "none", cursor: "pointer" }}
          >
            Yes, correct
          </button>
          <button
            onClick={() => submitFeedback("false_positive")}
            style={{ padding: "6px 16px", background: feedback === "false_positive" ? "#dc2626" : "#e5e7eb", color: feedback === "false_positive" ? "#fff" : "#111", borderRadius: 4, border: "none", cursor: "pointer" }}
          >
            False positive
          </button>
        </div>
        {feedback && <p style={{ marginTop: 8, fontSize: 13, color: "#6b7280" }}>Feedback recorded. Thank you.</p>}
      </section>
    </div>
  );
}
