import api from "./client";
import type { AdminOverview, AdminEvent, TaskLogEntry } from "@/types";

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
};
