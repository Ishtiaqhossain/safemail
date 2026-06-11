# Spec: Public Marketing Landing Page

Status: **DRAFT — awaiting approval** · Owner: frontend · Created: 2026-06-11

## Objective

**What & why.** Today a first-time visitor has no idea what SafeMail is. The root
path `/` redirects to `/dashboard`, which bounces unauthenticated visitors to the
`/login` card — whose only product explanation is the line *"Email monitoring for
families."* There is **no marketing or education content anywhere** before the
registration gate. This kills conversion: people won't register for a product they
don't understand.

Build a public, Bark-inspired (https://www.bark.us) landing page at `/` that
educates a worried parent on the problem, how SafeMail works, what it detects, and
the privacy guarantees — and funnels them into registration via a
"request an invite" email-capture CTA.

**SafeMail is currently invite-only**, and this is enforced for real in the backend
(`auth.py:64`, `settings.invite_only_enabled` + the allowlist service). The landing
page must communicate this clearly — it's both honest and a legitimate scarcity/upsell
angle. The CTA does **not** fake a "we'll email you" confirmation (we have no waitlist
store): submitting routes the visitor to the register form, and if their email isn't
on the allowlist the backend already returns the invite-only message, which the Login
page surfaces. Honest end-to-end, zero backend changes.

**User.** The Worried Parent (PRD §3): has a child aged 8–15 with a Gmail / school
Google account; wants to catch real dangers without surveilling everything.

**Success looks like:**
- A visitor who has never heard of SafeMail can, within one scroll, explain (a) what
  problem it solves, (b) how it works in 3 steps, (c) what it detects, (d) that raw
  email is never stored.
- Every primary CTA ("Request an invite") lands the visitor on the registration form
  with their email pre-filled.
- The invite-only status is stated plainly (hero badge + FAQ) — no visitor is misled
  into thinking they can sign up instantly without an invite.
- Logged-in users never see the landing page — `/` sends them to `/dashboard`.
- Zero backend changes; no new runtime dependencies; build + typecheck stay green.

### Reframed success criteria (testable)
- [ ] `GET /` (unauthenticated) renders the landing page, HTTP 200, no redirect to `/login`.
- [ ] `GET /` (authenticated) redirects to `/dashboard`.
- [ ] Page contains all 11 sections listed under "Content / Sections" below.
- [ ] All "Request an invite" CTAs navigate to
      `/login?mode=register&email=<value>` (email omitted from query when blank).
- [ ] The hero shows an "Invite-only alpha" badge and the FAQ explains how to get in.
- [ ] `/login?mode=register&email=foo@bar.com` opens the **Register** tab with the
      email field pre-populated.
- [ ] Layout is usable at 360px (mobile), 768px (tablet), and ≥1200px (desktop):
      no horizontal scroll, multi-column grids collapse to one column on mobile.
- [ ] `npm run build` (tsc + vite) and `npm run lint` pass with no new errors.

## Tech Stack

Unchanged. React 18.3 + TypeScript 5.6 + Vite 5 + react-router-dom 6. Inline styles +
CSS variables from `src/index.css`. **No** Tailwind, no UI library, no animation
library, no analytics SDK, no new dependencies.

The one structural addition: a scoped CSS file `src/pages/landing.css` (imported by
the landing page only) to provide **responsive behavior** — inline styles cannot
express media queries. All classes are namespaced `.lp-*` so they can't leak into the
app shell.

## Commands

```
Dev:      cd frontend && npm run dev          # http://localhost:3000
Build:    cd frontend && npm run build        # tsc && vite build  (typecheck gate)
Lint:     cd frontend && npm run lint
Preview:  cd frontend && npm run preview
```

There is no frontend unit-test runner in this repo — verification is build + lint +
manual browser check (see Testing Strategy).

## Project Structure

```
frontend/src/
├── App.tsx                 → MODIFIED: add public "/" route + authed redirect
├── pages/
│   ├── Login.tsx           → MODIFIED: read ?mode and ?email query params (prefill)
│   ├── Landing.tsx         → NEW: the landing page; composes section components
│   └── landing.css         → NEW: scoped .lp-* responsive styles (media queries)
└── (everything else unchanged)
```

**Component organization.** Following the repo convention (pages are self-contained
files with inline styles), `Landing.tsx` holds the page plus its section components as
local function components in the same file. Two shared local helpers:
- `EmailCaptureCTA` — the email input + button, used in the hero and the early-access
  band. Encapsulates the "navigate to register with email" behavior so it's defined once.
- `Section` — a max-width, padded wrapper for consistent vertical rhythm.

## Code Style

Match `Login.tsx` exactly: inline `style={{}}` objects, CSS variables referenced as
literal hex (the codebase uses literal hex in inline styles, e.g. `#2563eb`, not
`var(--primary)`), camelCase, default export for the page, 🛡️ shield + "SafeMail"
brand lockup, Inter font (inherited), 8/12/14px radius scale, slate palette.

```tsx
// Local section component pattern used throughout Landing.tsx
function HowItWorks() {
  return (
    <Section id="how-it-works" bg="#fff">
      <h2 style={{ fontSize: 30, textAlign: "center", letterSpacing: "-0.02em" }}>
        How SafeMail works
      </h2>
      <div className="lp-grid-3" style={{ marginTop: 40 }}>
        {STEPS.map((s, i) => (
          <div key={s.title} style={{ textAlign: "center" }}>
            <div style={{ fontSize: 34 }}>{s.icon}</div>
            <h3 style={{ marginTop: 12 }}>{i + 1}. {s.title}</h3>
            <p style={{ color: "#64748b", marginTop: 6 }}>{s.body}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}
```

Content (steps, dangers, FAQ, testimonials) lives in module-level `const` arrays at
the top of the file so copy is easy to find and edit.

## Content / Sections

Grounded in the PRD and `analysis.py` detection categories. **The 6 detection
categories are fixed and must match the product:** self-harm, grooming, bullying,
drugs, stranger contact, personal-info sharing.

1. **Sticky top nav** — 🛡️ SafeMail · anchor links (How it works · What we detect ·
   Privacy · FAQ) · "Sign in" (→ `/login`) · "Get early access" button (→ hero).
2. **Hero** — an **"Invite-only alpha"** pill/badge above the headline; headline (the
   blind-spot promise), subhead, `EmailCaptureCTA` (button reads "Request an invite"),
   trust microcopy ("Free during the alpha · No credit card"), and a supporting visual:
   a CSS-built mock **alert card** (severity chip + summary + suggested action) so the
   product is shown, not just described.
3. **Trust bar** — three stat chips: "Alerts in under 5 minutes" · "Raw emails never
   stored" · "Built for kids aged 8–15". (No fake company logos — we have no assets.)
4. **The problem** — "Your child's inbox is a blind spot." The binary-choice framing
   from PRD §1 (read everything = invasive vs. read nothing = exposed).
5. **How it works (3 steps)** — Connect Gmail (under 5 min) → AI reads every email →
   You're alerted only when it matters.
6. **What we detect (6-card grid)** — the six categories, each with an emoji icon, a
   one-line plain-language description, and the severity framing.
7. **Privacy promise** — Raw email body is never stored (only the AI summary +
   metadata) · You choose which categories alert you · Your child knows it's
   safety-only, not surveillance. (All true per PRD §5.6 / CLAUDE.md.)
8. **Testimonials** — 2–3 parent quotes. **Placeholder copy, clearly labelled in a
   code comment as sample content to be replaced** — we will not invent attributed
   real people. Mark with generic first-name + "parent of two" style attribution.
9. **Early-access band ("upsell")** — restates value, "Invite-only — limited spots
   during the alpha" scarcity framing, second `EmailCaptureCTA` ("Request an invite").
   This replaces a pricing table (no pricing per decision).
10. **FAQ (accordion)** — Is this spying on my kid? · **How do I get an invite?** (we're
    in invite-only alpha; request one above and we'll add you to the list) · What does
    it cost? (free during the alpha) · Does it work with a school Google account? · Will
    my child know? · What data do you store? · How fast are alerts? Built with native
    `<details>/<summary>` (no JS, no library).
11. **Final CTA + Footer** — closing CTA, then footer with brand, anchor links, and
    placeholder Privacy/Terms links + copyright.

## Routing & Login changes

**App.tsx**
- Add `PublicRoute` wrapper: `loading → spinner`, `authenticated → <Navigate to="/dashboard">`,
  `unauthenticated → render children` (no NavBar — the landing page has its own nav).
- Add `<Route path="/" element={<PublicRoute authStatus={authStatus}><Landing/></PublicRoute>} />`.
- The catch-all `*` stays `→ /dashboard` (which already cascades to `/login` if needed).

**Login.tsx**
- Read `searchParams.get("mode")`; if `"register"`, initialize `mode` state to `"register"`.
- Read `searchParams.get("email")`; if present, initialize `email` state to it.
- No other behavior change. (Existing `?reset=true` handling is untouched.)

## Testing Strategy

No JS test runner exists in `frontend/`; do not add one for this task. Verification is:

1. **Typecheck/build gate:** `npm run build` (runs `tsc`) must pass — catches prop/type
   errors. **Primary automated gate.**
2. **Lint gate:** `npm run lint` clean.
3. **Manual browser checklist** (against `npm run dev`):
   - `/` unauthenticated → landing renders, all 11 sections present.
   - Hero CTA with an email → lands on Register tab, email pre-filled.
   - Hero CTA blank → lands on Register tab, no email.
   - "Sign in" → `/login` (Sign-in tab).
   - Resize to 360px → single-column, no horizontal scroll; FAQ accordions open/close.
   - Log in, then visit `/` → redirected to `/dashboard`.

## Boundaries

- **Always:** match existing inline-style conventions and the slate/blue palette;
  keep the 6 detection categories accurate to the product; run `npm run build` before
  declaring done; keep all copy truthful to what the product actually does.
- **Ask first:** adding any npm dependency; adding a real waitlist/email-capture
  backend endpoint; changing auth/routing behavior beyond the `/` route and Login
  prefill; introducing a CSS framework or build-config change.
- **Never:** invent statistics, real customer names, certifications, or compliance
  claims (e.g. "COPPA-certified") that aren't substantiated; store secrets; add
  tracking/analytics SDKs; modify backend code.

## Success Criteria

The "Reframed success criteria" checklist under Objective is the definition of done.
All boxes checked + build/lint green + manual checklist passed.

## Open Questions

1. **Testimonials:** OK to ship clearly-labelled placeholder quotes for you to replace,
   or omit the section until you supply real ones? (Default: ship placeholders.)
2. **Footer legal links:** Privacy Policy / Terms — link to `#` placeholders for now, or
   do these pages exist somewhere? (Default: `#` placeholders.)
3. **"Free during the alpha" claim:** confirm accurate to say publicly. (Default: keep,
   since registration is free for allowlisted users.)
4. **Proper waitlist capture (future):** the honest invite funnel currently routes to
   the register form, where non-allowlisted emails see the backend's invite-only
   message. A real "request an invite" experience would need a backend waitlist endpoint
   to actually store the email and notify them — out of scope here (ask-first boundary),
   flagged as the natural follow-up.
```
