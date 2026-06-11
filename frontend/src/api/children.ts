import api from "./client";
import type { Child, WeeklyStats } from "@/types";

export const childrenApi = {
  list: () => api.get<Child[]>("/children").then((r) => r.data),

  create: (displayName: string, birthYear?: number) =>
    api.post<Child>("/children", { display_name: displayName, birth_year: birthYear }).then((r) => r.data),

  update: (id: string, displayName?: string, birthYear?: number) =>
    api.patch<Child>(`/children/${id}`, { display_name: displayName, birth_year: birthYear }).then((r) => r.data),

  delete: (id: string) => api.delete(`/children/${id}`),

  getStats: (childId: string, week?: string) =>
    api.get<WeeklyStats>(`/children/${childId}/stats`, { params: { week } }).then((r) => r.data),

  connectGmail: (childId: string, returnTo?: string) => {
    const qs = returnTo ? `&return_to=${encodeURIComponent(returnTo)}` : "";
    return api.get<{ auth_url: string }>(`/auth/google/connect?child_id=${childId}${qs}`)
      .then((r) => { window.location.href = r.data.auth_url; });
  },

  disconnectGmail: (connectionId: string) => api.delete(`/auth/google/${connectionId}`),
};
