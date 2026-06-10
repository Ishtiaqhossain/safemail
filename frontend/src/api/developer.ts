import api from "./client";

export const devApi = {
  injectFakeAlerts: () =>
    api.post<{ inserted: number; child_name: string }>("/developer/fake-alerts").then((r) => r.data),

  clearFakeData: () =>
    api.delete<{ deleted: number }>("/developer/fake-data").then((r) => r.data),

  triggerPoll: () =>
    api.post<{ status: string }>("/developer/trigger-poll").then((r) => r.data),

  classify: (body: { email_body: string; subject: string; sender: string }) =>
    api.post<Record<string, unknown>>("/developer/classify", body).then((r) => r.data),

  testNotification: () =>
    api.post<{ sent_to: string }>("/developer/test-notification").then((r) => r.data),

  queueDepth: () =>
    api.get<{ pending: number }>("/developer/queue-depth").then((r) => r.data),
};
