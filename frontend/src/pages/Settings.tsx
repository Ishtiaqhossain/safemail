import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { childrenApi } from "@/api/children";
import { alertsApi } from "@/api/alerts";
import { authApi } from "@/api/auth";
import { clearAccessToken } from "@/api/client";
import { LS_KEY } from "@/pages/Onboarding";
import type { Child, AlertPreference, Severity, Category } from "@/types";

const SEVERITIES: { value: Severity; label: string; color: string; bg: string }[] = [
  { value: "critical", label: "Critical", color: "#dc2626", bg: "#fef2f2" },
  { value: "high",     label: "High",     color: "#ea580c", bg: "#fff7ed" },
  { value: "medium",   label: "Medium",   color: "#d97706", bg: "#fffbeb" },
  { value: "low",      label: "Low",      color: "#16a34a", bg: "#f0fdf4" },
];

const CATEGORIES: { value: Category; label: string; icon: string }[] = [
  { value: "self_harm",             label: "Self-Harm",          icon: "🆘" },
  { value: "grooming",              label: "Grooming",           icon: "⚠️" },
  { value: "bullying",              label: "Bullying",           icon: "😔" },
  { value: "drugs_alcohol",         label: "Drugs & Alcohol",    icon: "🚫" },
  { value: "stranger_contact",      label: "Stranger Contact",   icon: "👤" },
  { value: "personal_info_sharing", label: "Personal Info",      icon: "🔒" },
];

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.07em", textTransform: "uppercase", color: "#94a3b8", margin: "0 0 10px" }}>
      {children}
    </p>
  );
}

function ConnStatus({ status }: { status: "active" | "revoked" | "error" }) {
  const map = {
    active:  { color: "#16a34a", bg: "#f0fdf4", dot: "#16a34a" },
    revoked: { color: "#64748b", bg: "#f1f5f9", dot: "#94a3b8" },
    error:   { color: "#dc2626", bg: "#fef2f2", dot: "#dc2626" },
  };
  const s = map[status];
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 600, color: s.color, background: s.bg, padding: "2px 8px", borderRadius: 99 }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: s.dot, display: "inline-block" }} />
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

function AppleConnectForm({ childId, onDone }: { childId: string; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        style={{ padding: "8px 16px", background: "#f8fafc", color: "#334155", border: "1px solid #e2e8f0", borderRadius: 7, fontSize: 13, fontWeight: 500 }}
      >
        + Connect Apple Mail (iCloud)
      </button>
    );
  }

  const submit = async () => {
    if (!email.trim() || !pw.trim()) { setErr("Enter the iCloud email and app-specific password."); return; }
    setBusy(true); setErr(null);
    try {
      await childrenApi.connectAppleMail(childId, email.trim(), pw.trim());
      setOpen(false); setEmail(""); setPw("");
      onDone();
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setErr(detail || "Couldn't connect that account.");
      setBusy(false);
    }
  };

  return (
    <div style={{ width: "100%", background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: 12 }}>
      <p style={{ fontSize: 12.5, color: "#64748b", margin: "0 0 8px", lineHeight: 1.5 }}>
        Enter the child's <strong>iCloud mailbox</strong> — an <strong>@icloud.com</strong> (or
        @me.com / @mac.com) address. iCloud needs an{" "}
        <strong>app-specific password</strong> (not the Apple ID password) — create one at{" "}
        <a href="https://appleid.apple.com" target="_blank" rel="noreferrer">appleid.apple.com</a>. It's read-only.
      </p>
      <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="child@icloud.com" inputMode="email"
             style={{ width: "100%", marginBottom: 8 }} />
      <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="app-specific password"
             style={{ width: "100%", marginBottom: 8 }} />
      {err && <p style={{ color: "#dc2626", fontSize: 12, margin: "0 0 8px" }}>{err}</p>}
      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={submit} disabled={busy}
                style={{ padding: "7px 14px", background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, fontSize: 13, fontWeight: 600 }}>
          {busy ? "Connecting…" : "Connect"}
        </button>
        <button onClick={() => { setOpen(false); setErr(null); }}
                style={{ padding: "7px 14px", background: "none", color: "#64748b", border: "1px solid #e2e8f0", borderRadius: 6, fontSize: 13 }}>
          Cancel
        </button>
      </div>
    </div>
  );
}

