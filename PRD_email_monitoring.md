# PRD: AI-Powered Email Monitoring for Child Safety

**Product:** OpenBark  
**Feature:** Email Monitoring & Smart Alerts  
**Author:** Product Team  
**Date:** 2026-06-08  
**Status:** Draft  
**Version:** 1.0

---

## 1. Problem Statement

Children increasingly use email — particularly Gmail — for school, social communication, and app sign-ups. Email is largely invisible to parents: unlike social media, there is no feed to scroll, no profile to check. Predators, bullies, and harmful content exploit this blind spot.

Parents today face a binary choice: read every email their child receives (invasive, time-consuming, erodes trust) or read none (leaves children exposed). There is no middle ground that surfaces only the emails that actually matter.

---

## 2. Goal

Build an AI-powered email monitoring layer that connects to a child's Gmail account, scans incoming and outgoing messages for safety risks, and sends parents a prioritized alert — with enough context to act — only when something genuinely concerning is detected.

**What success looks like in 90 days:**
- Parents receive fewer than 3 false-positive alerts per week per child
- ≥ 80% of parents who receive a true-positive alert take a documented action
- ≤ 5 min from email received to parent alert delivered
- NPS ≥ 40 from beta cohort

---

## 3. Target Users

| Persona | Description |
|---|---|
| **Primary: The Worried Parent** | Has a child aged 8–15 with a school Gmail account. Wants to know about dangers without becoming a surveillance state. |
| **Secondary: The School Administrator** | Manages G Suite for Education deployments. Wants fleet-level safety tooling without manual review overhead. |

---

## 4. User Stories

### Parent
- As a parent, I want to connect my child's Gmail account in under 5 minutes so I don't need technical help to get started.
- As a parent, I want to receive an alert only when something genuinely concerning is detected so I am not overwhelmed by noise.
- As a parent, I want each alert to tell me the severity, a brief summary, and a suggested next step so I know how to respond without reading the full email.
- As a parent, I want to choose which alert categories matter to me so I can tune out topics that are not a concern for my family.
- As a parent, I want a weekly digest of my child's email activity (volume, senders, categories) so I have general awareness without reading individual emails.

### Child
- As a child, I want to know that my parent is notified only for safety reasons — not every email — so I feel like my privacy is respected.

---

## 5. Feature Requirements

### 5.1 Gmail OAuth Connection
- Parent authenticates with Google OAuth 2.0 on behalf of the child's account.
- Scopes required: `gmail.readonly` (read-only; we never send or delete).
- Support for Google Workspace for Education accounts (school-issued Gmail).
- Connection status indicator in dashboard (connected / disconnected / token expired).
- Re-auth prompt if token is revoked or expired.

### 5.2 Email Ingestion Pipeline
- Poll Gmail API for new messages every 5 minutes (Phase 1); migrate to Gmail Push Notifications (Pub/Sub) in Phase 2 for near-real-time.
- Ingest both **inbox** (received) and **sent** folders.
- Extract: sender, recipient(s), subject, body text, attachment filenames, timestamp.
- Strip and ignore email thread history older than 30 days to limit context noise.
- Store only extracted metadata and AI analysis results — never store raw email body text after analysis completes.

### 5.3 AI Analysis Engine

**Detection categories (v1):**

| Category | Examples |
|---|---|
| Self-harm / Suicidal ideation | Expressions of hopelessness, goodbye messages |
| Sexual content / Grooming | Unsolicited sexual language, requests to move to another platform |
| Bullying / Harassment | Targeted threats, coordinated exclusion |
| Drugs / Alcohol | Solicitation, offers, arrangements to obtain |
| Stranger danger | Unknown adults making unusual contact, requests for location or photo |
| Doxxing / Personal info sharing | Child sharing home address, school name, phone number |

**How it works:**
- Run each email through a prompt-based LLM classifier (Claude claude-sonnet-4-6 via Anthropic API).
- Classify by category and severity: `low` / `medium` / `high` / `critical`.
- Generate a 1-2 sentence plain-English summary safe for the parent to read.
- Generate a suggested parent response script appropriate to the severity.
- Flag false-positive risk score to suppress low-confidence alerts.

**Thresholds:**
- `critical` and `high` → immediate push notification + email to parent.
- `medium` → batched into daily digest unless parent opts into real-time.
- `low` → weekly digest only.
- Confidence < 70% → do not alert; log for model review.

### 5.4 Parent Alert Delivery

**Push notification (mobile):**
- Severity badge (color-coded: red / orange / yellow).
- One-line summary: e.g. "Someone asked Emma to share her home address."
- Tap to expand: full summary + suggested response + option to view flagged email in Gmail.

**Email alert:**
- Delivered to parent's email immediately for `critical`/`high`.
- Contains: child name, alert category, AI summary, recommended next step, link to dashboard.
- Does not include the raw email body.

