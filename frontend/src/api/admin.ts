import api from "./client";
import type { AdminOverview, AdminEvent, TaskLogEntry, LlmStats, AllowedEmail } from "@/types";

interface PagedResponse<T> {
  data: T[];
  meta: { total: number; page: number; per_page: number };
}

export const adminApi = {
  getOverview: () => api.get<AdminOverview>("/admin/overview").then((r) => r.data),

  getEvents: (page = 1) =>
    api.get<PagedResponse<AdminEvent>>("/admin/events", { params: { page, per_page: 50 } }).then((r) => r.data),

  getTasks: (page = 1, status?: string) =>
    api.get<PagedResponse<TaskLogEntry>>("/admin/tasks", { params: { page, per_page: 50, status } }).then((r) => r.data),

  getLlmStats: () => api.get<LlmStats>("/admin/llm-stats").then((r) => r.data),

  getAllowlist: () =>
    api.get<{ data: AllowedEmail[] }>("/admin/allowlist").then((r) => r.data.data),

  addAllowedEmail: (email: string, note?: string) =>
    api.post<AllowedEmail>("/admin/allowlist", { email, note }).then((r) => r.data),

  removeAllowedEmail: (id: string) =>
    api.delete(`/admin/allowlist/${id}`).then((r) => r.data),
};
