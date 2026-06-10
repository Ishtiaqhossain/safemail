import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { devApi } from "@/api/developer";

type Status = { type: "success" | "error"; message: string } | null;

function Card({ children, style = {} }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 10, padding: "20px 22px", ...style }}>
      {children}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.07em", textTransform: "uppercase", color: "#94a3b8", margin: "0 0 14px" }}>
      {children}
    </p>
  );
}

function Feedback({ status }: { status: Status }) {
  if (!status) return null;
  const ok = status.type === "success";
  return (
    <p style={{
      marginTop: 10, fontSize: 13, display: "inline-block",
      color: ok ? "#16a34a" : "#dc2626",
      background: ok ? "#f0fdf4" : "#fef2f2",
      border: `1px solid ${ok ? "#bbf7d0" : "#fecaca"}`,
      padding: "6px 12px", borderRadius: 6,
    }}>
      {status.message}
    </p>
  );
}

function Btn({
  label, onClick, danger = false, loading = false,
}: { label: string; onClick: () => void; danger?: boolean; loading?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      style={{
        padding: "8px 18px", borderRadius: 7, border: "none", fontWeight: 600, fontSize: 13,
        background: loading ? "#94a3b8" : danger ? "#dc2626" : "#2563eb",
        color: "#fff",
      }}
    >
      {loading ? "Working…" : label}
    </button>
  );
}

