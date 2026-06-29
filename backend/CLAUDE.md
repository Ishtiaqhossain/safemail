# SafeMail backend — Claude Code Guide

Applies to everything under `backend/`. See the **root `CLAUDE.md`** for the project
overview, how to run the full stack, architecture decisions, and deployment.

**Backend invariants** (the most important, repeated from root because they're easy
to get wrong here):
- **Never persist raw email body.** Only the AI summary + metadata are written to the DB.
- **Two SQLAlchemy engines:** FastAPI uses **async** (asyncpg) via `get_db`; Celery uses
  a **sync** engine (`SyncSessionLocal`). Don't mix sessions across the two.
- **OAuth tokens / IMAP app-passwords are Fernet-encrypted** (`app/services/crypto.py`)
  before storage; never log or return them.

## Running tests

```bash
cd backend && source .venv/bin/activate

# Unit + pipeline tests (no API key needed, ~5s)
pytest tests/evaluation/test_pipeline.py -v

# Auth + API tests (needs test DB)
docker exec -it <postgres-container> psql -U postgres -c "CREATE DATABASE safemail_test;"
pytest tests/test_auth.py tests/test_alerts.py tests/test_waitlist.py -v

# Full AI accuracy suite (calls real Claude API, costs ~$0.20, takes ~2 min)
pytest tests/evaluation/test_classifier.py -v -s

# Precision/recall report only
pytest tests/evaluation/test_classifier.py::test_precision_recall_report -v -s
```

Quality gates: ≥ 85% recall, ≤ 15% false positive rate. CI runs the non-paid suite
(everything except `test_classifier.py`); the paid eval is `classifier-eval.yml`
(manual). When you add a new test file, add it to the `backend` job's pytest list in
`.github/workflows/ci.yml` (CI enumerates files, it doesn't run the whole dir).

## Key environment variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection. Any scheme is auto-normalized to `postgresql+asyncpg://` in `config.py`. |
| `REDIS_URL` | Redis connection |
| `FERNET_KEY` | AES encryption key for OAuth tokens / IMAP app-passwords |
| `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` | RSA key **contents** (PEM, `\n`-escaped accepted). Preferred in prod; falls back to the `*_PATH` files when unset. |
| `JWT_PRIVATE_KEY_PATH` / `JWT_PUBLIC_KEY_PATH` | Paths to the RSA keypair (local-dev default) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | Google OAuth app (redirect must match the Google Console value exactly) |
| `MICROSOFT_CLIENT_ID` / `MICROSOFT_CLIENT_SECRET` / `MICROSOFT_REDIRECT_URI` | Microsoft Entra (Azure) app — optional; Outlook connect errors clearly if unset |
| `ANTHROPIC_API_KEY` | Claude API key for email classification |
| `SENDGRID_API_KEY` | For alert and digest emails |
| `EMAIL_FROM` | From-address for all transactional email — must be a verified SendGrid sender |
| `TRANSACTIONAL_EMAIL_ENABLED` | When `false`, all outbound email (verification/reset/alerts/digest/reconnect/health/waitlist) is skipped (default `true`; off in E2E/CI) |
| `FCM_SERVICE_ACCOUNT_JSON` | Firebase push notifications (optional) |
| `DEBUG` | `true` locally (enables `/docs`, relaxes validation); **`false` in production** |
| `COOKIE_SECURE` | `true` in production (HTTPS-only refresh cookie) |
| `FRONTEND_URL` | Base URL used to build links in transactional email (default `http://localhost:3000`) |
| `CONFIDENCE_THRESHOLD` | Min classifier confidence to alert (default `0.70`); below this is dropped |
| `MAX_BODY_LENGTH` | Email body truncation before analysis (default `8000`) |
| `ALERT_POLL_INTERVAL_MINUTES` | Mailbox poll cadence (default `5`) |
| `CASCADE_ENABLED` | Gate the multi-model cost-saving cascade (default `false`) |
| `RATE_LIMIT_ENABLED` | Toggle auth rate limiting (default `true`) |
| `INVITE_ONLY_ENABLED` | Require allowlist/waitlist to register (default `true`) |
| `MONITORING_ENABLED` / `MONITORING_INTERVAL_MINUTES` | Scheduled self-monitoring cycle (default `true` / `10`) |
| `AUTO_REMEDIATION_ENABLED` | Let the remediation agent take bounded fix actions; off = diagnose-and-recommend only (default `false`) |
| `OPS_ALERT_EMAIL` | Destination for system-health + new-waitlist-signup alerts; falls back to all admin parents if unset |
| `E2E_SEED_ENABLED` / `E2E_SEED_SECRET` | Mount the `/v1/dev/*` E2E seed router (only with `DEBUG=true` too) + its required header secret. **Never set in prod.** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | JWT lifetimes (default `15` / `30`) |
| `RUN_MIGRATIONS` | Set `true` on the API container only — its entrypoint runs `alembic upgrade head` (handled at the entrypoint, not in `config.py`) |

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
Fernet-encrypted, IMAP is read-only via EXAMINE + BODY.PEEK).

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
3. Wire the connect UI (frontend) — see `frontend/CLAUDE.md`.

## Adding a new detection category

1. Add the category string to `SYSTEM_PROMPT` in `app/services/analysis.py`
2. Add severity guidance to `CATEGORY_SEVERITY_GUIDE` in the same file
3. Add fixtures to `tests/evaluation/fixtures.py`
4. Add the type to `Category` in `frontend/src/types/index.ts`
5. Add a label to `CATEGORY_LABELS` in `app/services/notifications.py`

## E2E seed seam (`app/routers/dev.py`)

DEBUG-only `/v1/dev/*` endpoints used by the frontend E2E suite to create state
without OAuth/AI/email. Mounted only when `DEBUG=true` **and** `E2E_SEED_ENABLED=true`,
and every request needs the `X-E2E-Seed-Secret` header. Never reachable in prod —
`tests/test_dev_seam.py` enforces that in clean subprocesses. (Frontend usage:
`frontend/CLAUDE.md`.)
