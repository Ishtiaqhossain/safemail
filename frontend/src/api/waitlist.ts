import axios from "axios";
import { API_BASE } from "./client";

// Public, unauthenticated endpoint. We deliberately use a bare axios call (not
// the shared `api` instance) so the auth interceptors — which redirect to
// /login on 401/403 — never fire for an anonymous visitor on the landing page.
//
// Returns the backend status: "ok" when added to (or already on) the waitlist,
// or "already_invited" when the email is already on the allowlist and can
// register right away.
export type WaitlistStatus = "ok" | "already_invited";

export async function joinWaitlist(email: string, source = "landing"): Promise<WaitlistStatus> {
  const { data } = await axios.post(`${API_BASE}/v1/waitlist`, { email, source }, { withCredentials: true });
  return (data?.status as WaitlistStatus) ?? "ok";
}