export default function Developer() {
  const navigate = useNavigate();
  const [queueDepth, setQueueDepth] = useState<number | null>(null);

  const [injectLoading, setInjectLoading] = useState(false);
  const [injectStatus, setInjectStatus] = useState<Status>(null);
  const [clearLoading,  setClearLoading]  = useState(false);
  const [clearStatus,   setClearStatus]   = useState<Status>(null);
  const [pollLoading,   setPollLoading]   = useState(false);
  const [pollStatus,    setPollStatus]    = useState<Status>(null);
  const [notifLoading,  setNotifLoading]  = useState(false);
  const [notifStatus,   setNotifStatus]   = useState<Status>(null);

  const [emailBody, setEmailBody]         = useState("");
  const [subject, setSubject]             = useState("");
  const [sender, setSender]               = useState("test@example.com");
  const [classifyLoading, setClassifyLoading] = useState(false);
  const [classifyResult, setClassifyResult]   = useState<Record<string, unknown> | null>(null);
  const [classifyError, setClassifyError]     = useState<string | null>(null);

  useEffect(() => {
    devApi.queueDepth().then((d) => setQueueDepth(d.pending)).catch(() => setQueueDepth(null));
  }, []);

  const handleInject = async () => {
    setInjectLoading(true); setInjectStatus(null);
    try {
      const r = await devApi.injectFakeAlerts();
      setInjectStatus({ type: "success", message: `Injected ${r.inserted} alerts for "${r.child_name}"` });
      navigate("/alerts");
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed";
      setInjectStatus({ type: "error", message: msg });
    } finally { setInjectLoading(false); }
  };

  const handleClear = async () => {
    if (!confirm("Delete all fake alerts?")) return;
    setClearLoading(true); setClearStatus(null);
    try {
      const r = await devApi.clearFakeData();
      setClearStatus({ type: "success", message: `Deleted ${r.deleted} fake alerts` });
    } catch { setClearStatus({ type: "error", message: "Failed to clear fake data" }); }
    finally { setClearLoading(false); }
  };

  const handlePoll = async () => {
    setPollLoading(true); setPollStatus(null);
    try {
      await devApi.triggerPoll();
      setPollStatus({ type: "success", message: "Gmail poll queued — check the Celery worker logs" });
      devApi.queueDepth().then((d) => setQueueDepth(d.pending)).catch(() => {});
    } catch { setPollStatus({ type: "error", message: "Failed to queue poll" }); }
    finally { setPollLoading(false); }
  };

  const handleNotification = async () => {
    setNotifLoading(true); setNotifStatus(null);
    try {
      const r = await devApi.testNotification();
      setNotifStatus({ type: "success", message: `Test email sent to ${r.sent_to}` });
    } catch { setNotifStatus({ type: "error", message: "Failed — check SENDGRID_API_KEY" }); }
    finally { setNotifLoading(false); }
  };

  const handleClassify = async () => {
    if (!emailBody.trim()) return;
    setClassifyLoading(true); setClassifyResult(null); setClassifyError(null);
    try {
      const r = await devApi.classify({ email_body: emailBody, subject, sender });
      setClassifyResult(r);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Classification failed";
      setClassifyError(msg);
    } finally { setClassifyLoading(false); }
  };

  return (
    <div style={{ padding: "28px 24px", maxWidth: 820, margin: "0 auto" }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 24 }}>
        <h1>Developer Tools</h1>
        <span style={{ fontSize: 11, fontWeight: 700, background: "#ede9fe", color: "#7c3aed", padding: "3px 10px", borderRadius: 99, letterSpacing: "0.06em" }}>
          DEV
        </span>
      </div>

      {/* Test Data */}
      <Card style={{ marginBottom: 16 }}>
        <SectionTitle>Test Data</SectionTitle>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <div>
            <Btn label="Inject Fake Alerts" onClick={handleInject} loading={injectLoading} />
            <p style={{ fontSize: 12, color: "#94a3b8", margin: "5px 0 0" }}>Inserts 8 realistic alerts covering all categories and severities.</p>
            <Feedback status={injectStatus} />
          </div>
          <div>
            <Btn label="Clear Fake Data" onClick={handleClear} loading={clearLoading} danger />
            <p style={{ fontSize: 12, color: "#94a3b8", margin: "5px 0 0" }}>Deletes all alerts prefixed with "fake_".</p>
            <Feedback status={clearStatus} />
          </div>
        </div>
      </Card>

      {/* Pipeline */}
      <Card style={{ marginBottom: 16 }}>
        <SectionTitle>Pipeline</SectionTitle>
        <div style={{ display: "flex", gap: 24, alignItems: "flex-start", flexWrap: "wrap" }}>
          <div>
            <Btn label="Trigger Gmail Poll Now" onClick={handlePoll} loading={pollLoading} />
            <p style={{ fontSize: 12, color: "#94a3b8", margin: "5px 0 0" }}>Fires poll_all_connections immediately instead of waiting 5 min.</p>
            <Feedback status={pollStatus} />
          </div>
          <div style={{ border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 20px", textAlign: "center", minWidth: 110 }}>
            <p style={{ fontSize: 11, fontWeight: 600, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", margin: "0 0 4px" }}>Queue depth</p>
            <p style={{ fontSize: 28, fontWeight: 700, color: "#0f172a", margin: 0 }}>{queueDepth ?? "—"}</p>
          </div>
        </div>
      </Card>

      {/* Classifier Playground */}
      <Card style={{ marginBottom: 16 }}>
        <SectionTitle>Classifier Playground</SectionTitle>
        <p style={{ fontSize: 13, color: "#64748b", margin: "0 0 14px" }}>
          Paste email content to run it through Claude without creating an alert.
        </p>
        <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: 12, fontWeight: 600, display: "block", color: "#374151", marginBottom: 4 }}>Subject</label>
            <input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Email subject" style={{ width: "100%" }} />
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ fontSize: 12, fontWeight: 600, display: "block", color: "#374151", marginBottom: 4 }}>Sender</label>
            <input value={sender} onChange={(e) => setSender(e.target.value)} placeholder="sender@example.com" style={{ width: "100%" }} />
          </div>
        </div>
        <label style={{ fontSize: 12, fontWeight: 600, display: "block", color: "#374151", marginBottom: 4 }}>Email body</label>
        <textarea
          value={emailBody}
          onChange={(e) => setEmailBody(e.target.value)}
          placeholder="Paste email body here…"
          rows={5}
          style={{ width: "100%", fontFamily: "monospace", fontSize: 12, resize: "vertical" }}
        />
        <div style={{ marginTop: 10 }}>
          <Btn label="Classify" onClick={handleClassify} loading={classifyLoading} />
        </div>
        {classifyError && <p style={{ color: "#dc2626", fontSize: 13, marginTop: 8 }}>{classifyError}</p>}
        {classifyResult && (
          <pre style={{
            marginTop: 12, background: "#f8fafc", border: "1px solid #e2e8f0",
            borderRadius: 7, padding: 14, fontSize: 12, overflowX: "auto", lineHeight: 1.6,
          }}>
            {JSON.stringify(classifyResult, null, 2)}
          </pre>
        )}
      </Card>

      {/* Notifications */}
      <Card>
        <SectionTitle>Notifications</SectionTitle>
        <Btn label="Send Test Email" onClick={handleNotification} loading={notifLoading} />
        <p style={{ fontSize: 12, color: "#94a3b8", margin: "5px 0 0" }}>Sends a test alert email to your account address via SendGrid.</p>
        <Feedback status={notifStatus} />
      </Card>
    </div>
  );
}
