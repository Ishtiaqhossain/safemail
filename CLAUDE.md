# SafeMail — Claude Code Guide

## What this project is

SafeMail is an AI-powered email monitoring service for parents. It connects to a child's email account — Gmail, Outlook / Microsoft 365, or Apple iCloud (behind a provider-agnostic ingestion layer) — scans emails with Claude AI, and sends parents a smart alert only when something genuinely dangerous is detected. Raw email body text is never stored — only the AI-generated summary and metadata.

The six detection categories (enum values used throughout the code): `self_harm`, `grooming`, `bullying`, `drugs_alcohol`, `stranger_contact`, `personal_info_sharing`.

Access is **invite-only** (`INVITE_ONLY_ENABLED`): a public landing page captures a waitlist, and allowlisted emails can register directly. There's also a parent **admin** console and a **developer** console (LLM cost/usage stats).

> **Subtree guides** (these load automatically when you touch files under them):
> - **`backend/CLAUDE.md`** — FastAPI/Celery internals, the env-var reference, the email-provider abstraction, DB migrations, and backend tests.
> - **`frontend/CLAUDE.md`** — React/Vite conventions, the auth client model, and the Playwright E2E suite.
>
> This root file is the overview + cross-cutting context (architecture, how to run, deploy). Keep shared rules here; keep subtree-specific detail in the files above (don't duplicate).

## Repo structure

```
safemail/
├── backend/                  Python/FastAPI backend
│   ├── app/
│   │   ├── main.py           FastAPI app entry point
│   │   ├── config.py         Settings (pydantic-settings, reads .env)
│   │   ├── database.py       SQLAlchemy async engine (FastAPI) + sync engine (Celery)
│   │   ├── auth.py           JWT helpers, bcrypt, get_current_parent dependency
│   │   ├── models/           SQLAlchemy ORM — Parent, Child, GmailConnection, Alert, AlertPreference,
│   │   │                       AllowedEmail, WaitlistEntry, TaskLog, WeeklyStats
│   │   ├── schemas/          Pydantic request/response models
│   │   ├── routers/          FastAPI routers — auth, children, alerts, preferences, stats,
│   │   │                       onboarding, waitlist, admin, developer
│   │   ├── services/         Business logic — gmail, analysis, notifications, crypto,
│   │   │                       allowlist, token_denylist
│   │   ├── tasks/            Celery tasks — ingestion.py, analysis.py, digest.py, utils.py
│   │   ├── ratelimit.py      Auth-endpoint rate limiting (active when DEBUG=false)
│   │   └── worker.py         Celery app + beat schedule
│   ├── alembic/              DB migrations
│   ├── tests/                pytest (see backend/CLAUDE.md)
│   ├── keys/                 JWT RSA keypair (gitignored)
│   ├── .env / .env.example   Local secrets (gitignored) + template
│   └── requirements.txt
├── frontend/                 React 18 + TypeScript + Vite
│   └── src/
│       ├── api/              Axios API clients — client, auth, alerts, children,
│       │                       onboarding, waitlist, admin, developer
│       ├── components/       AlertBadge, NavBar
│       ├── pages/            Landing, Login, Onboarding, VerifyEmail, ForgotPassword,
│       │                       ResetPassword, Dashboard, AlertFeed, AlertDetail,
│       │                       Settings, Admin, Developer, Monitoring
│       ├── e2e/              Playwright browser tests (see frontend/CLAUDE.md)
│       └── types/            Shared TypeScript types
├── docker-compose.yml        Local dev: Postgres + Redis + API + worker + beat
├── docker-compose.prod.yml   Production stack (adds frontend; no bind mounts/reload)
├── .env.production.example   Production env contract
├── docs/
│   ├── DEVELOPMENT.md         Dev setup, env vars, tests, deploy (developer-facing)
│   └── DEPLOY-railway.md      Step-by-step Railway deploy guide
├── PRD_email_monitoring.md   Product requirements
└── TECH_SPEC_email_monitoring.md  Technical specification
```

## How to run locally

### Prerequisites
```bash
# All must be installed
python3.12 --version
node --version      # 20+
docker --version
```

### First-time setup
```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Generate JWT keys
mkdir -p keys
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -pubout -out keys/public.pem

# Generate Fernet key and add to .env
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

cp .env.example .env  # then fill in all values
```

### Start everything (4 terminals)
```bash
# 1. Databases
docker compose up postgres redis

# 2. API (http://localhost:8000, docs at /docs)
cd backend && source .venv/bin/activate && alembic upgrade head && uvicorn app.main:app --reload

# 3. Celery worker (polls mailboxes every 5 min, runs AI, sends alerts)
cd backend && source .venv/bin/activate && celery -A app.worker worker -l info

# 4. Frontend (http://localhost:3000)
cd frontend && npm install && npm run dev
```

### Or with Docker Compose
```bash
docker compose up
```

## Testing

- **Backend** (pytest) and the **AI accuracy / quality gates** — see **`backend/CLAUDE.md`**.
  Quality gates: ≥ 85% recall, ≤ 15% false positive rate.
- **Frontend** (Playwright browser E2E) — see **`frontend/CLAUDE.md`**.
- CI (`.github/workflows/ci.yml`) runs three jobs on every PR: backend pytest, frontend `tsc`, and the E2E suite.

## Architecture decisions

- **Raw email body is never persisted.** It lives in memory and the Redis queue only. Only the AI summary, category, severity, and metadata are written to the DB.
- **Celery uses a sync SQLAlchemy engine.** FastAPI uses async (asyncpg). Both point at the same Postgres DB. Don't mix sessions between the two.
- **Provider-agnostic ingestion.** Gmail (OAuth), Microsoft 365 (OAuth + Graph), and Apple iCloud (IMAP) sit behind a Strategy interface — see `backend/CLAUDE.md` ("Inbound email providers").
- **Confidence threshold is 0.70.** Emails classified below this are silently dropped. Tune via `CONFIDENCE_THRESHOLD`.
- **AI cost resilience (in `app/services/analysis.py`).** Prompt caching on the system prompt, retry with error discrimination, and an optional multi-model cascade gated behind `CASCADE_ENABLED` (default off — a cheaper model screens, escalating to a stronger one only when needed). Parent feedback on alerts feeds back into reporting (`WeeklyStats`, developer console).
- **Invite-only access (`INVITE_ONLY_ENABLED`, default on).** Non-allowlisted signups land on a waitlist; allowlisted emails (`AllowedEmail`) register directly. See `app/services/allowlist.py` and the `waitlist`/`onboarding` routers. A new waitlist signup emails ops (`OPS_ALERT_EMAIL`, else admin parents).
- **Mailbox polling is every 5 minutes.** Redis dedup set (7-day TTL) prevents the same message being analyzed twice.
- **OAuth tokens / IMAP app-passwords are Fernet-encrypted** before writing to the DB. Never log or return them in API responses.
- **JWT uses RS256** (asymmetric). Private key signs, public key verifies. Locally from `backend/keys/`; in production from the `JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY` env vars (no secret-file mount required).
- **First-party analytics (`app/services/analytics_events.py`, always on).** A privacy-respecting, in-house product-analytics suite for the user funnel — no third-party SaaS, no cookies, no PII (consistent with the "raw email body never stored" posture). Anonymous client events (`page_viewed`, onboarding-step drop-offs, CTA clicks) post to the public `POST /v1/analytics/collect` (validated against an event allowlist); authoritative server-side conversion events (`waitlist_joined`, `account_registered`, `email_verified`, `gmail_connected`, `onboarding_completed`, `alert_feedback_given`, `account_deleted`, …) are emitted from the routers via `record_event_async`. `analytics_events.parent_id` is `ON DELETE CASCADE` so a user's events are erased with their account (right-to-erasure). The admin **Analytics** tab (`pages/Admin.tsx`) shows the AARRR funnel with per-stage conversion + drop-off, time-to-value, and event/page/referrer breakdowns (`GET /v1/analytics/{overview,funnel,events}`, admin-gated). The client tracker (`frontend/src/analytics.ts`) respects Do-Not-Track / Global Privacy Control. Full design: `docs/analytics-spec.md`.
- **Agentic self-monitoring (`MONITORING_ENABLED`, default on).** A Celery beat task (`app/tasks/monitoring.py::run_monitoring_cycle`, every `MONITORING_INTERVAL_MINUTES`) runs health probes (`app/services/monitoring.py`: Redis, Celery queue backlog, poll liveness/staleness, task failure rate, terminal Claude API errors, connections in error). A new problem opens a `HealthIncident` (deduped by `fingerprint`), is handed to an LLM remediation agent (`app/services/remediation.py` — a Claude tool-use loop with read-only investigation tools plus an allowlist of bounded, idempotent fix actions gated behind `AUTO_REMEDIATION_ENABLED`), and emails ops (`send_health_alert`). Re-trips bump `times_seen`; incidents auto-resolve when their probe stops firing. Admin-only console at `/monitoring`.
- **Production hardening (active when `DEBUG=false`).** Rate limiting on auth endpoints (`app/ratelimit.py`), refresh-token revocation via a Redis denylist (`app/services/token_denylist.py`), security-headers middleware + tight CORS, password-strength validation, generic 500 bodies (full traceback logged server-side), `/docs` disabled, and startup validation that required secrets are set.

## Deployment

Portable Docker stack configured entirely via env vars — runs on any Docker host or PaaS.

- **Canonical artifact:** `docker-compose.prod.yml` (six services: postgres, redis, api, worker, beat, frontend). The frontend is an nginx container that serves the SPA and reverse-proxies `/v1` to the API (same-origin → refresh cookie works, no CORS). nginx re-resolves the API upstream per request (`resolver` + variable `proxy_pass`) so it survives backend redeploys.
- **Backend image** (`backend/Dockerfile`): non-root, `entrypoint.sh` runs migrations when `RUN_MIGRATIONS=true`, uvicorn binds `--host ::` (IPv6 dual-stack, required for Railway private networking).
- **Railway (current deploy):** see `docs/DEPLOY-railway.md`; per-service manifests in `backend/railway.json` + `frontend/railway.json`. Each service needs its Root Directory set (`backend` or `frontend`).
- **Env contract:** `.env.production.example`. Full variable reference: `backend/CLAUDE.md`.

## API base URL

`http://localhost:8000/v1` — Swagger UI at `http://localhost:8000/docs`
