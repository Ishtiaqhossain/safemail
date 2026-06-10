import { useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import axios from "axios";
import { setAccessToken, setIsAdmin, setIsDeveloper, setIsEmailVerified } from "@/api/client";

export default function Login({ onLogin }: { onLogin?: () => void }) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const resetSuccess = searchParams.get("reset") === "true";
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const endpoint = mode === "login" ? "/v1/auth/login" : "/v1/auth/register";
      const body = mode === "login" ? { email, password } : { email, password, full_name: fullName };
      const { data } = await axios.post(endpoint, body, { withCredentials: true });
      setAccessToken(data.access_token);
      setIsAdmin(data.is_admin ?? false);
      setIsDeveloper(data.is_developer ?? false);
      setIsEmailVerified(data.is_email_verified ?? true);
      onLogin?.();
      navigate("/dashboard");
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Something went wrong";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      background: "#f8fafc",
      padding: 20,
    }}>
      {/* Brand */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 28 }}>
        <span style={{ fontSize: 28 }}>🛡️</span>
        <span style={{ fontSize: 22, fontWeight: 700, color: "#0f172a", letterSpacing: "-0.02em" }}>SafeMail</span>
      </div>

      {/* Card */}
      <div style={{
        background: "#fff",
        border: "1px solid #e2e8f0",
        borderRadius: 14,
        padding: "32px 36px",
        width: "100%",
        maxWidth: 400,
        boxShadow: "0 4px 16px rgba(0,0,0,0.06)",
      }}>
        {resetSuccess && (
          <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 7, padding: "10px 14px", color: "#16a34a", fontSize: 13, marginBottom: 20 }}>
            Password updated. You can now sign in with your new password.
          </div>
        )}

        <h2 style={{ marginBottom: 4, fontSize: 18 }}>
          {mode === "login" ? "Welcome back" : "Create your account"}
        </h2>
        <p style={{ color: "#64748b", fontSize: 13, marginBottom: 24 }}>
          {mode === "login"
            ? "Sign in to your SafeMail account."
            : "Start protecting your family today."}
        </p>

        {/* Mode toggle */}
        <div style={{
          display: "flex",
          background: "#f1f5f9",
          borderRadius: 8,
          padding: 3,
          marginBottom: 22,
        }}>
          {(["login", "register"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              style={{
                flex: 1,
                padding: "7px 0",
                borderRadius: 6,
                border: "none",
                background: mode === m ? "#fff" : "transparent",
                color: mode === m ? "#0f172a" : "#64748b",
                fontWeight: mode === m ? 600 : 400,
                fontSize: 13,
                boxShadow: mode === m ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
                transition: "all 0.15s",
              }}
            >
              {m === "login" ? "Sign in" : "Register"}
            </button>
          ))}
        </div>

        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {mode === "register" && (
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: 5, color: "#374151" }}>
                Full name
              </label>
              <input
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Jane Smith"
                style={{ width: "100%" }}
              />
            </div>
          )}
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
          <div>
            <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: 5, color: "#374151" }}>
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              style={{ width: "100%" }}
            />
            {mode === "login" && (
              <div style={{ textAlign: "right", marginTop: 4 }}>
                <Link to="/forgot-password" style={{ fontSize: 12, color: "#64748b" }}>
                  Forgot password?
                </Link>
              </div>
            )}
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
              padding: "10px 0",
              background: "#2563eb",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              fontWeight: 600,
              fontSize: 14,
              cursor: loading ? "not-allowed" : "pointer",
              marginTop: 4,
            }}
          >
            {loading ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>
      </div>

      <p style={{ marginTop: 20, fontSize: 12, color: "#94a3b8" }}>
        Email monitoring for families.
      </p>
    </div>
  );
}
