import { useState } from "react";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import axios from "axios";
import { API_BASE } from "@/api/client";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token");

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (!token) {
    return (
      <div style={{
        minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
        background: "#f8fafc", padding: 20,
      }}>
        <div style={{
          background: "#fff", border: "1px solid #e2e8f0", borderRadius: 14,
          padding: "32px 36px", maxWidth: 400, width: "100%", textAlign: "center",
        }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>⚠️</div>
          <h2 style={{ marginBottom: 8 }}>Invalid reset link</h2>
          <p style={{ color: "#64748b", fontSize: 14, marginBottom: 20 }}>
            This reset link is missing or malformed. Please request a new one.
          </p>
          <Link to="/forgot-password" style={{ color: "#2563eb", fontWeight: 500, fontSize: 14 }}>
            Request a new link
          </Link>
        </div>
      </div>
    );
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirm) { setError("Passwords don't match."); return; }
    if (password.length < 8) { setError("Password must be at least 8 characters."); return; }
    setError(""); setLoading(true);
    try {
      await axios.post(`${API_BASE}/v1/auth/reset-password`, { token, new_password: password });
      navigate("/login?reset=true");
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? "Reset failed. The link may have expired.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: "100vh", display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center", background: "#f8fafc", padding: 20,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 28 }}>
        <span style={{ fontSize: 28 }}>🛡️</span>
        <span style={{ fontSize: 22, fontWeight: 700, color: "#0f172a", letterSpacing: "-0.02em" }}>SafeMail</span>
      </div>

      <div style={{
        background: "#fff", border: "1px solid #e2e8f0", borderRadius: 14,
        padding: "32px 36px", width: "100%", maxWidth: 400,
        boxShadow: "0 4px 16px rgba(0,0,0,0.06)",
      }}>
        <h2 style={{ marginBottom: 6 }}>Set a new password</h2>
        <p style={{ color: "#64748b", fontSize: 13, marginBottom: 24 }}>
          Choose a password with at least 8 characters.
        </p>

        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: 5, color: "#374151" }}>
              New password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              style={{ width: "100%" }}
            />
          </div>
          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: 5, color: "#374151" }}>
              Confirm password
            </label>
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="••••••••"
              required
              style={{ width: "100%" }}
            />
          </div>

          {error && (
            <div style={{ background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 7, padding: "9px 12px", color: "#dc2626", fontSize: 13 }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              padding: "10px 0", background: "#2563eb", color: "#fff",
              border: "none", borderRadius: 8, fontWeight: 600, fontSize: 14, marginTop: 4,
            }}
          >
            {loading ? "Saving…" : "Set new password"}
          </button>
        </form>
      </div>
    </div>
  );
}
