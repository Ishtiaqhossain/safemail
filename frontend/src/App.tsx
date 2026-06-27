import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { NavBar } from "@/components/NavBar";
import Login from "@/pages/Login";
import Landing from "@/pages/Landing";
import Dashboard from "@/pages/Dashboard";
import AlertFeed from "@/pages/AlertFeed";
import AlertDetail from "@/pages/AlertDetail";
import Settings from "@/pages/Settings";
import { isAuthenticated, tryRefresh, getIsAdmin, getIsDeveloper, getOnboardingCompleted } from "@/api/client";
import Admin from "@/pages/Admin";
import Developer from "@/pages/Developer";
import Monitoring from "@/pages/Monitoring";
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";
import VerifyEmail from "@/pages/VerifyEmail";
import Onboarding from "@/pages/Onboarding";
import { PrivacyPage, TermsPage } from "@/pages/Legal";

type AuthStatus = "loading" | "authenticated" | "unauthenticated";

function ProtectedRoute({ authStatus, children }: { authStatus: AuthStatus; children: React.ReactNode }) {
  if (authStatus === "loading") return <p style={{ padding: 24 }}>Loading...</p>;
  if (authStatus === "unauthenticated") return <Navigate to="/login" replace />;
  if (!getOnboardingCompleted()) return <Navigate to="/onboarding" replace />;
  return (
    <>
      <NavBar />
      <main>{children}</main>
    </>
  );
}

// Public marketing pages: logged-in users are sent to the dashboard; everyone
// else sees the page (no NavBar — the landing page has its own nav).
function PublicRoute({ authStatus, children }: { authStatus: AuthStatus; children: React.ReactNode }) {
  if (authStatus === "loading") return <p style={{ padding: 24 }}>Loading...</p>;
  if (authStatus === "authenticated") return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}

function OnboardingRoute({ authStatus, children }: { authStatus: AuthStatus; children: React.ReactNode }) {
  if (authStatus === "loading") return <p style={{ padding: 24 }}>Loading...</p>;
  if (authStatus === "unauthenticated") return <Navigate to="/login" replace />;
  return <main>{children}</main>;
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
        <Route path="/" element={<PublicRoute authStatus={authStatus}><Landing /></PublicRoute>} />
        <Route path="/login" element={<Login onLogin={handleLogin} />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/onboarding" element={<OnboardingRoute authStatus={authStatus}><Onboarding /></OnboardingRoute>} />
        <Route path="/dashboard" element={<ProtectedRoute authStatus={authStatus}><Dashboard /></ProtectedRoute>} />
        <Route path="/alerts" element={<ProtectedRoute authStatus={authStatus}><AlertFeed /></ProtectedRoute>} />
        <Route path="/alerts/:id" element={<ProtectedRoute authStatus={authStatus}><AlertDetail /></ProtectedRoute>} />
        <Route path="/settings" element={<ProtectedRoute authStatus={authStatus}><Settings /></ProtectedRoute>} />
        <Route path="/admin" element={<AdminRoute authStatus={authStatus}><Admin /></AdminRoute>} />
        <Route path="/monitoring" element={<AdminRoute authStatus={authStatus}><Monitoring /></AdminRoute>} />
        <Route path="/developer" element={<DeveloperRoute authStatus={authStatus}><Developer /></DeveloperRoute>} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
