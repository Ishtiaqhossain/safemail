import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { NavBar } from "@/components/NavBar";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import AlertFeed from "@/pages/AlertFeed";
import AlertDetail from "@/pages/AlertDetail";
import Settings from "@/pages/Settings";
import { isAuthenticated, tryRefresh } from "@/api/client";

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

export default function App() {
  const [authStatus, setAuthStatus] = useState<AuthStatus>(
    isAuthenticated() ? "authenticated" : "loading"
  );

  useEffect(() => {
    if (authStatus === "loading") {
      tryRefresh().then((ok) => setAuthStatus(ok ? "authenticated" : "unauthenticated"));
    }
  }, []);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login onLogin={() => setAuthStatus("authenticated")} />} />
        <Route path="/dashboard" element={<ProtectedRoute authStatus={authStatus}><Dashboard /></ProtectedRoute>} />
        <Route path="/alerts" element={<ProtectedRoute authStatus={authStatus}><AlertFeed /></ProtectedRoute>} />
        <Route path="/alerts/:id" element={<ProtectedRoute authStatus={authStatus}><AlertDetail /></ProtectedRoute>} />
        <Route path="/settings" element={<ProtectedRoute authStatus={authStatus}><Settings /></ProtectedRoute>} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
