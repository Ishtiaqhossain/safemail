import { Link, useNavigate } from "react-router-dom";
import api, { getIsAdmin, getIsDeveloper } from "@/api/client";

export function NavBar() {
  const navigate = useNavigate();

  const logout = async () => {
    await api.post("/auth/logout");
    navigate("/login");
  };

  return (
    <nav style={{ display: "flex", alignItems: "center", gap: 24, padding: "12px 24px", borderBottom: "1px solid #e5e7eb", background: "#fff" }}>
      <span style={{ fontWeight: 700, fontSize: 18 }}>SafeMail</span>
      <Link to="/dashboard">Dashboard</Link>
      <Link to="/alerts">Alerts</Link>
      <Link to="/settings">Settings</Link>
      {getIsAdmin() && <Link to="/admin">Admin</Link>}
      {getIsDeveloper() && <Link to="/developer" style={{ color: "#7c3aed" }}>Dev</Link>}
      <button onClick={logout} style={{ marginLeft: "auto", cursor: "pointer" }}>
        Logout
      </button>
    </nav>
  );
}
