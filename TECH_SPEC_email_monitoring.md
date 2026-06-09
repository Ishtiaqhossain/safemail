# Technical Specification: Email Monitoring MVP

**Product:** OpenBark — Email Monitoring  
**Spec Version:** 1.0  
**Date:** 2026-06-08  
**Status:** Draft  
**References:** PRD_email_monitoring.md

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                             │
│   Parent Web App (React)          Parent Mobile App (React Native) │
└────────────────────┬────────────────────────────┬───────────────┘
                     │ HTTPS / REST                │ FCM Push
┌────────────────────▼────────────────────────────▼───────────────┐
│                       API GATEWAY (REST)                        │
│                    api.openbark.com/v1                          │
└──┬──────────────┬───────────────┬──────────────┬────────────────┘
   │              │               │              │
┌──▼───┐  ┌──────▼──────┐ ┌──────▼──────┐ ┌────▼──────────────┐
│ Auth │  │  Ingestion  │ │  Analysis   │ │  Alert / Notif    │
│ Svc  │  │  Service    │ │  Service    │ │  Service          │
└──┬───┘  └──────┬──────┘ └──────┬──────┘ └────┬──────────────┘
   │              │               │              │
┌──▼──────────────▼───────────────▼──────────────▼──────────────┐
│                    PostgreSQL (primary DB)                      │
│                    Redis (queue + cache)                        │
└────────────────────────────────────────────────────────────────┘
         │                          │
