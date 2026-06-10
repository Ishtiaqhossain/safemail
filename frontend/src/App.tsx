import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { NavBar } from "@/components/NavBar";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import AlertFeed from "@/pages/AlertFeed";
import AlertDetail from "@/pages/AlertDetail";
import Settings from "@/pages/Settings";
import { isAuthenticated, tryRefresh, getIsAdmin, getIsDeveloper } from "@/api/client";
import Admin from "@/pages/Admin";
import Developer from "@/pages/Developer";
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";
import VerifyEmail from "@/pages/VerifyEmail";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

function ProtectedRoute({ authStatus, children }: { authStatus: AuthStatus; children: React.ReactNode }) {
  if (authStatus === "loading") return <p style={{ padding: 24 }}>Loading...</p>;
  if (authStatus === "unauthenticated") return <Navigate to="/login" replace />;
  return (
    <>
      <NavBar />
      <main>{children}</main>
    </>
  );
}

function AdminRoute({ authStatus, children }: { authStatus: AuthStatus; children: React.ReactNode }) {
  if (authStatus === "loading") return <p style={{ padding: 24 }}>Loading...</p>;
  if (authStatus === "unauthenticated") return <Navigate to="/login" replace />;
  if (!getIsAdmin()) return <Navigate to="/dashboard" replace />;
  return (
    <>
      <NavBar />
      <main>{children}</main>
    </>
  );
}

function DeveloperRoute({ authStatus, children }: { authStatus: AuthStatus; children: React.ReactNode }) {
  if (authStatus === "loading") return <p style={{ padding: 24 }}>Loading...</p>;
  if (authStatus === "unauthenticated") return <Navigate to="/login" replace />;
  if (!getIsDeveloper()) return <Navigate to="/dashboard" replace />;
  return (
    <>
      <NavBar />
      <main>{children}</main>
    </>
  );
}

export default function App() {
  const [authStatus, setAuthStatus] = useState<AuthStatus>(
    isAuthenticated() ? "authenticated" : "loading"
  );

  useEffect(() => {
    if (authStatus === "loading") {
      tryRefresh().then((ok) => setAuthStatus(ok ? "authenticated" : "unauthenticated"));
    }
  }, []);

  const handleLogin = () => setAuthStatus("authenticated");

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login onLogin={handleLogin} />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
        <Route path="/dashboard" element={<ProtectedRoute authStatus={authStatus}><Dashboard /></ProtectedRoute>} />
        <Route path="/alerts" element={<ProtectedRoute authStatus={authStatus}><AlertFeed /></ProtectedRoute>} />
        <Route path="/alerts/:id" element={<ProtectedRoute authStatus={authStatus}><AlertDetail /></ProtectedRoute>} />
        <Route path="/settings" element={<ProtectedRoute authStatus={authStatus}><Settings /></ProtectedRoute>} />
        <Route path="/admin" element={<AdminRoute authStatus={authStatus}><Admin /></AdminRoute>} />
        <Route path="/developer" element={<DeveloperRoute authStatus={authStatus}><Developer /></DeveloperRoute>} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
