import { useEffect, useState } from "react";
import { childrenApi } from "@/api/children";
import { alertsApi } from "@/api/alerts";
import type { Child, AlertPreference } from "@/types";

export default function Settings() {
  const [children, setChildren] = useState<Child[]>([]);
  const [newName, setNewName] = useState("");
  const [newYear, setNewYear] = useState("");
  const [addError, setAddError] = useState("");
  const [prefs, setPrefs] = useState<Record<string, AlertPreference>>({});

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
    try {
      await childrenApi.create(newName.trim(), newYear ? parseInt(newYear) : undefined);
      setNewName("");
      setNewYear("");
      load();
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to add child";
      setAddError(msg);
    }
  };

  const deleteChild = async (id: string) => {
    if (!confirm("Delete this child and all their data?")) return;
    await childrenApi.delete(id);
    load();
  };

  const savePref = async (childId: string, pref: AlertPreference) => {
    await alertsApi.updatePreferences(childId, pref);
    setPrefs((prev) => ({ ...prev, [childId]: pref }));
  };

  return (
    <div style={{ padding: 24, maxWidth: 700, margin: "0 auto" }}>
      <h2>Settings</h2>

      <section style={{ marginBottom: 32 }}>
        <h3>Add Child</h3>
        <form onSubmit={addChild} style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
          <div>
            <label style={{ display: "block", fontSize: 13, marginBottom: 4 }}>Name</label>
            <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Emma" required />
          </div>
          <div>
            <label style={{ display: "block", fontSize: 13, marginBottom: 4 }}>Birth year</label>
            <input value={newYear} onChange={(e) => setNewYear(e.target.value)} placeholder="2014" style={{ width: 80 }} />
          </div>
          <button type="submit" style={{ padding: "7px 16px", background: "#2563eb", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}>
            Add
          </button>
        </form>
        {addError && <p style={{ color: "#dc2626", marginTop: 8, fontSize: 14 }}>{addError}</p>}
      </section>

      <section>
        <h3>Children</h3>
        {children.map((child) => {
          const pref = prefs[child.id];
          return (
            <div key={child.id} style={{ border: "1px solid #e5e7eb", borderRadius: 8, padding: 16, marginBottom: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <h4 style={{ margin: 0 }}>{child.display_name}</h4>
                <button onClick={() => deleteChild(child.id)} style={{ color: "#dc2626", background: "none", border: "none", cursor: "pointer", fontSize: 13 }}>
                  Delete
                </button>
              </div>

              <div style={{ marginBottom: 12 }}>
                <p style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Gmail</p>
                {child.gmail_connections.length > 0 ? (
                  child.gmail_connections.map((conn) => (
                    <div key={conn.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 13 }}>
                      <span>{conn.gmail_address} <span style={{ color: conn.status === "active" ? "#16a34a" : "#dc2626" }}>({conn.status})</span></span>
                      <button onClick={() => childrenApi.disconnectGmail(conn.id).then(load)} style={{ fontSize: 12, cursor: "pointer" }}>
                        Disconnect
                      </button>
                    </div>
                  ))
                ) : (
                  <button onClick={() => childrenApi.connectGmail(child.id)} style={{ fontSize: 13, cursor: "pointer", color: "#2563eb", background: "none", border: "none", padding: 0 }}>
                    + Connect Gmail account
                  </button>
                )}
              </div>

              {pref && (
                <div style={{ fontSize: 13 }}>
                  <p style={{ fontWeight: 600, marginBottom: 6 }}>Alert Preferences</p>
                  <label>
                    <span>Digest frequency: </span>
                    <select
                      value={pref.digest_frequency}
                      onChange={(e) => savePref(child.id, { ...pref, digest_frequency: e.target.value as "daily" | "weekly" })}
                    >
                      <option value="daily">Daily</option>
                      <option value="weekly">Weekly</option>
                    </select>
                  </label>
                </div>
              )}
            </div>
          );
        })}
      </section>
    </div>
  );
}
