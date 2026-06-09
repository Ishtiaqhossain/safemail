import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { NavBar } from "@/components/NavBar";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import AlertFeed from "@/pages/AlertFeed";
import AlertDetail from "@/pages/AlertDetail";
import Settings from "@/pages/Settings";

function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <NavBar />
      <main>{children}</main>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/dashboard" element={<AuthLayout><Dashboard /></AuthLayout>} />
        <Route path="/alerts" element={<AuthLayout><AlertFeed /></AuthLayout>} />
        <Route path="/alerts/:id" element={<AuthLayout><AlertDetail /></AuthLayout>} />
        <Route path="/settings" element={<AuthLayout><Settings /></AuthLayout>} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
