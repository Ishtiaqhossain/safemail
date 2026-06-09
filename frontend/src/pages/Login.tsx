import { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { setAccessToken } from "@/api/client";

export default function Login() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const endpoint = mode === "login" ? "/v1/auth/login" : "/v1/auth/register";
      const body = mode === "login" ? { email, password } : { email, password, full_name: fullName };
      const { data } = await axios.post(endpoint, body, { withCredentials: true });
      setAccessToken(data.access_token);
      navigate("/dashboard");
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Something went wrong";
      setError(msg);
    }
  };

  return (
    <div style={{ maxWidth: 400, margin: "80px auto", padding: 24, border: "1px solid #e5e7eb", borderRadius: 8 }}>
      <h1 style={{ marginBottom: 24 }}>SafeMail</h1>
      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        <button onClick={() => setMode("login")} style={{ fontWeight: mode === "login" ? 700 : 400 }}>Login</button>
        <button onClick={() => setMode("register")} style={{ fontWeight: mode === "register" ? 700 : 400 }}>Register</button>
      </div>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {mode === "register" && (
          <input placeholder="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
        )}
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        {error && <p style={{ color: "red", fontSize: 14 }}>{error}</p>}
        <button type="submit" style={{ padding: "8px 16px", background: "#2563eb", color: "#fff", border: "none", borderRadius: 4, cursor: "pointer" }}>
          {mode === "login" ? "Login" : "Create Account"}
        </button>
      </form>
    </div>
  );
}
