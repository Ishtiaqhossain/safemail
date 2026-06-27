import axios from "axios";

// Base origin for the API. Defaults to "" so requests are relative ("/v1/...") —
// in production the frontend's nginx proxies /v1 to the API (same-origin, so the
// refresh cookie works with no CORS), and in dev Vite proxies it. Set
// VITE_API_BASE_URL at build time only when pointing at a separate API origin.
export const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

const api = axios.create({ baseURL: `${API_BASE}/v1`, withCredentials: true });

let accessToken: string | null = null;
let adminFlag = false;
let developerFlag = false;
let emailVerifiedFlag = true;
let onboardingCompletedFlag = true;

export function setAccessToken(token: string) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

export function clearAccessToken() {
  accessToken = null;
  adminFlag = false;
  developerFlag = false;
  emailVerifiedFlag = true;
  onboardingCompletedFlag = true;
}

export function setIsAdmin(v: boolean) { adminFlag = v; }
export function getIsAdmin() { return adminFlag; }
export function setIsDeveloper(v: boolean) { developerFlag = v; }
export function getIsDeveloper() { return developerFlag; }
export function setIsEmailVerified(v: boolean) { emailVerifiedFlag = v; }
export function getIsEmailVerified() { return emailVerifiedFlag; }
export function setOnboardingCompleted(v: boolean) { onboardingCompletedFlag = v; }
export function getOnboardingCompleted() { return onboardingCompletedFlag; }

export function isAuthenticated() {
  return !!accessToken;
}

export async function tryRefresh(): Promise<boolean> {
  try {
    const { data } = await axios.post(`${API_BASE}/v1/auth/refresh`, {}, { withCredentials: true });
    setAccessToken(data.access_token);
    setIsAdmin(data.is_admin ?? false);
    setIsDeveloper(data.is_developer ?? false);
    setIsEmailVerified(data.is_email_verified ?? true);
    setOnboardingCompleted(data.onboarding_completed ?? true);
    return true;
  } catch {
    return false;
  }
}

api.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    if (error.response?.status === 401 && !error.config._retry) {
      error.config._retry = true;
      try {
        const { data } = await axios.post(`${API_BASE}/v1/auth/refresh`, {}, { withCredentials: true });
        setAccessToken(data.access_token);
        error.config.headers.Authorization = `Bearer ${data.access_token}`;
        return api(error.config);
      } catch {
        accessToken = null;
        window.location.href = "/login";
      }
    }
    if (error.response?.status === 403 && !accessToken) {
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default api;
