import axios from "axios";

const api = axios.create({ baseURL: "/v1", withCredentials: true });

let accessToken: string | null = null;

export function setAccessToken(token: string) {
  accessToken = token;
}

export function clearAccessToken() {
  accessToken = null;
}

export function isAuthenticated() {
  return !!accessToken;
}

export async function tryRefresh(): Promise<boolean> {
  try {
    const { data } = await axios.post("/v1/auth/refresh", {}, { withCredentials: true });
    setAccessToken(data.access_token);
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
        const { data } = await axios.post("/v1/auth/refresh", {}, { withCredentials: true });
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
