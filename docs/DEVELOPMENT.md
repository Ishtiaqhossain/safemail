# Development Guide

Everything you need to run, test, and deploy SafeMail. For a product overview, see the [README](../README.md).

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy · Alembic |
| Workers | Celery · Redis |
| Database | PostgreSQL |
| AI | Anthropic Claude API |
| Frontend | React 18 · TypeScript · Vite |
| Auth | JWT RS256 · bcrypt |
| Encryption | Fernet (OAuth tokens at rest) |
| Notifications | SendGrid · Firebase FCM |

## Quick Start

### Prerequisites

```bash
python3.12 --version
node --version      # 20+
docker --version
```

### First-time setup

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Generate JWT keypair
mkdir -p keys
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -pubout -out keys/public.pem

# Generate Fernet encryption key — copy output to .env as FERNET_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

cp .env.example .env   # fill in all values
```

### Run locally (4 terminals)

```bash
# 1. Databases
docker compose up postgres redis

# 2. API  →  http://localhost:8000  (Swagger: /docs)
cd backend && source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --reload

# 3. Celery worker (polls Gmail every 5 min, runs AI, sends alerts)
cd backend && source .venv/bin/activate
celery -A app.worker worker -l info

# 4. Frontend  →  http://localhost:3000
cd frontend && npm install && npm run dev
```

Or start everything at once:

```bash
docker compose up
```

## API

Base URL: `http://localhost:8000/v1`
Swagger UI: `http://localhost:8000/docs`

## Environment Variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection. Any scheme (`postgres://`, `postgresql://`, `postgresql+asyncpg://`) is auto-normalized to asyncpg. |
| `REDIS_URL` | Redis connection |
| `FERNET_KEY` | AES encryption key for OAuth tokens |
| `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` | RSA key **contents** (PEM, `\n`-escaped OK). Used in production instead of files — no secret-file mount needed. |
| `JWT_PRIVATE_KEY_PATH` / `JWT_PUBLIC_KEY_PATH` | Paths to the RSA keypair (local-dev fallback when the above aren't set) |
| `GOOGLE_CLIENT_ID` | Google OAuth app client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth app client secret |
| `GOOGLE_REDIRECT_URI` | Must match Google Console exactly |
| `ANTHROPIC_API_KEY` | Claude API key for email classification |
| `SENDGRID_API_KEY` | For alert and digest emails |
| `EMAIL_FROM` | From-address for transactional email — must be a verified SendGrid sender |
| `FCM_SERVICE_ACCOUNT_JSON` | Firebase push notifications (optional) |
| `DEBUG` | `true` locally (enables `/docs`, relaxes secret validation). **Must be `false` in production.** |
| `COOKIE_SECURE` | `true` in production so the refresh cookie is HTTPS-only |

See `.env.example` (local) and `.env.production.example` (production contract) for full templates.

## Running Tests

```bash
cd backend && source .venv/bin/activate

# Unit + pipeline tests (~5s, no API key needed)
pytest tests/evaluation/test_pipeline.py -v

# Auth + API tests (requires test database)
pytest tests/test_auth.py tests/test_alerts.py -v

# Full AI accuracy suite (calls real Claude API, ~$0.20, ~2 min)
pytest tests/evaluation/test_classifier.py -v -s

# Precision/recall report only
pytest tests/evaluation/test_classifier.py::test_precision_recall_report -v -s
```

Quality gates: ≥ 85% recall · ≤ 15% false positive rate.

## DB Migrations

```bash
# After changing a model
alembic revision --autogenerate -m "description"
alembic upgrade head

# Roll back one step
alembic downgrade -1
```

## Deployment

The whole stack is packaged as portable Docker images configured purely through environment variables, so it runs on any Docker host or managed PaaS.

```bash
# Full production stack on any Docker host (VPS, etc.)
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

This brings up six services — Postgres, Redis, the API, a Celery worker, Celery beat, and the frontend (nginx serving the SPA and reverse-proxying `/v1` to the API, same-origin). The API container applies migrations on start (`RUN_MIGRATIONS=true`).

- **Managed PaaS (Railway):** step-by-step guide in [`DEPLOY-railway.md`](DEPLOY-railway.md). Thin per-service manifests live in `backend/railway.json` and `frontend/railway.json`.
- **Config contract:** every required production variable is listed in `.env.production.example`.
- Production hardening (all on by default when `DEBUG=false`): rate limiting on auth endpoints, refresh-token revocation, security headers, password-strength rules, generic 500s with server-side logging, and fail-fast validation of required secrets.

## Architecture Notes

- **No raw email storage.** Email bodies live in memory and the Redis queue only; only the AI summary and metadata reach Postgres.
- **Celery uses a sync SQLAlchemy engine.** FastAPI uses async (asyncpg). Both point at the same database — don't mix sessions between the two.
- **Gmail polling every 5 minutes.** A Redis dedup set (7-day TTL) prevents the same message being analyzed twice.
- **JWT uses RS256** (asymmetric). Private key signs, public key verifies. Both live in `backend/keys/` (gitignored).
