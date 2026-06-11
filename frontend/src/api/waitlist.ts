import axios from "axios";
import { API_BASE } from "./client";

// Public, unauthenticated endpoint. We deliberately use a bare axios call (not
// the shared `api` instance) so the auth interceptors — which redirect to
// /login on 401/403 — never fire for an anonymous visitor on the landing page.
export async function joinWaitlist(email: string, source = "landing"): Promise<void> {
  await axios.post(`${API_BASE}/v1/waitlist`, { email, source }, { withCredentials: true });
}
