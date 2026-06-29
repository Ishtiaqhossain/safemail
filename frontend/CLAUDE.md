# SafeMail frontend — Claude Code Guide

Applies to everything under `frontend/`. See the **root `CLAUDE.md`** for the project
overview, how to run the full stack, and architecture decisions; see
**`backend/CLAUDE.md`** for the API it talks to.

Stack: **React 18 + TypeScript + Vite**, React Router 6, Axios. Dev server on
`:3000`, which **proxies `/v1` → the API** (`vite.config.ts`) so the browser is
same-origin with the API and the refresh cookie works. `PORT` and `VITE_API_TARGET`
are env-overridable (used by the E2E suite to run on isolated ports).

## Auth / API client model (`src/api/client.ts`)
- The **access token lives in memory only** (never localStorage). The **refresh
  token is an httpOnly cookie** set by the API.
- On app load, `tryRefresh()` POSTs `/v1/auth/refresh` (cookie) to re-mint the access
  token; a 401 triggers one refresh-and-retry, then bounces to `/login`.
- Login/register responses also carry `is_admin`, `is_developer`, `is_email_verified`,
  `onboarding_completed` — stored as in-memory flags that drive the route guards in
  `App.tsx` (`ProtectedRoute`, `OnboardingRoute`, `AdminRoute`, `DeveloperRoute`).
- API base is relative (`""` → `/v1/...`) so prod nginx / dev Vite both proxy it; set
  `VITE_API_BASE_URL` only to point at a separate API origin.

## Conventions
- Keep API calls in `src/api/*` clients, not inline in pages.
- Provider connect UI (Onboarding step + Settings) has a picker: Gmail + Outlook use
  the OAuth redirect (`/auth/oauth/{provider}/connect` via `childrenApi`); Apple uses
  the credentials form (`/auth/email/connect`). Add new providers to the picker.
- The internal `gmail_*` field names in API payloads are legacy identifiers (see
  `backend/CLAUDE.md`) — they're not Gmail-specific.

## E2E tests (Playwright, `e2e/`)
Browser smoke tests drive the real app against a running stack. State is created via
the backend's DEBUG-only seed router (`/v1/dev/*`) — no OAuth/AI/email — so tests are
hermetic. CI runs them on every PR (the `e2e` job).

```bash
npm run test:e2e        # headless (boots the Vite dev server itself)
npm run test:e2e:ui     # interactive runner
```
Full local recipe (isolated ports + the backend env to start) is in
`docs/DEVELOPMENT.md`.

Conventions:
- Each spec seeds its **own namespaced parent** and resets before+after — never share
  one logged-in account across specs (`e2e/fixtures.ts`).
- Prefer role/label selectors; add **`data-testid`** for repeated rows and
  non-semantic status elements (e.g. `alert-row`, `recent-alert`, `prefs-saved`,
  `login-submit`). Scope row locators rather than matching one global testid.
- Assert on visible state / responses, not fixed sleeps.
