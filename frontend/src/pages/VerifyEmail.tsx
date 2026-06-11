import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import axios from "axios";
import { API_BASE } from "@/api/client";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");

  useEffect(() => {
    if (!token) { setStatus("error"); return; }
    axios.get(`${API_BASE}/v1/auth/verify-email?token=${encodeURIComponent(token)}`, { maxRedirects: 0 })
      .then(() => setStatus("success"))
      .catch((err) => {
        // The endpoint redirects to the dashboard on success; axios may follow the redirect.
        // If we land here with a 3xx or the page just loaded, treat as success.
        if (err?.response?.status >= 300 && err?.response?.status < 400) {
          window.location.href = err.response.headers?.location ?? "/dashboard?verified=true";
        } else {
          setStatus("error");
        }
      });
  }, [token]);

  const centered: React.CSSProperties = {
    minHeight: "100vh", display: "flex", flexDirection: "column",
    alignItems: "center", justifyContent: "center", background: "#f8fafc", padding: 20,
  };
  const card: React.CSSProperties = {
    background: "#fff", border: "1px solid #e2e8f0", borderRadius: 14,
    padding: "36px 40px", maxWidth: 400, width: "100%",
    textAlign: "center", boxShadow: "0 4px 16px rgba(0,0,0,0.06)",
  };

  if (status === "loading") {
    return (
      <div style={centered}>
        <div style={card}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>⏳</div>
          <h2>Verifying your email…</h2>
        </div>
      </div>
    );
  }

  if (status === "success") {
    return (
      <div style={centered}>
        <div style={card}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>✅</div>
          <h2 style={{ marginBottom: 8 }}>Email verified!</h2>
          <p style={{ color: "#64748b", fontSize: 14, marginBottom: 24 }}>
            Your email address has been confirmed.
          </p>
          <Link to="/dashboard" style={{ background: "#2563eb", color: "#fff", padding: "9px 24px", borderRadius: 7, fontWeight: 600, fontSize: 14, textDecoration: "none" }}>
            Go to dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div style={centered}>
      <div style={card}>
        <div style={{ fontSize: 36, marginBottom: 12 }}>⚠️</div>
        <h2 style={{ marginBottom: 8 }}>Link expired or invalid</h2>
        <p style={{ color: "#64748b", fontSize: 14, marginBottom: 24 }}>
          This verification link has expired or already been used. Log in and we'll send you a fresh one.
        </p>
        <Link to="/login" style={{ color: "#2563eb", fontSize: 14, fontWeight: 500 }}>
          Go to sign in
        </Link>
      </div>
    </div>
  );
}
