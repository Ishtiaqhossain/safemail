# SafeMail — Claude Code Guide

## What this project is

SafeMail is an AI-powered email monitoring service for parents. It connects to a child's Gmail account, scans emails with Claude AI, and sends parents a smart alert only when something genuinely dangerous is detected (self-harm, grooming, bullying, drugs, stranger contact, personal info sharing). Raw email body text is never stored — only the AI-generated summary and metadata.

## Repo structure

```
safemail/
├── backend/                  Python/FastAPI backend
│   ├── app/
│   │   ├── main.py           FastAPI app entry point
│   │   ├── config.py         Settings (pydantic-settings, reads .env)
│   │   ├── database.py       SQLAlchemy async engine (FastAPI) + sync engine (Celery)
│   │   ├── auth.py           JWT helpers, bcrypt, get_current_parent dependency
│   │   ├── models/           SQLAlchemy ORM models (Parent, Child, GmailConnection, Alert, ...)
│   │   ├── schemas/          Pydantic request/response models
│   │   ├── routers/          FastAPI routers — auth, children, alerts, preferences, stats
│   │   ├── services/         Business logic — gmail.py, analysis.py, notifications.py, crypto.py
│   │   ├── tasks/            Celery tasks — ingestion.py, analysis.py, digest.py
│   │   └── worker.py         Celery app + beat schedule
│   ├── alembic/              DB migrations
│   ├── tests/
│   │   ├── conftest.py       Async test DB + client fixtures
│   │   ├── test_auth.py      Auth endpoint tests
│   │   ├── test_alerts.py    Alert endpoint tests
│   │   └── evaluation/       AI classifier effectiveness tests (46 fixtures)
│   ├── keys/                 JWT RSA keypair (gitignored)
│   ├── .env                  Local secrets (gitignored)
│   ├── .env.example          Template
│   ├── pytest.ini
│   └── requirements.txt
├── frontend/                 React 18 + TypeScript + Vite
│   └── src/
│       ├── api/              Axios API clients (alerts.ts, children.ts, client.ts)
│       ├── components/       AlertBadge, NavBar
│       ├── pages/            Login, Dashboard, AlertFeed, AlertDetail, Settings
│       └── types/            Shared TypeScript types
├── docker-compose.yml        Postgres + Redis + API + worker + beat
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
| `DATABASE_URL` | PostgreSQL connection (asyncpg format) |
| `REDIS_URL` | Redis connection |
| `FERNET_KEY` | AES encryption key for OAuth tokens |
| `JWT_PRIVATE_KEY_PATH` | Path to RSA private key |
| `JWT_PUBLIC_KEY_PATH` | Path to RSA public key |
| `GOOGLE_CLIENT_ID` | Google OAuth app client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth app client secret |
| `GOOGLE_REDIRECT_URI` | Must match Google Console exactly |
| `ANTHROPIC_API_KEY` | Claude API key for email classification |
| `SENDGRID_API_KEY` | For alert and digest emails |
| `FCM_SERVICE_ACCOUNT_JSON` | Firebase push notifications (optional) |

## Architecture decisions

- **Raw email body is never persisted.** It lives in memory and the Redis queue only. Only the AI summary, category, severity, and metadata are written to the DB.
- **Celery uses a sync SQLAlchemy engine.** FastAPI uses async (asyncpg). Both point at the same Postgres DB. Don't mix sessions between the two.
- **Confidence threshold is 0.70.** Emails classified below this are silently dropped. Tune via `CONFIDENCE_THRESHOLD` in config.
- **Gmail polling is every 5 minutes.** Redis dedup set (7-day TTL) prevents the same message being analyzed twice.
- **OAuth tokens are Fernet-encrypted** before writing to the DB. Never log or return them in API responses.
- **JWT uses RS256** (asymmetric). Private key signs, public key verifies. Both stored in `backend/keys/`.

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
