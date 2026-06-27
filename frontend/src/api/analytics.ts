import api from "./client";

export interface FunnelStage {
  key: string;
  label: string;
  count: number;
  step_conversion: number | null;
  drop_off: number;
  overall_conversion: number | null;
}

export interface AnalyticsFunnel {
  window_days: number;
  acquisition: FunnelStage[];
  activation: {
    stages: FunnelStage[];
    time_to_value_seconds: number | null;
    activation_rate: number | null;
  };
}

export interface AnalyticsOverview {
  window_days: number;
  unique_visitors: number;
  page_views: number;
  waitlist_joined: number;
  signups: number;
  activated: number;
  activation_rate: number | null;
  logins: number;
  account_deletions: number;
  acquisition_funnel: FunnelStage[];
}

export interface AnalyticsEvents {
  window_days: number;
  by_name: { event: string; count: number }[];
  top_paths: { path: string; count: number }[];
  top_referrers: { referrer: string; count: number }[];
  daily: { day: string; page_views: number; visitors: number; signups: number }[];
}

export const analyticsApi = {
  overview: (days = 30) =>
    api.get<AnalyticsOverview>("/analytics/overview", { params: { days } }).then((r) => r.data),
  funnel: (days = 30) =>
    api.get<AnalyticsFunnel>("/analytics/funnel", { params: { days } }).then((r) => r.data),
  events: (days = 30) =>
    api.get<AnalyticsEvents>("/analytics/events", { params: { days } }).then((r) => r.data),
};
