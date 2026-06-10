import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { devApi } from "@/api/developer";

type Status = { type: "success" | "error"; message: string } | null;

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ border: "1px solid #e5e7eb", borderRadius: 8, padding: 20, marginBottom: 20 }}>
      <h3 style={{ margin: "0 0 16px", fontSize: 15, color: "#374151" }}>{title}</h3>
      {children}
    </section>
  );
}

function Feedback({ status }: { status: Status }) {
  if (!status) return null;
  const color = status.type === "success" ? "#16a34a" : "#dc2626";
  const bg = status.type === "success" ? "#f0fdf4" : "#fef2f2";
  return (
    <p style={{ marginTop: 10, fontSize: 13, color, background: bg, padding: "6px 12px", borderRadius: 4, display: "inline-block" }}>
      {status.message}
    </p>
  );
}

function ActionButton({
  label, onClick, danger = false, loading = false,
}: { label: string; onClick: () => void; danger?: boolean; loading?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      style={{
        padding: "7px 18px", cursor: loading ? "default" : "pointer", borderRadius: 4, border: "none",
        background: loading ? "#9ca3af" : danger ? "#dc2626" : "#2563eb",
        color: "#fff", fontSize: 14, fontWeight: 500,
      }}
    >
      {loading ? "Working…" : label}
    </button>
  );
}

