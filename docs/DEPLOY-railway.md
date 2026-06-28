# Deploying SafeMail to Railway

This deploys the **same Docker images** verified by `docker-compose.prod.yml` —
Railway is just a thin layer over them. Nothing here is Railway-specific in the
app code; if you ever leave Railway, the compose stack still runs anywhere.

The stack is **four app services** (api, worker, beat, frontend) plus Railway's
**managed Postgres and Redis**. `backend/railway.json` and `frontend/railway.json`
pin the Docker builder; per-service settings are configured in the dashboard
because the three backend services share one directory.

This guide uses the **dashboard** flow (easier than the CLI for a first
multi-service deploy).

---

## Step 0 — Generate production secrets locally first

Run these on your machine and keep the output handy. **Generate fresh values** —
do not reuse local-dev secrets.

```bash
cd ~/openbark

# 1. RSA keypair for JWT
openssl genrsa -out prod_private.pem 2048
openssl rsa -in prod_private.pem -pubout -out prod_public.pem

# 2. Convert each PEM to a single line with \n escapes
#    (Railway variables can't hold real newlines; the app restores them).
awk 'NF {printf "%s\\n", $0}' prod_private.pem    # -> paste as JWT_PRIVATE_KEY
awk 'NF {printf "%s\\n", $0}' prod_public.pem     # -> paste as JWT_PUBLIC_KEY

# 3. Fernet key (encrypts stored OAuth tokens)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # -> FERNET_KEY
```

You'll also need your existing **Google OAuth client ID/secret**, **Anthropic API
key**, and **SendGrid key** (and, optionally, a **Microsoft Entra app
ID/secret** to offer Outlook / Microsoft 365 — see Step 5).

> After pasting the keys into Railway, delete `prod_private.pem` /
> `prod_public.pem` — they shouldn't sit on disk.

## Step 1 — Create the project + datastores