┌────────▼──────────┐    ┌──────────▼──────────┐
│   Gmail API       │    │  Anthropic Claude    │
│   (Google)        │    │  API                 │
└───────────────────┘    └─────────────────────┘
```

---

## 2. Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Backend runtime | Python 3.12 + FastAPI | Async-native, fast iteration, strong AI/ML ecosystem |
| Task queue | Celery + Redis | Battle-tested for polling jobs and retries |
| Database | PostgreSQL 16 | Relational integrity for users/alerts; JSONB for flexible metadata |
| Cache / broker | Redis 7 | Queue broker, token cache, dedup store |
| AI | Anthropic Claude API (`claude-sonnet-4-6`) | Best precision/recall for nuanced text safety classification |
| Email provider | SendGrid | Transactional email reliability |
| Push notifications | Firebase Cloud Messaging (FCM) | Cross-platform iOS + Android |
| Auth | Google OAuth 2.0 + JWT (RS256) | Required for Gmail; JWT for parent session |
| Frontend | React 18 + TypeScript | Web dashboard |
| Infrastructure | AWS (ECS Fargate + RDS + ElastiCache) | Managed, scales to zero in beta |
| CI/CD | GitHub Actions | |
| Secrets | AWS Secrets Manager | |

---

## 3. Database Schema

```sql
-- Parents who have accounts
CREATE TABLE parents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    full_name       TEXT,
    timezone        TEXT NOT NULL DEFAULT 'UTC',
    fcm_token       TEXT,                          -- for push notifications
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Child profiles (no direct login)
CREATE TABLE children (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id       UUID NOT NULL REFERENCES parents(id) ON DELETE CASCADE,
    display_name    TEXT NOT NULL,
    birth_year      INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per connected Gmail account
CREATE TABLE gmail_connections (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id            UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    gmail_address       TEXT NOT NULL,
    access_token        TEXT NOT NULL,             -- encrypted at app level
    refresh_token       TEXT NOT NULL,             -- encrypted at app level
    token_expiry        TIMESTAMPTZ NOT NULL,
    history_id          TEXT,                      -- Gmail historyId for incremental sync
    status              TEXT NOT NULL DEFAULT 'active', -- active | revoked | error
    last_synced_at      TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (child_id, gmail_address)
);

-- Detected alerts (one per flagged email)
CREATE TABLE alerts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id            UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    gmail_connection_id UUID NOT NULL REFERENCES gmail_connections(id),
    gmail_message_id    TEXT NOT NULL,             -- Gmail message ID (not stored body)
    direction           TEXT NOT NULL,             -- 'inbound' | 'outbound'
    sender_address      TEXT NOT NULL,
    recipient_addresses TEXT[] NOT NULL,
    subject_snippet     TEXT,                      -- first 80 chars only
    received_at         TIMESTAMPTZ NOT NULL,
    category            TEXT NOT NULL,             -- see detection categories
    severity            TEXT NOT NULL,             -- critical | high | medium | low
    confidence          NUMERIC(4,3) NOT NULL,     -- 0.000–1.000
    ai_summary          TEXT NOT NULL,             -- 1-2 sentence parent-safe summary
    ai_response_script  TEXT,                      -- suggested parent response
    parent_feedback     TEXT,                      -- 'correct' | 'false_positive' | null
    notified_at         TIMESTAMPTZ,               -- when parent was alerted
    reviewed_at         TIMESTAMPTZ,               -- when parent marked reviewed
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_alerts_child_id ON alerts(child_id);
CREATE INDEX idx_alerts_severity ON alerts(severity);
CREATE INDEX idx_alerts_created_at ON alerts(created_at DESC);

-- Parent alert preferences per child
CREATE TABLE alert_preferences (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id           UUID NOT NULL REFERENCES parents(id) ON DELETE CASCADE,
    child_id            UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    -- categories: comma-separated list of disabled categories, null = all enabled
    disabled_categories TEXT[],
    -- delivery: which severities trigger immediate notification vs digest
    immediate_severities TEXT[] NOT NULL DEFAULT ARRAY['critical','high'],
    digest_frequency    TEXT NOT NULL DEFAULT 'weekly', -- daily | weekly
    UNIQUE (parent_id, child_id)
);

-- Weekly activity aggregates (pre-computed, never raw body)
CREATE TABLE weekly_stats (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id            UUID NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    week_start          DATE NOT NULL,
    total_emails        INT NOT NULL DEFAULT 0,
    emails_scanned      INT NOT NULL DEFAULT 0,
    alerts_by_severity  JSONB NOT NULL DEFAULT '{}', -- {"critical":0,"high":0,...}
    alerts_by_category  JSONB NOT NULL DEFAULT '{}',
    top_senders         JSONB NOT NULL DEFAULT '[]', -- [{address, count}] top 10
    UNIQUE (child_id, week_start)
);
```

---

## 4. Service Specifications

### 4.1 Auth Service

**Endpoints:**

```
POST   /v1/auth/register          Register parent account
POST   /v1/auth/login             Email + password login → JWT
POST   /v1/auth/refresh           Refresh JWT using refresh token
POST   /v1/auth/logout            Revoke refresh token
GET    /v1/auth/google/connect    Initiate Gmail OAuth flow for a child
GET    /v1/auth/google/callback   Handle OAuth callback, store tokens
DELETE /v1/auth/google/:id        Revoke Gmail connection
```

**JWT spec:**
- Algorithm: RS256
- Access token TTL: 15 minutes
- Refresh token TTL: 30 days (stored in HttpOnly cookie)
- Claims: `{ sub: parent_id, email, iat, exp }`

**Gmail OAuth flow:**

```
1. Parent clicks "Connect Gmail" for a child
2. GET /v1/auth/google/connect?child_id=<uuid>
   → Server generates state = JWT-signed { child_id, parent_id }
   → Redirect to Google OAuth consent screen
      scopes: gmail.readonly, userinfo.email
      access_type: offline (to get refresh token)
      prompt: consent (force refresh token issuance)

3. Google redirects to GET /v1/auth/google/callback?code=...&state=...
   → Verify state signature
   → Exchange code for access_token + refresh_token
   → Encrypt both tokens (AES-256-GCM, key from AWS Secrets Manager)
   → Store in gmail_connections
   → Trigger initial sync job for this connection
```

**Token encryption:**
```python
# Tokens are sensitive — never stored plaintext
# Use Fernet (AES-128-CBC + HMAC-SHA256) from cryptography library
from cryptography.fernet import Fernet

def encrypt_token(plaintext: str) -> str:
    return fernet.encrypt(plaintext.encode()).decode()

def decrypt_token(ciphertext: str) -> str:
    return fernet.decrypt(ciphertext.encode()).decode()
```

---

### 4.2 Ingestion Service

**Responsibility:** Poll Gmail for new messages and push raw (decrypted in-memory) message data onto the analysis queue.

**Celery beat schedule:**
```python
CELERYBEAT_SCHEDULE = {
    "poll-all-connections": {
        "task": "ingestion.tasks.poll_all_connections",
        "schedule": crontab(minute="*/5"),  # every 5 minutes
    },
    "aggregate-weekly-stats": {
        "task": "ingestion.tasks.aggregate_weekly_stats",
        "schedule": crontab(day_of_week="sun", hour=3, minute=0),
    },
}
```

**Poll task flow:**

```
poll_all_connections()
  → Query gmail_connections WHERE status = 'active'
  → For each connection, enqueue poll_connection(connection_id)

poll_connection(connection_id)
  → Load connection, decrypt tokens
  → If token_expiry < now + 5min: refresh via Google Token API
  → Call Gmail API: users.messages.list
      - q: "in:inbox OR in:sent"
      - maxResults: 50
      - pageToken: use history_id for incremental if available
  → For each message_id NOT in redis dedup set:
      → Fetch full message: users.messages.get(id, format='full')
      → Extract fields (see below)
      → Push to Redis queue: "analysis:pending"
      → Add message_id to redis dedup set (TTL: 7 days)
  → Update gmail_connections.last_synced_at and history_id
```

**Message extraction:**
```python
def extract_message(raw: dict, connection: GmailConnection) -> dict:
    headers = {h["name"]: h["value"] for h in raw["payload"]["headers"]}
    body = decode_body(raw["payload"])  # handles multipart

    return {
        "gmail_message_id": raw["id"],
        "gmail_connection_id": str(connection.id),
        "child_id": str(connection.child_id),
        "direction": "outbound" if headers.get("From", "").contains(connection.gmail_address) else "inbound",
        "sender_address": headers.get("From", ""),
        "recipient_addresses": parse_addresses(headers.get("To", "") + headers.get("Cc", "")),
        "subject": headers.get("Subject", "")[:80],
        "body_text": body[:8000],  # truncate — LLM context limit
        "received_at": parse_date(headers.get("Date")),
    }
    # NOTE: body_text exists ONLY in memory / the queue message.
    # It is NOT written to the database at any point.
```

**Error handling:**
- `401` from Google → mark connection status = 'error', notify parent to reconnect
- `429` rate limit → exponential backoff, max 3 retries
- Celery task failure → auto-retry up to 3 times with 60s delay

---

### 4.3 Analysis Service

**Responsibility:** Consume messages from the queue, run AI classification, persist alert records, route to notification service.

**Consumer loop:**
```
analyze_message(message: dict)
  → Check if gmail_message_id already analyzed (redis cache, TTL 24h)
  → Build prompt (see below)
  → Call Anthropic Claude API
  → Parse structured response
  → If confidence < 0.70: discard, log to metrics only
  → If confidence ≥ 0.70 AND severity != 'none':
      → Insert into alerts table (no body text stored)
      → Enqueue notify_parent(alert_id)
  → Update weekly_stats aggregate
```

**Claude API call:**
```python
import anthropic

client = anthropic.Anthropic()

SYSTEM_PROMPT = """
You are a child safety classifier for a parental monitoring service.
Analyze the provided email and determine if it contains content that
poses a safety risk to a minor. Be precise — false positives erode
parent trust. Normal school, social, or commercial emails should return
severity 'none'.

Respond ONLY with valid JSON matching this schema:
{
  "severity": "none" | "low" | "medium" | "high" | "critical",
  "category": "none" | "self_harm" | "grooming" | "bullying" | 
               "drugs_alcohol" | "stranger_contact" | "personal_info_sharing",
  "confidence": <float 0.0–1.0>,
  "summary": "<1-2 sentences describing the concern, written for a parent>",
  "response_script": "<suggested next step for the parent, or null if severity is none>"
}
"""

def classify_email(message: dict) -> dict:
    user_content = f"""
Direction: {message['direction']}
From: {message['sender_address']}
To: {', '.join(message['recipient_addresses'])}
Subject: {message['subject']}

Body:
{message['body_text']}
"""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return json.loads(response.content[0].text)
```

**Detection categories and severity guide (baked into prompt):**

| Category | Low | Medium | High | Critical |
|---|---|---|---|---|
| `self_harm` | Vague expressions of sadness | Hopelessness, worthlessness | Active self-harm references | Explicit suicide plan/intent |
| `grooming` | Unusual adult contact | Requests to move to private channel | Sexual language | Explicit solicitation of minor |
| `bullying` | Mild teasing | Sustained targeting | Threats | Coordinated harassment campaign |
| `drugs_alcohol` | References to others using | Child expressing interest | Offer/solicitation | Active arrangement to obtain |
| `stranger_contact` | Unknown adult initiating casual contact | Unusual questions (location, school) | Requests for photos | Requests to meet in person |
| `personal_info_sharing` | First name only | School name | Home address, phone | Full identity + location |

**Cost control:**
- Skip analysis if sender is in known-safe list (e.g. Google, school domain verified by parent)
- Max body length: 8,000 chars (~2,000 tokens) — truncate older thread history first
- Estimated cost per email: ~$0.003 (input) + ~$0.001 (output) = ~$0.004/email
- At 50 emails/day/child: ~$0.20/child/day → $6/child/month — within $14/mo plan margin

---

### 4.4 Alert & Notification Service

**Responsibility:** Deliver alerts to parents via push and email based on severity and preferences.

**Flow:**
```
notify_parent(alert_id)
  → Load alert + child + parent + preferences
  → Determine delivery mode:
      if severity in preferences.immediate_severities:
          send_push_notification(parent, alert)
          send_alert_email(parent, alert)
      else:
          enqueue_for_digest(alert_id, parent_id)
  → Update alerts.notified_at
```

**Push notification payload (FCM):**
```json
{
  "token": "<parent_fcm_token>",
  "notification": {
    "title": "Alert for Emma",
    "body": "Someone asked Emma to share her home address."
  },
  "data": {
    "alert_id": "<uuid>",
    "severity": "high",
    "category": "personal_info_sharing",
    "child_name": "Emma"
  },
  "android": { "priority": "high" },
  "apns": { "headers": { "apns-priority": "10" } }
}
```

**Alert email (SendGrid dynamic template):**
```
Subject: [OpenBark] High Alert — Emma's Email

Severity:  HIGH
Category:  Personal Information Sharing
Detected:  June 8, 2026 at 2:34 PM

What we found:
An unknown sender asked Emma to share her home address in an email.

Suggested next step:
Talk with Emma about not sharing personal location information with
people she hasn't met in person. You may want to check who this
sender is and consider blocking the address.

[ View in Dashboard ]

Note: We do not include the original email in this alert to protect
Emma's privacy. You can view the email directly in her Gmail account.
```

**Weekly digest (Celery task, Sunday 8am parent timezone):**
```python
def send_weekly_digest(parent_id: str):
    children = get_children(parent_id)
    for child in children:
        stats = get_weekly_stats(child.id, last_week())
        medium_low_alerts = get_alerts(child.id, severities=["medium","low"], week=last_week())
        render_and_send_digest_email(parent, child, stats, medium_low_alerts)
```

---

## 5. REST API Specification

Base URL: `https://api.openbark.com/v1`  
Auth: `Authorization: Bearer <access_token>` on all endpoints except `/auth/*`

### 5.1 Children

```
GET    /children                    List parent's children
POST   /children                    Create child profile
PATCH  /children/:id                Update child name/birth_year
DELETE /children/:id                Delete child + cascade all data

Body (POST/PATCH):
{
  "display_name": "Emma",
  "birth_year": 2014
}
```

### 5.2 Gmail Connections

```
GET    /children/:id/connections    List Gmail connections for child
DELETE /connections/:id             Disconnect Gmail account

GET /auth/google/connect?child_id=:id
  → 302 redirect to Google OAuth
GET /auth/google/callback?code=...&state=...
  → 302 redirect to /dashboard?connected=true
```

### 5.3 Alerts

```
GET  /alerts                        List alerts (paginated)
  Query params:
    child_id      filter by child
    severity      filter: critical,high,medium,low
    category      filter by category
    reviewed      filter: true | false
    from          ISO date
    to            ISO date
    page          default 1
    per_page      default 25, max 100

Response:
{
  "data": [
    {
      "id": "uuid",
      "child_id": "uuid",
      "child_name": "Emma",
      "direction": "inbound",
      "sender_address": "unknown@example.com",
      "subject_snippet": "Quick question...",
      "received_at": "2026-06-08T14:34:00Z",
      "category": "personal_info_sharing",
      "severity": "high",
      "ai_summary": "An unknown sender asked Emma to share her home address.",
      "ai_response_script": "Talk with Emma about...",
      "reviewed_at": null,
      "notified_at": "2026-06-08T14:38:22Z"
    }
  ],
  "meta": { "total": 42, "page": 1, "per_page": 25 }
}

PATCH /alerts/:id
  Body: { "reviewed": true }
  → Sets reviewed_at = now()

POST  /alerts/:id/feedback
  Body: { "feedback": "correct" | "false_positive" }
  → Sets parent_feedback, feeds model improvement loop
```

### 5.4 Preferences

```
GET   /children/:id/preferences     Get alert preferences
PUT   /children/:id/preferences     Replace preferences

Body:
{
  "disabled_categories": ["drugs_alcohol"],
  "immediate_severities": ["critical", "high"],
  "digest_frequency": "weekly"
}
```

### 5.5 Stats

```
GET /children/:id/stats?week=2026-06-02
Response:
{
  "week_start": "2026-06-02",
  "total_emails": 47,
  "emails_scanned": 47,
  "alerts_by_severity": { "critical": 0, "high": 1, "medium": 2, "low": 4 },
  "alerts_by_category": { "personal_info_sharing": 1, "bullying": 2 },
  "top_senders": [
    { "address": "teacher@school.edu", "count": 12 },
    { "address": "friend@gmail.com", "count": 8 }
  ]
}
```

---

## 6. Error Handling

All errors follow RFC 7807 Problem Details:

```json
{
  "type": "https://api.openbark.com/errors/token-expired",
  "title": "Gmail token expired",
  "status": 401,
  "detail": "The Gmail access token for this connection has expired. Please reconnect.",
  "connection_id": "uuid"
}
```

**Standard error codes:**

| HTTP | Code | Trigger |
|---|---|---|
| 400 | `validation-error` | Invalid request body |
| 401 | `unauthenticated` | Missing or invalid JWT |
| 401 | `gmail-token-expired` | OAuth token revoked/expired |
| 403 | `forbidden` | Parent accessing another parent's data |
| 404 | `not-found` | Resource not found |
| 409 | `already-connected` | Gmail already linked to a child |
| 429 | `rate-limited` | >100 API calls/min per parent |
| 500 | `internal-error` | Unexpected server failure |
| 502 | `upstream-error` | Google or Anthropic API failure |

---

## 7. Security

### 7.1 Authentication
- Passwords hashed with bcrypt (cost factor 12)
- JWT signed with RS256 private key (stored in AWS Secrets Manager)
- Refresh tokens stored as HttpOnly, Secure, SameSite=Strict cookies
- PKCE flow for OAuth (state parameter is HMAC-signed JWT)

### 7.2 Data Protection
- All columns containing tokens: encrypted at application layer (Fernet/AES) before write
- Encryption key rotation: supported via key versioning in AWS Secrets Manager
- No raw email body ever written to disk or database — processed in-memory only
- Database: TLS required for all connections, VPC-private (no public endpoint)
- All API traffic: TLS 1.3 minimum

### 7.3 Authorization
- Every DB query scoped to `parent_id` derived from JWT — no object-level auth bypass possible
- Child resources always validated: `child.parent_id == jwt.parent_id`
- Gmail tokens accessed only by backend services, never exposed in API responses

### 7.4 Rate Limiting
- API: 100 req/min per parent (Redis token bucket)
- Gmail API: respect 250 quota units/user/second; exponential backoff on 429
- Anthropic API: queue depth monitoring; circuit breaker if latency > 30s

### 7.5 COPPA Compliance
- No child account, login, or personal data collection from the child
- Parent is the sole account holder and data subject
- Data deletion: `DELETE /children/:id` hard-deletes all child data within 24h
- Retention: all alert/stats data auto-deleted after 12 months via nightly Celery task

---

## 8. Infrastructure

```
AWS Region: us-east-1 (primary), us-west-2 (DR — Phase 2)

ECS Fargate services:
  - api          (FastAPI, 2 tasks, 512MB/0.25vCPU each)
  - worker       (Celery, 2 tasks, 1GB/0.5vCPU each)
  - beat         (Celery Beat scheduler, 1 task)

RDS PostgreSQL 16:
  - Instance: db.t4g.small (beta), db.t4g.medium (launch)
  - Multi-AZ: disabled for beta, enabled at launch
  - Automated backups: 7-day retention

ElastiCache Redis 7:
  - cache.t4g.micro (beta)
  - Cluster mode: disabled for beta

Secrets Manager:
  - JWT private/public keypair
  - Fernet encryption key
  - Database credentials
  - Anthropic API key
  - SendGrid API key
  - FCM service account JSON

Load Balancer: ALB → HTTPS (ACM cert), HTTP → 443 redirect

S3:
  - openbark-static: dashboard frontend (CloudFront CDN)
  - openbark-logs: ALB access logs, application logs

CloudWatch:
  - Log groups per service
  - Alarms: API error rate > 1%, worker queue depth > 500, DB CPU > 80%
```

---

## 9. Monitoring & Observability

**Key metrics to instrument (CloudWatch custom metrics):**

| Metric | Alert threshold |
|---|---|
| `emails_ingested_total` | — (trend monitoring) |
| `analysis_queue_depth` | > 500 → page on-call |
| `analysis_latency_p95` | > 30s → page on-call |
| `alert_delivery_latency_p95` | > 5min → page on-call |
| `anthropic_api_errors` | > 5/min → circuit breaker |
| `gmail_token_errors` | > 10/min → alert |
| `false_positive_rate_7d` | > 15% → product review |

**Structured logging (every analysis):**
```json
{
  "event": "email_analyzed",
  "gmail_message_id": "...",
  "child_id": "...",
  "severity": "high",
  "category": "personal_info_sharing",
  "confidence": 0.92,
  "latency_ms": 1840,
  "model": "claude-sonnet-4-6"
}
```

---

## 10. Local Development Setup

```bash
# Prerequisites: Docker, Python 3.12, Node 20

git clone https://github.com/openbark/openbark
cd openbark

# Start dependencies
docker compose up -d postgres redis

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in ANTHROPIC_API_KEY, Google OAuth creds

alembic upgrade head           # run migrations
uvicorn app.main:app --reload  # API on :8000
celery -A app.worker worker -l info   # in separate terminal
celery -A app.worker beat -l info     # in separate terminal

# Frontend
cd ../frontend
npm install
npm run dev                    # dashboard on :3000
```

**`.env.example`:**
```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/openbark
REDIS_URL=redis://localhost:6379/0
JWT_PRIVATE_KEY_PATH=./keys/private.pem
JWT_PUBLIC_KEY_PATH=./keys/public.pem
FERNET_KEY=<generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/v1/auth/google/callback
ANTHROPIC_API_KEY=
SENDGRID_API_KEY=
FCM_SERVICE_ACCOUNT_JSON=
FRONTEND_URL=http://localhost:3000
```

---

## 11. Project Structure

```
openbark/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app init
│   │   ├── config.py               # Settings from env
│   │   ├── database.py             # SQLAlchemy async engine
│   │   ├── models/                 # SQLAlchemy ORM models
│   │   │   ├── parent.py
│   │   │   ├── child.py
│   │   │   ├── gmail_connection.py
│   │   │   ├── alert.py
│   │   │   └── alert_preference.py
│   │   ├── routers/                # FastAPI routers
│   │   │   ├── auth.py
│   │   │   ├── children.py
│   │   │   ├── alerts.py
│   │   │   ├── preferences.py
│   │   │   └── stats.py
│   │   ├── services/
│   │   │   ├── gmail.py            # Gmail API client
│   │   │   ├── analysis.py         # Claude classification
│   │   │   ├── notifications.py    # FCM + SendGrid
│   │   │   └── crypto.py           # Token encryption
│   │   ├── tasks/                  # Celery tasks
│   │   │   ├── ingestion.py
│   │   │   ├── analysis.py
│   │   │   └── digest.py
│   │   └── worker.py               # Celery app
│   ├── alembic/                    # DB migrations
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── AlertFeed.tsx
│   │   │   ├── AlertDetail.tsx
│   │   │   └── Settings.tsx
│   │   ├── components/
│   │   └── api/                    # API client (axios)
│   └── package.json
├── docker-compose.yml
├── PRD_email_monitoring.md
└── TECH_SPEC_email_monitoring.md
```

---

## 12. Open Technical Decisions

| Decision | Options | Recommendation |
|---|---|---|
| Gmail sync strategy | Polling (5min) vs. Push (Pub/Sub) | Start with polling — simpler, no GCP Pub/Sub setup. Migrate to Push after beta proves out. |
| LLM prompt strategy | Zero-shot vs. few-shot | Few-shot with 3-4 examples per category — improves precision measurably without fine-tuning cost |
| Token storage | App-layer encryption vs. AWS KMS envelope | App-layer Fernet for beta speed; migrate to KMS envelope encryption before launch |
| Queue | Redis list vs. SQS | Redis sufficient for beta; SQS for production (dead-letter queue, visibility timeout) |
| False positive handling | Auto-suppress low confidence | Suppress < 0.70 confidence; route 0.70–0.80 to internal review queue for first 500 alerts |