export default function Settings() {
  const [children, setChildren] = useState<Child[]>([]);
  const [newName, setNewName] = useState("");
  const [newYear, setNewYear] = useState("");
  const [addError, setAddError] = useState("");
  const [addLoading, setAddLoading] = useState(false);
  const [prefs, setPrefs] = useState<Record<string, AlertPreference>>({});
  const [savedPrefId, setSavedPrefId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const navigate = useNavigate();

  const load = () => childrenApi.list().then(setChildren);

  useEffect(() => { load(); }, []);

  useEffect(() => {
    children.forEach((child) => {
      alertsApi.getPreferences(child.id).then((p) => {
        setPrefs((prev) => ({ ...prev, [child.id]: p }));
      });
    });
  }, [children]);

  const addChild = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setAddError("");
    setAddLoading(true);
    try {
      await childrenApi.create(newName.trim(), newYear ? parseInt(newYear) : undefined);
      setNewName("");
      setNewYear("");
      load();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to add child";
      setAddError(msg);
    } finally {
      setAddLoading(false);
    }
  };

  const deleteChild = async (id: string) => {
    if (!confirm("Delete this child and all their data?")) return;
    await childrenApi.delete(id);
    load();
  };

  const deleteAccount = async () => {
    const confirmed = window.prompt(
      "This permanently deletes your account and ALL data — every child, " +
      "email connection, and alert. This cannot be undone.\n\n" +
      'Type DELETE to confirm.'
    );
    if (confirmed !== "DELETE") return;
    setDeleting(true);
    try {
      await authApi.deleteAccount();
      clearAccessToken();
      navigate("/login");
    } catch {
      setDeleting(false);
      alert("Something went wrong deleting your account. Please try again.");
    }
  };

  const viewSetupGuide = () => {
    localStorage.removeItem(LS_KEY); // start the wizard fresh at step 1
    navigate("/onboarding");
  };

  const savePref = async (childId: string, pref: AlertPreference) => {
    await alertsApi.updatePreferences(childId, pref);
    setPrefs((prev) => ({ ...prev, [childId]: pref }));
    setSavedPrefId(childId);
    setTimeout(() => setSavedPrefId((id) => (id === childId ? null : id)), 2000);
  };

  return (
    <div style={{ padding: "28px 24px", maxWidth: 720, margin: "0 auto" }}>

      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ marginBottom: 4 }}>Settings</h1>
        <p style={{ color: "#64748b", fontSize: 14 }}>Manage your children and notification preferences.</p>
      </div>

      {/* Add child */}
      <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, padding: "22px 24px", marginBottom: 28, boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }}>
        <h2 style={{ marginBottom: 16, fontSize: 15 }}>Add a child</h2>
        <form onSubmit={addChild}>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: addError ? 12 : 0 }}>
            <div style={{ flex: "1 1 180px" }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 5 }}>
                Name <span style={{ color: "#dc2626" }}>*</span>
              </label>
              <input
                data-testid="settings-child-name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Emma"
                required
                style={{ width: "100%" }}
              />
            </div>
            <div style={{ flex: "0 0 120px" }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 5 }}>
                Birth year
              </label>
              <input
                value={newYear}
                onChange={(e) => setNewYear(e.target.value)}
                placeholder="2014"
              />
            </div>
            <div style={{ display: "flex", alignItems: "flex-end" }}>
              <button
                type="submit"
                disabled={addLoading}
                data-testid="settings-add-child"
                style={{ padding: "8px 20px", background: "#2563eb", color: "#fff", borderRadius: 7, fontWeight: 600 }}
              >
                {addLoading ? "Adding…" : "Add child"}
              </button>
            </div>
          </div>
          {addError && (
            <p style={{ color: "#dc2626", fontSize: 13, background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 6, padding: "7px 12px" }}>
              {addError}
            </p>
          )}
        </form>
      </div>

      {/* Children list */}
      {children.length === 0 ? (
        <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, padding: "36px 24px", textAlign: "center" }}>
          <p style={{ color: "#94a3b8", fontSize: 14 }}>No children added yet. Use the form above to get started.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {children.map((child) => {
            const pref = prefs[child.id];
            return (
              <div key={child.id} style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, overflow: "hidden", boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }}>

                {/* Child header */}
                <div style={{ padding: "16px 20px 14px", borderBottom: "1px solid #f1f5f9", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <div style={{ width: 36, height: 36, borderRadius: "50%", background: "#eff6ff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18 }}>
                      🧒
                    </div>
                    <div>
                      <p style={{ fontWeight: 600, fontSize: 15, color: "#0f172a" }}>{child.display_name}</p>
                      {child.birth_year && (
                        <p style={{ fontSize: 12, color: "#94a3b8" }}>Born {child.birth_year}</p>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => deleteChild(child.id)}
                    style={{ color: "#dc2626", background: "#fef2f2", border: "1px solid #fecaca", fontSize: 12, fontWeight: 500, padding: "4px 12px", borderRadius: 6 }}
                  >
                    Remove
                  </button>
                </div>

                {/* Email accounts */}
                <div style={{ padding: "14px 20px", borderBottom: "1px solid #f1f5f9" }}>
                  <SectionLabel>Email accounts</SectionLabel>
                  {child.gmail_connections.length > 0 && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
                      {child.gmail_connections.map((conn) => (
                        <div key={conn.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "#f8fafc", borderRadius: 7, padding: "9px 12px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <ConnStatus status={conn.status} />
                            <span style={{ fontSize: 13, color: "#374151" }}>{conn.gmail_address}</span>
                            <span style={{ fontSize: 11, color: "#94a3b8" }}>{conn.provider === "apple" ? "Apple Mail" : conn.provider === "microsoft" ? "Outlook" : "Gmail"}</span>
                          </div>
                          <button
                            onClick={() => childrenApi.disconnectGmail(conn.id).then(load)}
                            style={{ fontSize: 12, color: "#64748b", background: "none", border: "1px solid #e2e8f0", padding: "3px 10px", borderRadius: 5 }}
                          >
                            Disconnect
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    <button
                      onClick={() => childrenApi.connectGmail(child.id)}
                      style={{ padding: "8px 16px", background: "#eff6ff", color: "#2563eb", border: "1px solid #bfdbfe", borderRadius: 7, fontSize: 13, fontWeight: 500 }}
                    >
                      + Connect Gmail
                    </button>
                    <button
                      onClick={() => childrenApi.connectMicrosoft(child.id)}
                      style={{ padding: "8px 16px", background: "#eff6ff", color: "#2563eb", border: "1px solid #bfdbfe", borderRadius: 7, fontSize: 13, fontWeight: 500 }}
                    >
                      + Connect Outlook / Microsoft 365
                    </button>
                    <AppleConnectForm childId={child.id} onDone={load} />
                  </div>
                </div>

                {/* Preferences */}
                {pref && (
                  <div style={{ padding: "16px 20px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                      <SectionLabel>Alert preferences</SectionLabel>
                      {savedPrefId === child.id && (
                        <span data-testid="prefs-saved" style={{ fontSize: 12, color: "#16a34a", fontWeight: 500 }}>✓ Saved</span>
                      )}
                    </div>

                    {/* Immediate severities */}
                    <div style={{ marginBottom: 18 }}>
                      <p style={{ fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 3 }}>
                        Immediate alerts
                      </p>
                      <p style={{ fontSize: 12, color: "#94a3b8", marginBottom: 10 }}>
                        Send me an email right away when an alert is this severity.
                      </p>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        {SEVERITIES.map(({ value, label, color, bg }) => {
                          const checked = pref.immediate_severities.includes(value);
                          return (
                            <label
                              key={value}
                              style={{
                                display: "flex", alignItems: "center", gap: 6, cursor: "pointer",
                                background: checked ? bg : "#f8fafc",
                                border: `1px solid ${checked ? color + "80" : "#e2e8f0"}`,
                                borderRadius: 6, padding: "5px 12px", fontSize: 13, fontWeight: 500,
                                color: checked ? color : "#64748b", userSelect: "none",
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                style={{ accentColor: color, width: 14, height: 14 }}
                                onChange={() => {
                                  const next = checked
                                    ? pref.immediate_severities.filter((s) => s !== value)
                                    : [...pref.immediate_severities, value];
                                  savePref(child.id, { ...pref, immediate_severities: next });
                                }}
                              />
                              {label}
                            </label>
                          );
                        })}
                      </div>
                    </div>

                    {/* Categories to monitor */}
                    <div style={{ marginBottom: 18 }}>
                      <p style={{ fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 3 }}>
                        Categories to monitor
                      </p>
                      <p style={{ fontSize: 12, color: "#94a3b8", marginBottom: 10 }}>
                        Uncheck a category to stop receiving alerts for it.
                      </p>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))", gap: 8 }}>
                        {CATEGORIES.map(({ value, label, icon }) => {
                          const disabled = pref.disabled_categories?.includes(value) ?? false;
                          const checked = !disabled;
                          return (
                            <label
                              key={value}
                              style={{
                                display: "flex", alignItems: "center", gap: 8, cursor: "pointer",
                                background: checked ? "#f8fafc" : "#fafafa",
                                border: `1px solid ${checked ? "#e2e8f0" : "#e2e8f0"}`,
                                borderRadius: 7, padding: "8px 12px", fontSize: 13,
                                color: checked ? "#374151" : "#94a3b8", userSelect: "none",
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                style={{ width: 14, height: 14 }}
                                onChange={() => {
                                  const current = pref.disabled_categories ?? [];
                                  const next = checked
                                    ? [...current, value]
                                    : current.filter((c) => c !== value);
                                  savePref(child.id, { ...pref, disabled_categories: next });
                                }}
                              />
                              <span style={{ fontSize: 15 }}>{icon}</span>
                              <span style={{ fontWeight: 500 }}>{label}</span>
                            </label>
                          );
                        })}
                      </div>
                    </div>

                    {/* Digest frequency */}
                    <div>
                      <p style={{ fontSize: 13, fontWeight: 600, color: "#374151", marginBottom: 8 }}>
                        Email digest
                      </p>
                      <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
                        <span style={{ color: "#64748b" }}>Send me a digest email</span>
                        <select
                          value={pref.digest_frequency}
                          onChange={(e) => savePref(child.id, { ...pref, digest_frequency: e.target.value as "daily" | "weekly" })}
                          style={{ fontSize: 13 }}
                        >
                          <option value="daily">Daily</option>
                          <option value="weekly">Weekly</option>
                        </select>
                      </label>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Setup guide */}
      <div style={{ marginTop: 28, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, padding: "22px 24px", boxShadow: "0 1px 3px rgba(0,0,0,0.05)", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ marginBottom: 4, fontSize: 15 }}>Setup guide</h2>
          <p style={{ color: "#64748b", fontSize: 13, margin: 0, lineHeight: 1.5 }}>
            Walk through the SafeMail setup and privacy overview again.
          </p>
        </div>
        <button
          onClick={viewSetupGuide}
          style={{ padding: "8px 18px", background: "#fff", color: "#2563eb", border: "1px solid #bfdbfe", borderRadius: 7, fontWeight: 600, fontSize: 13, whiteSpace: "nowrap", cursor: "pointer" }}
        >
          View setup guide
        </button>
      </div>

      {/* Danger zone */}
      <div style={{ marginTop: 28, background: "#fff", border: "1px solid #fecaca", borderRadius: 12, padding: "22px 24px", boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }}>
        <h2 style={{ marginBottom: 4, fontSize: 15, color: "#dc2626" }}>Delete account</h2>
        <p style={{ color: "#64748b", fontSize: 13, marginBottom: 16, lineHeight: 1.5 }}>
          Permanently delete your account and all associated data — every child,
          email connection, and alert. We also revoke SafeMail's access to any
          connected email accounts. This cannot be undone.
        </p>
        <button
          onClick={deleteAccount}
          disabled={deleting}
          style={{ padding: "8px 18px", background: "#dc2626", color: "#fff", borderRadius: 7, fontWeight: 600, fontSize: 13, opacity: deleting ? 0.6 : 1 }}
        >
          {deleting ? "Deleting…" : "Delete my account"}
        </button>
      </div>
    </div>
  );
}
