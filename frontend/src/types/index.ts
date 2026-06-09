export type Severity = "critical" | "high" | "medium" | "low";
export type Category =
  | "self_harm"
  | "grooming"
  | "bullying"
  | "drugs_alcohol"
  | "stranger_contact"
  | "personal_info_sharing";

export interface Alert {
  id: string;
  child_id: string;
  child_name: string;
  direction: "inbound" | "outbound";
  sender_address: string;
  recipient_addresses: string[];
  subject_snippet: string | null;
  received_at: string;
  category: Category;
  severity: Severity;
  confidence: number;
  ai_summary: string;
  ai_response_script: string | null;
  parent_feedback: "correct" | "false_positive" | null;
  notified_at: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface AlertListResponse {
  data: Alert[];
  meta: { total: number; page: number; per_page: number };
}

export interface Child {
  id: string;
  display_name: string;
  birth_year: number | null;
  created_at: string;
  gmail_connections: GmailConnection[];
}

export interface GmailConnection {
  id: string;
  gmail_address: string;
  status: "active" | "revoked" | "error";
  last_synced_at: string | null;
}

export interface AlertPreference {
  disabled_categories: Category[] | null;
  immediate_severities: Severity[];
  digest_frequency: "daily" | "weekly";
}

export interface WeeklyStats {
  week_start: string;
  total_emails: number;
  emails_scanned: number;
  alerts_by_severity: Partial<Record<Severity, number>>;
  alerts_by_category: Partial<Record<Category, number>>;
  top_senders: { address: string; count: number }[];
}
