# SafeMail — Claude Code Guide

## What this project is

SafeMail is an AI-powered email monitoring service for parents. It connects to a child's email account — Gmail, Outlook / Microsoft 365, or Apple iCloud (behind a provider-agnostic ingestion layer) — scans emails with Claude AI, and sends parents a smart alert only when something genuinely dangerous is detected. Raw email body text is never stored — only the AI-generated summary and metadata.

The six detection categories (enum values used throughout the code): `self_harm`, `grooming`, `bullying`, `drugs_alcohol`, `stranger_contact`, `personal_info_sharing`.

Access is **invite-only** (`INVITE_ONLY_ENABLED`): a public landing page captures a waitlist, and allowlisted emails can register directly. There's also a parent **admin** console and a **developer** console (LLM cost/usage stats).

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
│   ├── tests/
│   │   ├── conftest.py       Async test DB + client fixtures
│   │   ├── test_auth.py      Auth endpoint tests
│   │   ├── test_alerts.py    Alert endpoint tests
│   │   └── evaluation/       AI classifier effectiveness tests (41 fixtures)
│   ├── keys/                 JWT RSA keypair (gitignored)
│   ├── .env                  Local secrets (gitignored)
│   ├── .env.example          Template
│   ├── pytest.ini
│   └── requirements.txt
├── frontend/                 React 18 + TypeScript + Vite
│   └── src/
│       ├── api/              Axios API clients — client, auth, alerts, children,
│       │                       onboarding, waitlist, admin, developer
│       ├── components/       AlertBadge, NavBar
│       ├── pages/            Landing, Login, Onboarding, VerifyEmail, ForgotPassword,
│       │                       ResetPassword, Dashboard, AlertFeed, AlertDetail,
│       │                       Settings, Admin, Developer
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

# 3. Celery worker (polls Gmail every 5 min, runs AI, sends alerts)
cd backend && source .venv/bin/activate && celery -A app.worker worker -l info

# 4. Frontend (http://localhost:3000)
cd frontend && npm install && npm run dev
```

### Or with Docker Compose
```bash
docker compose up
```

## Running tests

```bash
cd backend && source .venv/bin/activate

# Unit + pipeline tests (no API key needed, ~5s)
pytest tests/evaluation/test_pipeline.py -v

# Auth + API tests (needs test DB)
docker exec -it <postgres-container> psql -U postgres -c "CREATE DATABASE safemail_test;"
pytest tests/test_auth.py tests/test_alerts.py -v

# Full AI accuracy suite (calls real Claude API, costs ~$0.20, takes ~2 min)
pytest tests/evaluation/test_classifier.py -v -s

