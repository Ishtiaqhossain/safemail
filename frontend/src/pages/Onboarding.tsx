import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { childrenApi } from "@/api/children";
import { onboardingApi } from "@/api/onboarding";
import { setOnboardingCompleted } from "@/api/client";
import { track } from "@/analytics";

const STEP_LABELS = ["Welcome", "How it works", "Consent", "Add child", "Connect email", "Done"];
export const LS_KEY = "sm_onboarding";

const DETECTION = [
  ["🆘", "Self-harm"],
  ["🧑‍🤝‍🧑", "Grooming"],
  ["💬", "Bullying"],
  ["🍺", "Drugs / Alcohol"],
  ["👤", "Stranger contact"],
  ["🔑", "Personal info sharing"],
];

export default function Onboarding() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [step, setStep] = useState(0);
  const [childId, setChildId] = useState<string | null>(null);
  const [childName, setChildName] = useState("");
  const [birthYear, setBirthYear] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connectProvider, setConnectProvider] = useState<"google" | "apple" | "microsoft">("google");
  const [appleEmail, setAppleEmail] = useState("");
  const [applePassword, setApplePassword] = useState("");

  // Resume after the Gmail OAuth round-trip, or from a refresh mid-wizard.
  useEffect(() => {
    if (params.get("connected") === "true") {
      setStep(5);
      params.delete("connected");
      setParams(params, { replace: true });
      return;
    }
    try {
      const saved = JSON.parse(localStorage.getItem(LS_KEY) || "{}");
      if (typeof saved.step === "number") setStep(saved.step);
      if (saved.childId) setChildId(saved.childId);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    localStorage.setItem(LS_KEY, JSON.stringify({ step, childId }));
  }, [step, childId]);

  // Track which wizard step the user is on — reveals where they drop off.
  useEffect(() => {
    track("onboarding_step_viewed", { step, label: STEP_LABELS[step] });
  }, [step]);

  const finishLater = async () => {
    track("gmail_connect_skipped", { step });
    setBusy(true);
    try { await onboardingApi.complete(); } catch { /* non-blocking */ }
    setOnboardingCompleted(true);
    localStorage.removeItem(LS_KEY);
    navigate("/dashboard");
  };

  const recordConsentAndNext = async () => {
    setBusy(true); setError(null);
    try {
      await onboardingApi.consent();
      setStep(3);
    } catch {
      setError("Couldn't save your consent. Please try again.");
    } finally { setBusy(false); }
  };

  const createChildAndNext = async () => {
    if (!childName.trim()) { setError("Please enter your child's name."); return; }
    setBusy(true); setError(null);
    try {
      const child = await childrenApi.create(childName.trim(), birthYear ? Number(birthYear) : undefined);
      setChildId(child.id);
      setStep(4);
    } catch {
      setError("Couldn't add your child. Please try again.");
    } finally { setBusy(false); }
  };

  const connectGmail = async () => {
    if (!childId) { setStep(3); return; }
    track("gmail_connect_initiated", {});
    setBusy(true); setError(null);
    try {
      await childrenApi.connectGmail(childId, "/onboarding?connected=true");
      // redirect happens; component unmounts
    } catch {
      setError("Couldn't start the Gmail connection. Please try again.");
      setBusy(false);
    }
  };

  const connectMicrosoft = async () => {
    if (!childId) { setStep(3); return; }
    track("gmail_connect_initiated", { provider: "microsoft" });
    setBusy(true); setError(null);
    try {
      await childrenApi.connectMicrosoft(childId, "/onboarding?connected=true");
      // redirect happens; component unmounts
    } catch {
      setError("Couldn't start the Microsoft connection. Please try again.");
      setBusy(false);
    }
  };

  const connectApple = async () => {
    if (!childId) { setStep(3); return; }
    if (!appleEmail.trim() || !applePassword.trim()) {
      setError("Enter the iCloud email and the app-specific password.");
      return;
    }
    track("gmail_connect_initiated", { provider: "apple" });
    setBusy(true); setError(null);
    try {
      await childrenApi.connectAppleMail(childId, appleEmail.trim(), applePassword.trim());
      setStep(5);
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || "Couldn't connect that account. Check the email and app-specific password.");
      setBusy(false);
    }
  };

  const finish = async () => {
    setBusy(true);
    try { await onboardingApi.complete(); } catch { /* non-blocking */ }
    setOnboardingCompleted(true);
    localStorage.removeItem(LS_KEY);
    navigate("/dashboard");
  };

  return (
    <div style={{ minHeight: "100vh", background: "#f8fafc", padding: "32px 20px" }}>
      <div style={{ maxWidth: 560, margin: "0 auto" }}>
        {/* Brand + progress */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "center", marginBottom: 18 }}>
          <span style={{ fontSize: 22 }}>🛡️</span>
          <span style={{ fontSize: 18, fontWeight: 700, color: "#0f172a" }}>SafeMail</span>
        </div>
        <Progress step={step} />

        <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 14, padding: "30px 32px", marginTop: 18, boxShadow: "0 4px 16px rgba(0,0,0,0.05)" }}>
          {error && (
            <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 7, padding: "9px 12px", color: "#dc2626", fontSize: 13, marginBottom: 16 }}>
              {error}
            </div>
          )}

          {step === 0 && (
            <Step title="Welcome to SafeMail 👋"
                  body="We watch your child's email for genuinely dangerous content and alert you only when something needs your attention — no noise, no daily digests of nothing.">
              <p style={{ fontSize: 14, color: "#475569", lineHeight: 1.6 }}>
                This quick setup takes about 2 minutes: you'll add your child and connect their email account (Gmail or Apple Mail). Let's go.
              </p>
              <PrimaryBtn onClick={() => setStep(1)}>Get started</PrimaryBtn>
            </Step>
          )}

          {step === 1 && (
            <Step title="How it works"
                  body="Every few minutes we scan new email with AI and flag only what looks unsafe.">
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, margin: "8px 0 20px", fontSize: 13, color: "#475569", fontWeight: 500 }}>
                <span>📥 New email</span><span style={{ color: "#cbd5e1" }}>→</span>
                <span>🤖 AI scan</span><span style={{ color: "#cbd5e1" }}>→</span>
                <span>🔔 Alert (only if unsafe)</span>
              </div>
              <div style={{ background: "#f0f9ff", border: "1px solid #bae6fd", borderRadius: 9, padding: "12px 14px", marginBottom: 18 }}>
                <p style={{ fontSize: 13, fontWeight: 600, color: "#0369a1", margin: "0 0 4px" }}>🔒 Your child's privacy comes first</p>
                <p style={{ fontSize: 13, color: "#0c4a6e", margin: 0, lineHeight: 1.55 }}>
                  We never store the actual email. Only a short AI summary, the category, and severity are kept — the email body lives in memory just long enough to be analyzed, then it's gone.
                </p>
              </div>
              <p style={{ fontSize: 13, fontWeight: 600, color: "#334155", margin: "0 0 8px" }}>We watch for:</p>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 20 }}>
                {DETECTION.map(([icon, label]) => (
                  <div key={label} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#475569" }}>
                    <span>{icon}</span>{label}
                  </div>
                ))}
              </div>
              <NavRow onBack={() => setStep(0)} onNext={() => setStep(2)} />
            </Step>
          )}

          {step === 2 && (
            <Step title="Before you begin"
                  body="SafeMail is most effective — and most respectful — when your child knows about it.">
              <p style={{ fontSize: 14, color: "#475569", lineHeight: 1.6, marginBottom: 16 }}>
                We strongly encourage an open conversation with your child about why you're using SafeMail.
                Monitoring works best as a safety net you've talked about together, not a secret.
              </p>
              <label style={{ display: "flex", gap: 10, alignItems: "flex-start", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 9, padding: "12px 14px", cursor: "pointer" }}>
                <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} style={{ marginTop: 3 }} />
                <span style={{ fontSize: 13, color: "#334155", lineHeight: 1.5 }}>
                  I confirm I'm the parent or legal guardian of this child and have the right to monitor this account.
                </span>
              </label>
              <NavRow onBack={() => setStep(1)} onNext={recordConsentAndNext} nextLabel={busy ? "Saving…" : "I agree"} nextDisabled={!consent || busy} />
            </Step>
          )}

          {step === 3 && (
            <Step title="Add your child"
                  body="Who are we helping you keep safe?">
              <label style={lbl}>Child's name or nickname</label>
              <input value={childName} onChange={(e) => setChildName(e.target.value)} placeholder="e.g. Alex" style={{ width: "100%", marginBottom: 14 }} />
              <label style={lbl}>Birth year (optional)</label>
              <input value={birthYear} onChange={(e) => setBirthYear(e.target.value.replace(/[^0-9]/g, "").slice(0, 4))}
                     placeholder="e.g. 2012" inputMode="numeric" style={{ width: "100%" }} />
              <NavRow onBack={() => setStep(2)} onNext={createChildAndNext} nextLabel={busy ? "Adding…" : "Continue"} nextDisabled={busy} />
            </Step>
          )}

          {step === 4 && (
            <Step title="Connect their email"
                  body="The last step — link the email account you want us to keep an eye on.">
              <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
                {(["google", "apple", "microsoft"] as const).map((p) => (
                  <button
                    key={p}
                    onClick={() => { setConnectProvider(p); setError(null); }}
                    style={{
                      flex: 1, padding: "10px 8px", borderRadius: 8, fontSize: 13, fontWeight: 600,
                      cursor: "pointer",
                      border: connectProvider === p ? "2px solid #2563eb" : "1px solid #e2e8f0",
                      background: connectProvider === p ? "#eff6ff" : "#fff",
                      color: connectProvider === p ? "#1d4ed8" : "#475569",
                    }}
                  >
                    {p === "google" ? "Gmail" : p === "apple" ? "Apple Mail" : "Outlook"}
                  </button>
                ))}
              </div>

              {connectProvider === "google" && (
                <>
                  <div style={{ background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 9, padding: "12px 14px", marginBottom: 16 }}>
                    <p style={{ fontSize: 13, fontWeight: 600, color: "#92400e", margin: "0 0 6px" }}>What you'll see on Google's screen</p>
                    <p style={{ fontSize: 13, color: "#78350f", margin: 0, lineHeight: 1.55 }}>
                      Google will ask to let SafeMail "read your email." That's expected — it's <strong>read-only</strong>,
                      we never send or delete anything, we never store the email itself, and you can disconnect anytime from Settings.
                    </p>
                  </div>
                  <PrimaryBtn onClick={connectGmail} disabled={busy}>{busy ? "Opening Google…" : "Connect Gmail"}</PrimaryBtn>
                </>
              )}

              {connectProvider === "apple" && (
                <>
                  <div style={{ background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 9, padding: "12px 14px", marginBottom: 16 }}>
                    <p style={{ fontSize: 13, fontWeight: 600, color: "#92400e", margin: "0 0 6px" }}>You'll need an app-specific password</p>
                    <p style={{ fontSize: 13, color: "#78350f", margin: 0, lineHeight: 1.55 }}>
                      iCloud needs an <strong>app-specific password</strong> (not the Apple ID password). Create one at{" "}
                      <a href="https://appleid.apple.com" target="_blank" rel="noreferrer" style={{ color: "#92400e", fontWeight: 600 }}>appleid.apple.com</a>{" "}
                      → Sign-In and Security → App-Specific Passwords. It's read-only and you can disconnect anytime.
                    </p>
                  </div>
                  <label style={lbl}>iCloud email</label>
                  <input value={appleEmail} onChange={(e) => setAppleEmail(e.target.value)}
                         placeholder="name@icloud.com" inputMode="email" style={{ width: "100%", marginBottom: 12 }} />
                  <label style={lbl}>App-specific password</label>
                  <input type="password" value={applePassword} onChange={(e) => setApplePassword(e.target.value)}
                         placeholder="xxxx-xxxx-xxxx-xxxx" style={{ width: "100%", marginBottom: 14 }} />
                  <PrimaryBtn onClick={connectApple} disabled={busy}>{busy ? "Connecting…" : "Connect Apple Mail"}</PrimaryBtn>
                </>
              )}

              {connectProvider === "microsoft" && (
                <>
                  <div style={{ background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 9, padding: "12px 14px", marginBottom: 16 }}>
                    <p style={{ fontSize: 13, fontWeight: 600, color: "#92400e", margin: "0 0 6px" }}>What you'll see on Microsoft's screen</p>
                    <p style={{ fontSize: 13, color: "#78350f", margin: 0, lineHeight: 1.55 }}>
                      Microsoft will ask to let SafeMail read mail. That's expected — it's <strong>read-only</strong>,
                      we never send or delete anything, we never store the email itself, and you can disconnect anytime from Settings.
                    </p>
                  </div>
                  <PrimaryBtn onClick={connectMicrosoft} disabled={busy}>{busy ? "Opening Microsoft…" : "Connect Outlook / Microsoft 365"}</PrimaryBtn>
                </>
              )}

              {error && <p style={{ color: "#dc2626", fontSize: 13, margin: "10px 0 0" }}>{error}</p>}
              <button onClick={() => setStep(5)} style={textBtn}>I'll connect it later</button>
              <BackLink onClick={() => setStep(3)} />
            </Step>
          )}

          {step === 5 && (
            <Step title="You're all set 🎉"
                  body="SafeMail is now watching over your child's email.">
              <ul style={{ fontSize: 14, color: "#475569", lineHeight: 1.7, paddingLeft: 18, margin: "0 0 20px" }}>
                <li>We scan for new email roughly every 5 minutes.</li>
                <li>You'll only get an alert when something genuinely needs your attention.</li>
                <li>All alerts appear on your dashboard and in the Alerts tab.</li>
              </ul>
              <PrimaryBtn onClick={finish} disabled={busy}>{busy ? "Finishing…" : "Go to dashboard"}</PrimaryBtn>
            </Step>
          )}
        </div>

        {step < 5 && (
          <div style={{ textAlign: "center", marginTop: 16 }}>
            <button onClick={finishLater} disabled={busy} style={{ background: "none", border: "none", color: "#94a3b8", fontSize: 13, cursor: "pointer" }}>
              Skip setup for now
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function Progress({ step }: { step: number }) {
  return (
    <div style={{ display: "flex", gap: 6, justifyContent: "center" }}>
      {STEP_LABELS.map((label, i) => (
        <div key={label} title={label} style={{
          height: 5, width: 34, borderRadius: 99,
          background: i <= step ? "#2563eb" : "#e2e8f0", transition: "background 0.2s",
        }} />
      ))}
    </div>
  );
}

function Step({ title, body, children }: { title: string; body: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 style={{ fontSize: 20, fontWeight: 700, color: "#0f172a", margin: "0 0 6px" }}>{title}</h2>
      <p style={{ fontSize: 14, color: "#64748b", margin: "0 0 20px", lineHeight: 1.5 }}>{body}</p>
      {children}
    </div>
  );
}

function PrimaryBtn({ children, onClick, disabled }: { children: React.ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      width: "100%", padding: "11px 0", background: disabled ? "#93c5fd" : "#2563eb", color: "#fff",
      border: "none", borderRadius: 9, fontWeight: 600, fontSize: 14.5, cursor: disabled ? "not-allowed" : "pointer",
    }}>{children}</button>
  );
}

