import { Link, useLocation, useNavigate } from "react-router-dom";
import api, { getIsAdmin, getIsDeveloper, clearAccessToken } from "@/api/client";

const NAV_LINKS = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/alerts",    label: "Alerts" },
  { to: "/settings",  label: "Settings" },
];

export function NavBar() {
  const location = useLocation();
  const navigate = useNavigate();

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch {}
    clearAccessToken();
    navigate("/login");
  };

  const isActive = (path: string) => location.pathname === path || (path !== "/dashboard" && location.pathname.startsWith(path));

  return (
    <nav style={{
      background: "#fff",
      borderBottom: "1px solid #e2e8f0",
      boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
      position: "sticky",
      top: 0,
      zIndex: 50,
    }}>
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "0 24px", display: "flex", alignItems: "center", height: 56 }}>

        {/* Logo */}
        <Link to="/dashboard" style={{ display: "flex", alignItems: "center", gap: 8, marginRight: 32, textDecoration: "none" }}>
          <span style={{ fontSize: 20 }}>🛡️</span>
          <span style={{ fontWeight: 700, fontSize: 16, color: "#0f172a", letterSpacing: "-0.01em" }}>SafeMail</span>
        </Link>

        {/* Primary nav */}
        <div style={{ display: "flex", alignItems: "center", gap: 2, flex: 1 }}>
          {NAV_LINKS.map(({ to, label }) => (
            <Link
              key={to}
              to={to}
              style={{
                padding: "6px 12px",
                borderRadius: 6,
                fontSize: 14,
                fontWeight: isActive(to) ? 600 : 400,
                color: isActive(to) ? "#2563eb" : "#64748b",
                background: isActive(to) ? "#eff6ff" : "transparent",
                textDecoration: "none",
                transition: "background 0.15s, color 0.15s",
              }}
            >
              {label}
            </Link>
          ))}
        </div>

        {/* Role links + logout */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {getIsAdmin() && (
            <Link
              to="/monitoring"
              style={{
                fontSize: 12, fontWeight: 600, padding: "3px 10px", borderRadius: 99,
                background: isActive("/monitoring") ? "#dcfce7" : "#f1f5f9",
                color: isActive("/monitoring") ? "#15803d" : "#64748b",
                textDecoration: "none",
              }}
            >
              Health
            </Link>
          )}
          {getIsAdmin() && (
            <Link
              to="/admin"
              style={{
                fontSize: 12, fontWeight: 600, padding: "3px 10px", borderRadius: 99,
                background: isActive("/admin") ? "#dbeafe" : "#f1f5f9",
                color: isActive("/admin") ? "#1d4ed8" : "#64748b",
                textDecoration: "none",
              }}
            >
              Admin
            </Link>
          )}
          {getIsDeveloper() && (
            <Link
              to="/developer"
              style={{
                fontSize: 12, fontWeight: 600, padding: "3px 10px", borderRadius: 99,
                background: isActive("/developer") ? "#ede9fe" : "#f1f5f9",
                color: isActive("/developer") ? "#7c3aed" : "#64748b",
                textDecoration: "none",
              }}
            >
              Dev
            </Link>
          )}
          <div style={{ width: 1, height: 20, background: "#e2e8f0", margin: "0 4px" }} />
          <button
            onClick={logout}
            data-testid="logout"
            style={{ background: "none", border: "1px solid #e2e8f0", color: "#64748b", padding: "5px 14px", borderRadius: 6, fontSize: 13 }}
          >
            Sign out
          </button>
        </div>
      </div>
    </nav>
  );
}
