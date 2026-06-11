# Deploying SafeMail to Railway

This deploys the **same Docker images** verified by `docker-compose.prod.yml` —
Railway is just a thin layer over them. Nothing here is Railway-specific in the
app code; if you ever leave Railway, the compose stack still runs anywhere.

The stack is **four app services** (api, worker, beat, frontend) plus Railway's
**managed Postgres and Redis**. `backend/railway.json` and `frontend/railway.json`
pin the Docker builder; per-service settings below are set in the dashboard
because the three backend services share one directory.

---

## 0. Prerequisites
- A Railway account + a new **Project** (`railway init` or the dashboard).
- This repo connected to the project (GitHub integration).
- Fresh production secrets (do **not** reuse local-dev values). See
  `.env.production.example` for the full list.

## 1. Add managed datastores
In the project: **New → Database → PostgreSQL**, then again **→ Redis**.
Railway exposes connection variables you'll reference below
(`${{Postgres.DATABASE_URL}}`, `${{Redis.REDIS_URL}}`).

## 2. Shared variables (set once at the project level)
Project → **Variables** → add the secrets every backend service needs. Using
shared/reference variables means you set them once:

```
DEBUG=false
COOKIE_SECURE=true
INVITE_ONLY_ENABLED=true
FERNET_KEY=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
ANTHROPIC_API_KEY=...
SENDGRID_API_KEY=...
JWT_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----
JWT_PUBLIC_KEY=-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----
```

Notes:
- **JWT keys**: paste the PEM **contents** with `\n` for newlines (the app
  restores them). Generate with
  `openssl genrsa -out private.pem 2048 && openssl rsa -in private.pem -pubout -out public.pem`.
- `DATABASE_URL` / `REDIS_URL` are set **per backend service** in step 3 as
  references (so they resolve to the managed add-ons).

## 3. Create the backend services (api, worker, beat)
Create three services from the repo, each with **Root Directory = `backend`**
(they all use `backend/Dockerfile` via `backend/railway.json`). They differ only
in start command and a couple of vars:

| Service | Custom Start Command | Extra variables |
|---|---|---|
| **api** | *(leave default — uses the Dockerfile entrypoint)* | `RUN_MIGRATIONS=true` |
| **worker** | `celery -A app.worker worker -l info -c 4` | — |
| **beat** | `celery -A app.worker beat -l info` | — |

For **every** backend service, add these reference variables:
```
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
```
(The app normalizes the `postgres://` scheme to asyncpg automatically.)

Why these settings:
- Only **api** sets `RUN_MIGRATIONS=true`, so its entrypoint runs
  `alembic upgrade head` once on deploy; worker/beat skip it (no migration race).
- **api** keeps the default start command so the entrypoint (migrations) runs;
  worker/beat override it with their Celery commands.
- **api**: set **Health Check Path** = `/health` in its service settings.
- The api listens on Railway's `$PORT` automatically (Dockerfile `CMD`).

## 4. Create the frontend service
New service, **Root Directory = `frontend`** (uses `frontend/Dockerfile` +
`frontend/railway.json`, health check `/`). It serves the SPA and reverse-proxies
`/v1` to the API so everything is **same-origin** (the `SameSite=Strict` refresh
cookie works, no CORS).

Set on the frontend service:
```
API_UPSTREAM=${{api.RAILWAY_PRIVATE_DOMAIN}}:8000
```
This points nginx at the api over Railway's private network. (Pin the api to a
fixed internal port by setting `PORT=8000` on the **api** service so the upstream
address is stable.)

> nginx resolves the api hostname when it starts, so if the frontend boots
> before the api is reachable it may crash once and restart. That's expected —
> the `ON_FAILURE` restart policy recovers it automatically once the api is up.
> Deploy the api first to avoid the extra restart.

## 5. Domains & OAuth
- Generate a public domain for the **frontend** service (Settings → Networking →
  Generate Domain), or attach a custom domain.
- Set these (shared or on api) to the frontend's public URL:
  ```
  FRONTEND_URL=https://<your-frontend-domain>
  GOOGLE_REDIRECT_URI=https://<your-frontend-domain>/v1/auth/google/callback
  ```
  (`/v1` is proxied to the api, so the callback rides the same domain.)
- In the **Google Cloud console**, add that redirect URI and the frontend origin
  to the OAuth client's authorized lists.

## 6. Deploy & verify
Deploy all services. Then, against the frontend's public URL:
- `GET /` returns the app; `GET /v1/...` reaches the API (proxy works).
- Check the **api** deploy logs show `alembic upgrade head` ran.
- Register a parent → the verification email arrives (once PR3's domain email is
  set up) → log in → dashboard loads.
- Add a child → Google OAuth completes against the production redirect URI.

## Bootstrapping the first admin
`INVITE_ONLY_ENABLED=true` blocks registration except the **very first** account
(empty `parents` table). Register yourself first, then promote in the Railway
Postgres console:
```sql
UPDATE parents SET is_admin = true, is_developer = true WHERE email = 'you@example.com';
```

## Cost
~$13–16/mo at beta traffic (metered): api/worker/beat hold ~200–300 MB RAM each,
Postgres + Redis are usage-billed, frontend is light. The $5 Hobby plan credit
offsets part of it.
