import api from "./client";
import type { Alert, AlertListResponse, AlertPreference } from "@/types";

export interface AlertFilters {
  child_id?: string;
  severity?: string;
  category?: string;
  reviewed?: boolean;
  from?: string;
  to?: string;
  page?: number;
  per_page?: number;
}

export const alertsApi = {
  list: (filters: AlertFilters = {}) =>
    api.get<AlertListResponse>("/alerts", { params: filters }).then((r) => r.data),

  markReviewed: (id: string) =>
    api.patch<Alert>(`/alerts/${id}`, { reviewed: true }).then((r) => r.data),

  submitFeedback: (id: string, feedback: "correct" | "false_positive") =>
    api.post(`/alerts/${id}/feedback`, { feedback }).then((r) => r.data),

  getPreferences: (childId: string) =>
    api.get<AlertPreference>(`/children/${childId}/preferences`).then((r) => r.data),

  updatePreferences: (childId: string, prefs: AlertPreference) =>
    api.put<AlertPreference>(`/children/${childId}/preferences`, prefs).then((r) => r.data),
};