**Weekly digest:**
- Total emails scanned, breakdown by category, any low/medium flags.
- Sent every Sunday at 8am in parent's timezone.

### 5.5 Parent Dashboard (Web)

- **Alert feed:** chronological list of all alerts with severity, category, date, and status (reviewed / unreviewed).
- **Child profile:** connected account, monitoring status, category preferences.
- **Alert preferences:** toggle categories on/off, choose real-time vs. digest per severity level.
- **Activity summary:** weekly email volume chart, top senders (name/domain), category distribution.
- **Feedback on alerts:** thumbs up/down on each alert to improve model accuracy.

### 5.6 Privacy & Data Handling
- Raw email body is processed in memory only; never written to disk or database.
- Only the following are persisted: alert record (category, severity, summary, timestamp, message ID), sender metadata, weekly stats aggregates.
- Data retained for 12 months then auto-deleted.
- Parent can delete all data for a child at any time.
- COPPA compliant: parent is the account holder; child has no direct account.
- All data encrypted at rest (AES-256) and in transit (TLS 1.3).

---

## 6. Out of Scope (v1)

- Attachment content scanning (PDFs, images) — Phase 2
- Non-Gmail providers (Outlook, Yahoo) — Phase 2
- SMS / iMessage monitoring — separate workstream
- Social media monitoring — separate workstream
- AI-generated replies or auto-response on behalf of parent
- Two-way communication between parent and child through the app
- School administrator / fleet management console

---

## 7. Success Metrics

| Metric | Target | Measurement |
|---|---|---|
| Onboarding completion rate | ≥ 70% of signups connect a Gmail account | Funnel analytics |
| Alert precision | ≤ 15% false positive rate | Parent thumbs-down feedback |
| Alert recall | ≥ 85% of injected test cases detected | Monthly red team injection |
| Time to alert | ≤ 5 min (p95) | Pipeline latency logs |
| Parent action rate | ≥ 80% of high/critical alerts marked "reviewed" | Dashboard event tracking |
| 30-day retention | ≥ 65% | Subscription churn |
| NPS | ≥ 40 | In-app survey at day 14 |

---

## 8. Technical Architecture (High Level)

```
Child Gmail Account
      │
      ▼ (OAuth 2.0 / Gmail API)
Ingestion Service (polling → Pub/Sub in Phase 2)
      │
      ▼
Message Queue (deduplicate, rate-limit)
      │
      ▼
AI Analysis Service
  └── Prompt → Anthropic Claude API
  └── Response → category, severity, summary, confidence
      │
      ▼
Alert Router
  ├── critical/high → Push Notification + Email (immediate)
  ├── medium → Daily digest queue
  └── low → Weekly digest queue
      │
      ▼
Parent Dashboard (web) + Mobile App (push)
```

**Stack assumptions:**
- Backend: Node.js or Python (FastAPI)
- Queue: Redis or SQS
- Database: PostgreSQL (alert records, user profiles)
- AI: Anthropic Claude API (`claude-sonnet-4-6`)
- Auth: Google OAuth 2.0 + JWT for parent session
- Notifications: FCM (Android/iOS push) + SendGrid (email)

---

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Google revokes OAuth app approval | Medium | High | Apply for Google's "Trusted" app verification early; build appeal process |
| High false-positive rate erodes parent trust | High | High | Tune confidence threshold; add human review queue for first 1000 alerts |
| LLM API cost at scale | Medium | Medium | Cache repeated sender/pattern analysis; batch low-priority emails |
| COPPA / GDPR compliance gaps | Low | Critical | Legal review before beta; privacy-by-design (no raw body storage) |
| Child circumvents by using alternate email | High | Low | Out of scope to solve fully; note in onboarding |

---

## 10. Milestones

| Milestone | Owner | Target |
|---|---|---|
| Gmail OAuth + ingestion pipeline working | Engineering | Week 3 |
| AI classifier v1 (3 categories) | Engineering / AI | Week 5 |
| Parent alert delivery (email + push) | Engineering | Week 6 |
| Web dashboard MVP | Engineering / Design | Week 8 |
| Closed beta (50 families) | Product | Week 9 |
| Precision/recall red team review | Product / AI | Week 10 |
| Public launch (paid) | All | Week 12 |

---

## 11. Open Questions

1. Do we require parental consent UI from the child, or is parent-only consent sufficient under our legal framework?
2. What is our policy if a `critical` alert (e.g. active self-harm) is detected — do we surface crisis hotline numbers automatically?
3. Should the child be notified that monitoring is active, and if so, how?
4. Gmail API polling limits: 250 quota units/user/second — do we need to request quota increase from Google for scale?
5. What LLM prompt strategy gives best precision/recall tradeoff — zero-shot, few-shot, or fine-tuned classifier?