function NavRow({ onBack, onNext, nextLabel = "Continue", nextDisabled }: { onBack: () => void; onNext: () => void; nextLabel?: string; nextDisabled?: boolean }) {
  return (
    <div style={{ display: "flex", gap: 10, marginTop: 22 }}>
      <button onClick={onBack} style={{ padding: "10px 18px", background: "#fff", border: "1px solid #e2e8f0", color: "#475569", borderRadius: 9, fontSize: 14, cursor: "pointer" }}>Back</button>
      <button onClick={onNext} disabled={nextDisabled} style={{
        flex: 1, padding: "10px 0", background: nextDisabled ? "#93c5fd" : "#2563eb", color: "#fff",
        border: "none", borderRadius: 9, fontWeight: 600, fontSize: 14, cursor: nextDisabled ? "not-allowed" : "pointer",
      }}>{nextLabel}</button>
    </div>
  );
}

function BackLink({ onClick }: { onClick: () => void }) {
  return <button onClick={onClick} style={{ ...textBtn, color: "#64748b" }}>Back</button>;
}

const lbl: React.CSSProperties = { display: "block", fontSize: 13, fontWeight: 500, marginBottom: 5, color: "#374151" };
const textBtn: React.CSSProperties = {
  display: "block", width: "100%", marginTop: 10, padding: "8px 0",
  background: "none", border: "none", color: "#2563eb", fontSize: 13.5, cursor: "pointer",
};