1. [railway.com](https://railway.com) -> **New Project** -> **Deploy from GitHub
   repo** -> pick `Ishtiaqhossain/safemail` (authorize Railway on the repo if
   prompted).
2. It creates one service — that's fine, you'll configure it as the **api** in
   Step 3.
3. In the project canvas: **+ New -> Database -> Add PostgreSQL**. Again:
   **+ New -> Database -> Add Redis**.

## Step 2 — Set shared variables

Project (not a service) -> **Variables** tab -> add the secrets every backend
service shares:

```
DEBUG=false
COOKIE_SECURE=true
INVITE_ONLY_ENABLED=true
FERNET_KEY=<from step 0>
GOOGLE_CLIENT_ID=<yours>
GOOGLE_CLIENT_SECRET=<yours>
ANTHROPIC_API_KEY=<yours>
SENDGRID_API_KEY=<yours>
JWT_PRIVATE_KEY=<escaped PEM from step 0>
JWT_PUBLIC_KEY=<escaped PEM from step 0>
```

## Step 3 — Configure the three backend services

Each uses **Root Directory = `backend`** (so it builds `backend/Dockerfile` via
`backend/railway.json`).

> **Set the Root Directory or the build fails.** Without it Railway builds the
> repo root with its autodetect builder (Railpack) and errors with
> *"could not determine how to build the app"* — it never sees the per-service
> `railway.json`/`Dockerfile`. Setting the root directory fixes it. If Railway
> still ignores the Dockerfile, force it under **Settings -> Build -> Builder ->
> Dockerfile**.

**api** (the service auto-created in Step 1):
- Settings -> **Source** -> Root Directory: `backend`
- Settings -> **Variables** (in addition to the shared ones):
  ```
  DATABASE_URL=${{Postgres.DATABASE_URL}}
  REDIS_URL=${{Redis.REDIS_URL}}
  RUN_MIGRATIONS=true
  PORT=8000
  ```
- Settings -> **Deploy -> Healthcheck Path**: `/health`
- Leave **Custom Start Command empty** — it must use the Dockerfile entrypoint so
  migrations run.

**worker** — **+ New -> GitHub Repo -> same repo**:
- Root Directory: `backend`
- Variables: `DATABASE_URL=${{Postgres.DATABASE_URL}}`,
  `REDIS_URL=${{Redis.REDIS_URL}}` (no `RUN_MIGRATIONS`)
- Settings -> Deploy -> **Custom Start Command**:
  `celery -A app.worker worker -l info -c 4`

**beat** — another new service from the repo:
- Root Directory: `backend`
- Same two reference vars
- Custom Start Command: `celery -A app.worker beat -l info`

Why these settings:
- Only **api** sets `RUN_MIGRATIONS=true`, so its entrypoint runs
  `alembic upgrade head` once per deploy; worker/beat skip it (no migration race).
- **api** keeps the default start command so the entrypoint runs; worker/beat
  override it with their Celery commands.
- The app normalizes the `postgres://` scheme from `DATABASE_URL` to asyncpg
  automatically.

> **Reference-var note:** if Railway named your DB services something other than
> `Postgres`/`Redis`, use the actual names in `${{ServiceName.DATABASE_URL}}`.
> The variable editor autocompletes them.

## Step 4 — Configure the frontend service

**+ New -> GitHub Repo -> same repo**:
- Root Directory: `frontend` (uses `frontend/Dockerfile` + `frontend/railway.json`,
  health check `/`).
- Variable: `API_UPSTREAM=${{api.RAILWAY_PRIVATE_DOMAIN}}:8000` — points nginx at
  the api over Railway's private network (this is why we pinned api `PORT=8000`).
- Settings -> Networking -> **Generate Domain** (gives `something.up.railway.app`).

The frontend serves the SPA and reverse-proxies `/v1` to the api, so everything
is **same-origin** (the `SameSite=Strict` refresh cookie works, no CORS).

> nginx resolves the api hostname when it starts, so if the frontend boots before
> the api is reachable it may crash once and restart. That's expected — the
> `ON_FAILURE` restart policy recovers it once the api is up. Deploy the api
> first (Step 6) to avoid the extra restart.

## Step 5 — Wire URLs + Google OAuth

Once you have the frontend domain, add to **shared variables** (or the api
service):
```
FRONTEND_URL=https://<frontend-domain>
GOOGLE_REDIRECT_URI=https://<frontend-domain>/v1/auth/google/callback
```
(`/v1` is proxied to the api, so OAuth rides the same domain — no separate api
domain needed.)

Then in [Google Cloud Console](https://console.cloud.google.com) -> **APIs &
Services -> Credentials -> your OAuth client**:
- **Authorized redirect URIs**: add
  `https://<frontend-domain>/v1/auth/google/callback`
- **Authorized JavaScript origins**: add `https://<frontend-domain>`

### Microsoft (Outlook / Microsoft 365) — optional

Skip this if you only want Gmail + Apple; the app boots fine without it and the
"Outlook / Microsoft 365" connect option errors clearly until it's configured.

1. In the [Microsoft Entra admin center](https://entra.microsoft.com) ->
   **Identity -> Applications -> App registrations -> New registration**:
   - **Supported account types**: *Accounts in any organizational directory and
     personal Microsoft accounts* (this is the `common` tenant — covers school
     M365 **and** personal Outlook.com).
   - **Redirect URI**: platform **Web**, value
     `https://<frontend-domain>/v1/auth/oauth/microsoft/callback`.
2. **Certificates & secrets -> New client secret** -> copy the secret **value**
   (not the id).
3. **API permissions -> Add a permission -> Microsoft Graph -> Delegated**: add
   `Mail.Read`, `User.Read`, `offline_access`, `openid`, `email`. (Admin consent
   isn't required for personal accounts; for a school tenant the tenant admin may
   need to grant it.)
4. Add to Railway **shared variables** (or the api service):
   ```
   MICROSOFT_CLIENT_ID=<application (client) id>
   MICROSOFT_CLIENT_SECRET=<client secret value>
   MICROSOFT_REDIRECT_URI=https://<frontend-domain>/v1/auth/oauth/microsoft/callback
   ```
   The redirect URI must match the one registered in step 1 exactly.

## Step 6 — Deploy in the right order

Deploy **api first** (so the frontend's nginx can resolve it on boot), then
worker, beat, frontend. Watch the **api deploy logs** for
`Running upgrade ... alembic upgrade head` followed by
`Application startup complete`.

## Step 7 — Verify

Against `https://<frontend-domain>`:
- `GET /` loads the app; `GET /v1/...` reaches the API (proxy works).
- Register an account -> succeeds (the first account bypasses the invite gate).
- Log in -> dashboard loads (JWT signs/verifies from env keys; same-origin cookie).
- Add a child -> "Connect Gmail" -> Google OAuth completes back to your domain.
  (If Microsoft is configured, "Connect Outlook / Microsoft 365" likewise.)
- (Once PR3's domain email is set up) the verification email arrives, not in spam.

## Step 8 — Make yourself the first admin

`INVITE_ONLY_ENABLED=true` blocks registration except the **very first** account
(empty `parents` table). Register yourself first, then open the **Postgres service
-> Data / Query tab** and run:
```sql
UPDATE parents SET is_admin = true, is_developer = true WHERE email = 'you@example.com';
```
Log out and back in to pick up the new claims.

---

## Troubleshooting

**Frontend keeps restarting / 502 on `/v1`.** The private-network proxy
(`API_UPSTREAM`) is the likeliest culprit. Confirm the **api** service is healthy
and that you set `PORT=8000` on it (so `${{api.RAILWAY_PRIVATE_DOMAIN}}:8000` is
correct). Railway's internal DNS is IPv6 and nginx resolves the upstream at
startup; redeploy the frontend after the api is up. If it still fails, point
`API_UPSTREAM` at the api's **public** domain instead — that needs an HTTPS
upstream in nginx, so open an issue / ask and we'll adjust `nginx.conf.template`.

**`/docs` returns 404.** Expected in production — Swagger is disabled when
`DEBUG=false`.

**App won't boot, logs mention "Missing required production settings".** A
required secret (`FERNET_KEY` / `GOOGLE_CLIENT_SECRET` / `ANTHROPIC_API_KEY` /
`SENDGRID_API_KEY`) is unset on that service. The fail-fast check naming the
missing key is intentional.

**Login works but stays logged out after refresh.** The refresh cookie isn't
sticking — check the frontend and api ride the **same domain** via the `/v1`
proxy (don't set `VITE_API_BASE_URL` to a separate api domain), and that
`COOKIE_SECURE=true` with HTTPS.

## Cost

~$13–16/mo at beta traffic (metered): api/worker/beat hold ~200–300 MB RAM each,
Postgres + Redis are usage-billed, the frontend is light. The $5 Hobby plan
credit offsets part of it.
