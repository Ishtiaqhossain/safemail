# SafeMail Analytics Suite — Spec

A first-party, privacy-respecting product-analytics suite for SafeMail's full user
funnel: **landing visit → waitlist → register → verify → consent → add child →
connect Gmail → onboarded → first alert → engagement → churn.** It answers: how
many people enter each stage, where they drop off, and how long activation takes.

## 1. Research & decision

We surveyed event-taxonomy practice and the analytics tooling landscape before
building:

- **Taxonomy** — use `object_action`, `snake_case`, **fixed** event names (dynamic
  data goes in properties, never in names), an **allowlist** of 10–200 events, ≤20
  properties each. ([taxonomy playbook](https://www.digitalapplied.com/blog/product-analytics-event-taxonomy-tracking-plan-2026),
  [Segment naming](https://segment.com/academy/collecting-data/naming-conventions-for-clean-data/),
  [PostHog best practices](https://posthog.com/docs/product-analytics/best-practices))
- **Funnel framework** — AARRR (Acquisition, Activation, Retention, Revenue,
  Referral). Activation is the **"aha moment"**, not signup; measure per-stage
  drop-off and **time-to-value**. Signup→activated commonly leaks ~70%.
  ([Amplitude AARRR](https://amplitude.com/blog/pirate-metrics-framework),
  [TTV framework](https://www.digitalapplied.com/blog/customer-onboarding-time-to-value-2026-saas-metrics-framework))
- **Tooling** — Plausible/Umami are cookieless web analytics but can't see
  server-side funnel steps; PostHog is full-featured but heavy and SaaS-leaning.
  ([OpenPanel survey](https://openpanel.dev/articles/self-hosted-web-analytics),
  [PostHog GDPR roundup](https://posthog.com/blog/best-gdpr-compliant-analytics-tools))
- **Schema** — event store keyed by an anonymous first-party `visitor_id`
  pre-login, stitched to a stable user id post-login; no IP/PII.
  ([first-party tracking](https://analytics-api.com/first-party-data-tracking-building-analytics-without-cookies/))

**Decision: build first-party, in-house, no third-party SaaS.** SafeMail handles
children's data and promises "raw email body is never stored" / full account
erasure. Sending any funnel data to GA4/Mixpanel/PostHog-cloud would contradict
that posture (same reasoning we applied to keeping LLM tracing self-hosted). A
purpose-built first-party suite also lets us span the server-side funnel steps that
cookieless web-analytics tools can't see, and reconstruct most of the funnel
retroactively from data we already have.

> If this ever needs session replay, A/B testing, or warehouse-scale event volume,
> the scale-up path is **self-hosted PostHog** — not a SaaS. Until then, in-house
> is simpler, cheaper, and privacy-clean.

## 2. Privacy model (load-bearing)

1. **No PII, ever.** Events store an anonymous random `visitor_id`, an optional
   `parent_id` (UUID, not email), page path, referrer, UTM, and a small properties
   bag. No IP address, no email, no child name/birth-year/Gmail address, no email
   content or alert summaries.
2. **Right-to-erasure reaches analytics.** `analytics_events.parent_id` is
   `ON DELETE CASCADE`, so deleting an account erases that parent's events.
   Anonymous pre-login rows have no link to a person and carry no PII.
3. **First-party only.** Events post to our own `/v1/analytics/collect`; no
   third-party scripts, no third-party cookies.
4. **Respect Do-Not-Track / Global Privacy Control.** The client tracker is a
   no-op when `navigator.doNotTrack === "1"` or `navigator.globalPrivacyControl`
   is set. Identifier lives in `localStorage` (anonymous random UUID), not a
   tracking cookie.
5. **Consent note.** `monitoring_consent_at` covers child-email monitoring, not
   parent web analytics. Collection here is anonymous and metadata-only; teams
   with strict ePrivacy obligations may still want a cookie/consent banner before
   enabling client tracking. That's a product decision left to the operator;
   server-side conversion events (which need no client storage) work regardless.

## 3. Event taxonomy (the allowlist)

`object_action`, snake_case. The backend rejects names outside this set so the
data stays clean. Source is `client` (browser) or `server` (authoritative).

| Event | Source | Where | Funnel stage |
|---|---|---|---|
| `page_viewed` | client | every route change | Acquisition |
| `landing_cta_clicked` | client | Landing CTAs | Acquisition |
| `waitlist_joined` | server | `POST /waitlist` | Acquisition |
| `waitlist_already_invited` | server | `POST /waitlist` | Acquisition |
| `account_registered` | server | `POST /auth/register` | Signup |
| `login_succeeded` | server | `POST /auth/login` | Retention |
| `email_verified` | server | `GET /auth/verify-email` | Activation |
| `onboarding_step_viewed` | client | onboarding wizard steps | Activation |
| `consent_given` | server | `POST /onboarding/consent` | Activation |
| `child_added` | server | `POST /children` | Activation |
| `gmail_connect_initiated` | client | "Connect Gmail" click | Activation |
| `gmail_connected` | server | OAuth callback | **Activation (aha)** |
| `gmail_connect_skipped` | client | "I'll connect later" | Activation |
| `onboarding_completed` | server | `POST /onboarding/complete` | Activation |
| `alerts_viewed` | client | AlertFeed load | Engagement |
| `alert_viewed` | client | AlertDetail load | Engagement |
| `alert_feedback_given` | server | `POST /alerts/:id/feedback` | Engagement |
| `gmail_disconnected` | server | disconnect | Churn signal |
| `account_deleted` | server | `DELETE /auth/account` | Churn |

Properties carry dynamics (e.g. `landing_cta_clicked` → `{cta: "hero_waitlist"}`,
`alert_feedback_given` → `{value: "correct"}`, `onboarding_step_viewed` →
`{step: 4, label: "Connect Gmail"}`).

## 4. The funnels

We expose **two** complementary views:

### A. Acquisition (event-based, windowed by event time — forward-looking)
`Unique visitors → Waitlist joined → Registered`. Derived from `page_viewed`
(distinct `visitor_id`), `waitlist_joined`, and `account_registered` events. This
is the top-of-funnel the database alone can't see; it populates as client/server
events accrue.

### B. Activation (cohort-based on Parent rows — works retroactively today)
Take every parent **created in the window**, then check how far each one got,
regardless of when:

`Registered → Email verified → Consent given → Child added → Gmail connected →
Onboarding completed → Received first alert`

For each step: **count**, **step conversion %** (vs previous), **drop-off %**, and
overall conversion. Plus **time-to-value**: median(`onboarding_completed_at −
created_at`) and median(first `GmailConnection.created_at − created_at`).

This is a true single-cohort funnel computed from existing timestamps
(`Parent.created_at/onboarding_completed_at/monitoring_consent_at/is_email_verified`,
`Child.created_at`, `GmailConnection.created_at`, `Alert.created_at`), so it's
accurate for existing users on day one — no waiting for instrumentation.

### Known gaps (documented, not hidden)
- No historical `email_verified_at` or login events exist pre-instrumentation, so
  retroactive verification timing and login frequency start from rollout.
- Waitlist rows are deleted on approval, so durable waitlist counts come from the
  `waitlist_joined` **event**, not the `waitlist_entries` table.
- Visitor→signup stitching across the anonymous boundary is approximate (standard
  for first-party analytics).

## 5. Architecture

```
Browser ──page_viewed / *_clicked──▶ POST /v1/analytics/collect (public, batched)
                                          │  validate against allowlist, no PII
Routers/tasks ──record_event(server)──▶  analytics_events (Postgres, JSONB props)
                                          │
Admin console ◀── GET /v1/analytics/{overview,funnel,events} (admin-gated)
```

- **Model:** `analytics_events` (`app/models/analytics_event.py`) — `event_name`,
  `visitor_id`, `session_id`, `parent_id` (CASCADE), `path`, `referrer`, `utm`,
  `source`, `properties`, `created_at`; indexed on name+created, visitor, parent,
  created.
- **Service:** `app/services/analytics_events.py` — the allowlist, async
  `record_event_async` (routers) and sync `record_event_sync` (Celery), plus the
  funnel/overview computation helpers.
- **Ingestion:** `POST /v1/analytics/collect` — public, accepts a batch, validates
  names, caps size/length, stamps `created_at`, stitches `parent_id` if a bearer
  token is present.
- **Read API (admin):** `GET /v1/analytics/overview`, `/funnel`, `/events`.
- **Client:** `frontend/src/analytics.ts` — first-party `visitor_id`
  (localStorage) + `session_id` (sessionStorage), `track()`/`pageview()`, batched
  flush (interval + `visibilitychange`), UTM/referrer capture, DNT/GPC respect.
- **Dashboard:** an `Analytics` tab in `pages/Admin.tsx`.

## 6. Out of scope (for now)
Revenue/MRR (no billing yet), referral/virality loops, A/B experimentation,
session replay, per-user drill-down. All are additive on this foundation.
