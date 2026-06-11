import api from "./client";

export const authApi = {
  // Permanently erase the parent account and all associated data
  // (children, Gmail connections, alerts, preferences, stats). Irreversible.
  deleteAccount: () => api.delete("/auth/account"),
};
