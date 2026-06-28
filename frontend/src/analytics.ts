// First-party, privacy-respecting analytics client.
//
// - Anonymous: a random visitor_id (localStorage) + session_id (sessionStorage).
//   No PII is ever sent; events carry only an event name, path, referrer, UTM,
//   and a small properties bag.
// - First-party: posts to our own /v1/analytics/collect — no third-party scripts.
// - Respects Do-Not-Track / Global Privacy Control: a no-op when set.
// See docs/analytics-spec.md.
import { API_BASE, getAccessToken } from "./api/client";

const VID_KEY = "sm_vid";
const SID_KEY = "sm_sid";
const FLUSH_MS = 4000;
const MAX_BATCH = 50;

const disabled =
  typeof navigator !== "undefined" &&
  (navigator.doNotTrack === "1" ||
    (window as unknown as { doNotTrack?: string }).doNotTrack === "1" ||
    (navigator as unknown as { globalPrivacyControl?: boolean }).globalPrivacyControl === true);

function randomId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.floor(Math.random() * 1e9)}`;
}

function getVisitorId(): string {
  let v = localStorage.getItem(VID_KEY);
  if (!v) {
    v = randomId();
    localStorage.setItem(VID_KEY, v);
  }
  return v;
}

function getSessionId(): string {
  let s = sessionStorage.getItem(SID_KEY);
  if (!s) {
    s = randomId();
    sessionStorage.setItem(SID_KEY, s);
  }
  return s;
}

interface QueuedEvent {
  name: string;
  path?: string;
  referrer?: string;
  utm?: Record<string, string>;
  properties?: Record<string, unknown>;
}

let queue: QueuedEvent[] = [];
let timer: number | null = null;

function parseUtm(): Record<string, string> | undefined {
  const p = new URLSearchParams(window.location.search);
  const utm: Record<string, string> = {};
  for (const k of ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"]) {
    const val = p.get(k);
    if (val) utm[k.replace("utm_", "")] = val;
  }
  return Object.keys(utm).length ? utm : undefined;
}

function scheduleFlush() {
  if (timer != null) return;
  timer = window.setTimeout(() => {
    timer = null;
    flush();
  }, FLUSH_MS);
}

export function flush() {
  if (disabled || queue.length === 0) return;
  const events = queue.splice(0, MAX_BATCH);
  const batch = { visitor_id: getVisitorId(), session_id: getSessionId(), events };
  const token = getAccessToken();
  try {
    // keepalive lets the request survive a page unload (replaces sendBeacon, and
    // unlike sendBeacon it can carry the Authorization header for parent stitching).
    fetch(`${API_BASE}/v1/analytics/collect`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(batch),
      keepalive: true,
    }).catch(() => {});
  } catch {
    /* never let analytics throw into the app */
  }
}

export function track(name: string, properties?: Record<string, unknown>) {
  if (disabled) return;
  queue.push({ name, path: window.location.pathname, properties });
  scheduleFlush();
}

export function pageview(path: string) {
  if (disabled) return;
  queue.push({
    name: "page_viewed",
    path,
    referrer: document.referrer || undefined,
    utm: parseUtm(),
  });
  scheduleFlush();
}

let inited = false;
export function initAnalytics() {
  if (disabled || inited) return;
  inited = true;
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flush();
  });
  window.addEventListener("pagehide", () => flush());
}