export default function Developer() {
  const navigate = useNavigate();
  const [queueDepth, setQueueDepth] = useState<number | null>(null);

  // Per-section loading + status
  const [injectLoading, setInjectLoading] = useState(false);
  const [injectStatus, setInjectStatus] = useState<Status>(null);
  const [clearLoading, setClearLoading] = useState(false);
  const [clearStatus, setClearStatus] = useState<Status>(null);
  const [pollLoading, setPollLoading] = useState(false);
  const [pollStatus, setPollStatus] = useState<Status>(null);
  const [notifLoading, setNotifLoading] = useState(false);
  const [notifStatus, setNotifStatus] = useState<Status>(null);

  // Classifier playground
  const [emailBody, setEmailBody] = useState("");
  const [subject, setSubject] = useState("");
  const [sender, setSender] = useState("test@example.com");
  const [classifyLoading, setClassifyLoading] = useState(false);
  const [classifyResult, setClassifyResult] = useState<Record<string, unknown> | null>(null);
  const [classifyError, setClassifyError] = useState<string | null>(null);

  useEffect(() => {
    devApi.queueDepth().then((d) => setQueueDepth(d.pending)).catch(() => setQueueDepth(null));
  }, []);

  const handleInject = async () => {
    setInjectLoading(true);
    setInjectStatus(null);
    try {
      const r = await devApi.injectFakeAlerts();
      setInjectStatus({ type: "success", message: `Injected ${r.inserted} alerts for "${r.child_name}"` });
      navigate("/alerts");
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed";
      setInjectStatus({ type: "error", message: msg });
    } finally {
      setInjectLoading(false);
    }
  };

  const handleClear = async () => {
    if (!confirm("Delete all fake alerts?")) return;
    setClearLoading(true);
    setClearStatus(null);
    try {
      const r = await devApi.clearFakeData();
      setClearStatus({ type: "success", message: `Deleted ${r.deleted} fake alerts` });
    } catch {
      setClearStatus({ type: "error", message: "Failed to clear fake data" });
    } finally {
      setClearLoading(false);
    }
  };

  const handlePoll = async () => {
    setPollLoading(true);
    setPollStatus(null);
    try {
      await devApi.triggerPoll();
      setPollStatus({ type: "success", message: "Gmail poll queued — check the Celery worker logs" });
      devApi.queueDepth().then((d) => setQueueDepth(d.pending)).catch(() => {});
    } catch {
      setPollStatus({ type: "error", message: "Failed to queue poll" });
    } finally {
      setPollLoading(false);
    }
  };

  const handleNotification = async () => {
    setNotifLoading(true);
    setNotifStatus(null);
    try {
      const r = await devApi.testNotification();
      setNotifStatus({ type: "success", message: `Test email sent to ${r.sent_to}` });
    } catch {
      setNotifStatus({ type: "error", message: "Failed — check SENDGRID_API_KEY" });
    } finally {
      setNotifLoading(false);
    }
  };

  const handleClassify = async () => {
    if (!emailBody.trim()) return;
    setClassifyLoading(true);
    setClassifyResult(null);
    setClassifyError(null);
    try {
      const r = await devApi.classify({ email_body: emailBody, subject, sender });
      setClassifyResult(r);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Classification failed";
      setClassifyError(msg);
    } finally {
      setClassifyLoading(false);
    }
  };

  return (
    <div style={{ padding: 24, maxWidth: 800, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        <h2 style={{ margin: 0 }}>Developer Tools</h2>
        <span style={{ fontSize: 12, background: "#ede9fe", color: "#7c3aed", padding: "2px 10px", borderRadius: 99, fontWeight: 600 }}>
          DEV
        </span>
      </div>

      {/* ── Data Tools ──────────────────────────────────────────── */}
      <Section title="Test Data">
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-start" }}>
          <div>
            <ActionButton label="Inject Fake Alerts" onClick={handleInject} loading={injectLoading} />
            <p style={{ fontSize: 12, color: "#6b7280", margin: "4px 0 0" }}>
              Inserts 8 realistic alerts covering all categories and severities.
            </p>
            <Feedback status={injectStatus} />
          </div>
          <div>
            <ActionButton label="Clear Fake Data" onClick={handleClear} loading={clearLoading} danger />
            <p style={{ fontSize: 12, color: "#6b7280", margin: "4px 0 0" }}>
              Deletes all injected fake alerts (gmail_message_id starts with "fake_").
            </p>
            <Feedback status={clearStatus} />
          </div>
        </div>
      </Section>

      {/* ── Pipeline ────────────────────────────────────────────── */}
      <Section title="Pipeline">
        <div style={{ display: "flex", gap: 24, alignItems: "flex-start", flexWrap: "wrap" }}>
          <div>
            <ActionButton label="Trigger Gmail Poll Now" onClick={handlePoll} loading={pollLoading} />
            <p style={{ fontSize: 12, color: "#6b7280", margin: "4px 0 0" }}>
              Fires poll_all_connections immediately instead of waiting 5 min.
            </p>
            <Feedback status={pollStatus} />
          </div>
          <div style={{ border: "1px solid #e5e7eb", borderRadius: 6, padding: "10px 16px", minWidth: 120, textAlign: "center" }}>
            <p style={{ fontSize: 12, color: "#6b7280", margin: "0 0 4px" }}>Celery queue depth</p>
            <p style={{ fontSize: 28, fontWeight: 700, margin: 0 }}>{queueDepth ?? "—"}</p>
          </div>
        </div>
      </Section>

      {/* ── Classifier Playground ───────────────────────────────── */}
      <Section title="Classifier Playground">
        <p style={{ fontSize: 13, color: "#6b7280", marginTop: 0 }}>
          Paste email content to run it through Claude without creating an alert.
        </p>
        <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: 12, display: "block", marginBottom: 3 }}>Subject</label>
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Email subject"
              style={{ width: "100%", boxSizing: "border-box" }}
            />
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: 12, display: "block", marginBottom: 3 }}>Sender</label>
            <input
              value={sender}
              onChange={(e) => setSender(e.target.value)}
              placeholder="sender@example.com"
              style={{ width: "100%", boxSizing: "border-box" }}
            />
          </div>
        </div>
        <label style={{ fontSize: 12, display: "block", marginBottom: 3 }}>Email body</label>
        <textarea
          value={emailBody}
          onChange={(e) => setEmailBody(e.target.value)}
          placeholder="Paste email body here…"
          rows={6}
          style={{ width: "100%", boxSizing: "border-box", fontFamily: "monospace", fontSize: 13, resize: "vertical" }}
        />
        <div style={{ marginTop: 8 }}>
          <ActionButton label="Classify" onClick={handleClassify} loading={classifyLoading} />
        </div>
        {classifyError && (
          <p style={{ color: "#dc2626", fontSize: 13, marginTop: 8 }}>{classifyError}</p>
        )}
        {classifyResult && (
          <pre style={{
            marginTop: 12, background: "#f9fafb", border: "1px solid #e5e7eb",
            borderRadius: 6, padding: 14, fontSize: 13, overflowX: "auto",
          }}>
            {JSON.stringify(classifyResult, null, 2)}
          </pre>
        )}
      </Section>

      {/* ── Notifications ───────────────────────────────────────── */}
      <Section title="Notifications">
        <ActionButton label="Send Test Email Notification" onClick={handleNotification} loading={notifLoading} />
        <p style={{ fontSize: 12, color: "#6b7280", margin: "4px 0 0" }}>
          Sends a test alert email to your account address via SendGrid.
        </p>
        <Feedback status={notifStatus} />
      </Section>
    </div>
  );
}