# Precision/recall report only
pytest tests/evaluation/test_classifier.py::test_precision_recall_report -v -s
```

Quality gates: ≥ 85% recall, ≤ 15% false positive rate.

**E2E (Playwright):** browser smoke tests in `frontend/e2e/` drive the real app
against a running stack; state is created via a DEBUG-only seed router
(`app/routers/dev.py`, `/v1/dev/*`) gated behind `DEBUG=true` **and**
`E2E_SEED_ENABLED=true` + an `X-E2E-Seed-Secret` header — no OAuth/AI/email calls.
Run `cd frontend && npm run test:e2e` (full local recipe + isolated-ports note in
`docs/DEVELOPMENT.md`). CI runs it on every PR (the `e2e` job); the seam is never
mounted in prod (`tests/test_dev_seam.py` enforces this).

## Key environment variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection. Any scheme is auto-normalized to `postgresql+asyncpg://` in `config.py`. |
| `REDIS_URL` | Redis connection |
| `FERNET_KEY` | AES encryption key for OAuth tokens |
| `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` | RSA key **contents** (PEM, `\n`-escaped accepted). Preferred in prod; falls back to the `*_PATH` files when unset. |
| `JWT_PRIVATE_KEY_PATH` / `JWT_PUBLIC_KEY_PATH` | Paths to the RSA keypair (local-dev default) |
| `GOOGLE_CLIENT_ID` | Google OAuth app client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth app client secret |
| `GOOGLE_REDIRECT_URI` | Must match Google Console exactly |
| `ANTHROPIC_API_KEY` | Claude API key for email classification |
| `SENDGRID_API_KEY` | For alert and digest emails |
| `EMAIL_FROM` | From-address for all transactional email — must be a verified SendGrid sender |
| `FCM_SERVICE_ACCOUNT_JSON` | Firebase push notifications (optional) |
| `DEBUG` | `true` locally (enables `/docs`, relaxes validation); **`false` in production** |
| `COOKIE_SECURE` | `true` in production (HTTPS-only refresh cookie) |
| `FRONTEND_URL` | Base URL used to build links in transactional email (default `http://localhost:3000`) |
| `CONFIDENCE_THRESHOLD` | Min classifier confidence to alert (default `0.70`); below this is dropped |
| `MAX_BODY_LENGTH` | Email body truncation before analysis (default `8000`) |
| `ALERT_POLL_INTERVAL_MINUTES` | Gmail poll cadence (default `5`) |
| `CASCADE_ENABLED` | Gate the multi-model cost-saving cascade (default `false`) |
| `RATE_LIMIT_ENABLED` | Toggle auth rate limiting (default `true`) |
| `INVITE_ONLY_ENABLED` | Require allowlist/waitlist to register (default `true`) |
| `MONITORING_ENABLED` | Gate the scheduled self-monitoring cycle (default `true`) |
| `MONITORING_INTERVAL_MINUTES` | Health-probe cadence (default `10`) |
| `AUTO_REMEDIATION_ENABLED` | Let the remediation agent take bounded fix actions; off = diagnose-and-recommend only (default `false`) |
| `OPS_ALERT_EMAIL` | Destination for system-health alerts; falls back to all admin parents if unset |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | JWT lifetimes (default `15` / `30`) |
| `RUN_MIGRATIONS` | Set `true` on the API container only — its entrypoint runs `alembic upgrade head` (handled at the entrypoint, not in `config.py`) |

## Architecture decisions

- **Raw email body is never persisted.** It lives in memory and the Redis queue only. Only the AI summary, category, severity, and metadata are written to the DB.
- **Celery uses a sync SQLAlchemy engine.** FastAPI uses async (asyncpg). Both point at the same Postgres DB. Don't mix sessions between the two.
- **Confidence threshold is 0.70.** Emails classified below this are silently dropped. Tune via `CONFIDENCE_THRESHOLD` in config.
- **AI cost resilience (in `app/services/analysis.py`).** Prompt caching on the system prompt, retry with error discrimination, and an optional multi-model cascade gated behind `CASCADE_ENABLED` (default off — a cheaper model screens, escalating to a stronger one only when needed). Parent feedback on alerts feeds back into reporting (`WeeklyStats`, developer console).
- **Invite-only access (`INVITE_ONLY_ENABLED`, default on).** Non-allowlisted signups land on a waitlist; allowlisted emails (`AllowedEmail`) register directly. See `app/services/allowlist.py` and the `waitlist`/`onboarding` routers.
- **Gmail polling is every 5 minutes.** Redis dedup set (7-day TTL) prevents the same message being analyzed twice.
- **OAuth tokens are Fernet-encrypted** before writing to the DB. Never log or return them in API responses.
- **JWT uses RS256** (asymmetric). Private key signs, public key verifies. Locally from `backend/keys/`; in production from the `JWT_PRIVATE_KEY`/`JWT_PUBLIC_KEY` env vars (no secret-file mount required).
- **First-party analytics (`app/services/analytics_events.py`, always on).** A privacy-respecting, in-house product-analytics suite for the user funnel — no third-party SaaS, no cookies, no PII (consistent with the "raw email body never stored" posture). Anonymous client events (`page_viewed`, onboarding-step drop-offs, CTA clicks) post to the public `POST /v1/analytics/collect` (validated against an event allowlist); authoritative server-side conversion events (`waitlist_joined`, `account_registered`, `email_verified`, `gmail_connected`, `onboarding_completed`, `alert_feedback_given`, `account_deleted`, …) are emitted from the routers via `record_event_async`. `analytics_events.parent_id` is `ON DELETE CASCADE` so a user's events are erased with their account (right-to-erasure). The admin **Analytics** tab (`pages/Admin.tsx`) shows the AARRR funnel with per-stage conversion + drop-off, time-to-value, and event/page/referrer breakdowns (`GET /v1/analytics/{overview,funnel,events}`, admin-gated). The activation funnel is computed from existing Parent/Child/GmailConnection/Alert timestamps, so it's accurate for existing users without backfill. The client tracker (`frontend/src/analytics.ts`) respects Do-Not-Track / Global Privacy Control. Full design + research: `docs/analytics-spec.md`.
- **Agentic self-monitoring (`MONITORING_ENABLED`, default on).** A Celery beat task (`app/tasks/monitoring.py::run_monitoring_cycle`, every `MONITORING_INTERVAL_MINUTES`) runs health probes (`app/services/monitoring.py`: Redis, Celery queue backlog, Gmail-poll liveness/staleness, task failure rate, terminal Claude API errors, connections in error). A new problem opens a `HealthIncident` (deduped by `fingerprint`), is handed to an LLM remediation agent (`app/services/remediation.py` — a Claude tool-use loop with read-only investigation tools plus an allowlist of bounded, idempotent fix actions gated behind `AUTO_REMEDIATION_ENABLED`), and emails ops (`send_health_alert`). Re-trips bump `times_seen`; incidents auto-resolve when their probe stops firing. Admin-only console at `/monitoring` (router `app/routers/monitoring.py`, page `frontend/src/pages/Monitoring.tsx`).
- **Production hardening (active when `DEBUG=false`).** Rate limiting on auth endpoints (`app/ratelimit.py`), refresh-token revocation via a Redis denylist (`app/services/token_denylist.py`), security-headers middleware + tight CORS, password-strength validation, generic 500 bodies (full traceback logged server-side), `/docs` disabled, and startup validation that required secrets are set.

## Deployment

Portable Docker stack configured entirely via env vars — runs on any Docker host or PaaS.

- **Canonical artifact:** `docker-compose.prod.yml` (six services: postgres, redis, api, worker, beat, frontend). The frontend is an nginx container that serves the SPA and reverse-proxies `/v1` to the API (same-origin → refresh cookie works, no CORS). nginx re-resolves the API upstream per request (`resolver` + variable `proxy_pass`) so it survives backend redeploys.
- **Backend image** (`backend/Dockerfile`): non-root, `entrypoint.sh` runs migrations when `RUN_MIGRATIONS=true`, uvicorn binds `--host ::` (IPv6 dual-stack, required for Railway private networking).
- **Railway (current deploy):** see `docs/DEPLOY-railway.md`; per-service manifests in `backend/railway.json` + `frontend/railway.json`. Each service needs its Root Directory set (`backend` or `frontend`).
- **Env contract:** `.env.production.example`.

## API base URL

`http://localhost:8000/v1` — Swagger UI at `http://localhost:8000/docs`

## DB migrations

```bash
# Create a new migration after changing models
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

## Inbound email providers

Inbound monitoring is provider-agnostic behind a Strategy interface in
`app/services/email_providers/` (`base.py` defines `EmailProvider`; `gmail.py` =
Google/OAuth, `microsoft.py` = Outlook/Microsoft 365 over OAuth + Graph,
`apple.py` = Apple/iCloud over IMAP; `__init__.py` exposes `get_provider(name)`).
The ingestion loop (`app/tasks/ingestion.py`) dispatches through
`get_provider(conn.provider)`; the connection row carries a `provider` column
(default `"google"`).

Two auth models (`provider.auth_kind`): **oauth** (Gmail + Microsoft — generic
routes `GET /auth/oauth/{provider}/connect|callback`; `/auth/google/*` kept as
aliases; per-provider redirect URIs in config; the OAuth state token carries the
`provider`) and **credentials** (Apple — the parent supplies the iCloud address +
an app-specific password to `POST /auth/email/connect`; the password is stored
Fernet-encrypted, IMAP is read-only via EXAMINE + BODY.PEEK). The frontend connect
step (Onboarding + Settings) has a provider picker. Microsoft needs a Microsoft
Entra (Azure) app — `MICROSOFT_CLIENT_ID/SECRET/REDIRECT_URI` (optional; connect
errors clearly if unset).

**Note:** the table/columns/`message_data` keys still use the legacy `gmail_*`
names (e.g. `gmail_connections.gmail_address`, `gmail_message_id`) — a deliberate
deferral; they're just identifiers. A provider-neutral rename is future cleanup.

### Adding an email provider
1. Implement `EmailProvider` in `app/services/email_providers/<name>.py` — set
   `auth_kind`, implement the connect method for that kind (OAuth or
   `connect_with_credentials`) + the ingestion methods. `extract_message_data` MUST
   return the canonical dict shape.
2. Register it in `app/services/email_providers/__init__.py` `_PROVIDERS`. For an
   **OAuth** provider also add an `oauth_redirect_uri()` + its `*_redirect_uri`
   setting — the generic `/auth/oauth/{provider}/connect|callback` routes then work
   with no new route code (they resolve via the registry).
3. Wire the connect UI (reuse `/auth/email/connect` for credentials providers; OAuth
   providers use the generic route) and add it to the frontend provider picker.

## Adding a new detection category

1. Add the category string to `SYSTEM_PROMPT` in `backend/app/services/analysis.py`
2. Add severity guidance to `CATEGORY_SEVERITY_GUIDE` in the same file
3. Add fixtures to `backend/tests/evaluation/fixtures.py`
4. Add the type to `Category` in `frontend/src/types/index.ts`
5. Add a label to `CATEGORY_LABELS` in `backend/app/services/notifications.py`
