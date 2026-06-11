import api from "./client";

export const onboardingApi = {
  consent: () =>
    api.post<{ monitoring_consent: boolean }>("/onboarding/consent").then((r) => r.data),

  complete: () =>
    api.post<{ onboarding_completed: boolean }>("/onboarding/complete").then((r) => r.data),
};
