import { useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { API_BASE } from "@/api/client";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post(`${API_BASE}/v1/auth/forgot-password`, { email });
    } finally {
      setLoading(false);
      setSent(true); // always show success — don't reveal whether email exists
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
        {sent ? (
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 36, marginBottom: 16 }}>📬</div>
            <h2 style={{ marginBottom: 8 }}>Check your email</h2>
            <p style={{ color: "#64748b", fontSize: 14, marginBottom: 24 }}>
              If an account exists for <strong>{email}</strong>, we've sent a password reset link. It expires in 30 minutes.
            </p>
            <Link
              to="/login"
              style={{ color: "#2563eb", fontSize: 14, fontWeight: 500 }}
            >
              ← Back to sign in
            </Link>
          </div>
        ) : (
          <>
            <h2 style={{ marginBottom: 6 }}>Reset your password</h2>
            <p style={{ color: "#64748b", fontSize: 13, marginBottom: 24 }}>
              Enter your email and we'll send you a reset link.
            </p>
            <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: 5, color: "#374151" }}>
                  Email
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                  style={{ width: "100%" }}
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                style={{
                  padding: "10px 0", background: "#2563eb", color: "#fff",
                  border: "none", borderRadius: 8, fontWeight: 600, fontSize: 14,
                }}
              >
                {loading ? "Sending…" : "Send reset link"}
              </button>
            </form>
            <p style={{ marginTop: 20, textAlign: "center", fontSize: 13 }}>
              <Link to="/login" style={{ color: "#64748b" }}>← Back to sign in</Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
