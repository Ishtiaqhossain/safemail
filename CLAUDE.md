# SafeMail — Claude Code Guide

## What this project is

SafeMail is an AI-powered email monitoring service for parents. It connects to a child's Gmail account, scans emails with Claude AI, and sends parents a smart alert only when something genuinely dangerous is detected. Raw email body text is never stored — only the AI-generated summary and metadata.

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

## Adding a new detection category

1. Add the category string to `SYSTEM_PROMPT` in `backend/app/services/analysis.py`
2. Add severity guidance to `CATEGORY_SEVERITY_GUIDE` in the same file
3. Add fixtures to `backend/tests/evaluation/fixtures.py`
4. Add the type to `Category` in `frontend/src/types/index.ts`
5. Add a label to `CATEGORY_LABELS` in `backend/app/services/notifications.py`
