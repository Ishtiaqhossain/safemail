import { useState } from "react";
import { Link } from "react-router-dom";
import { joinWaitlist } from "@/api/waitlist";
import "./landing.css";

/* ------------------------------------------------------------------ */
/*  Content — edit copy here. Kept as module-level data so it's easy    */
/*  to find and change without hunting through JSX.                     */
/* ------------------------------------------------------------------ */

const STEPS = [
  {
    icon: "🔗",
    title: "Connect their Gmail",
    body: "A guided, read-only Google sign-in. Takes under five minutes — no apps to install on your child's device, no passwords to share.",
  },
  {
    icon: "🤖",
    title: "AI reads every email",
    body: "Claude scans each incoming and outgoing message for genuine safety risks — the way a careful adult would, but instantly and around the clock.",
  },
  {
    icon: "🔔",
    title: "You're alerted only when it matters",
    body: "No feed to scroll, no inbox to read. You get a clear alert — severity, a short summary, and a suggested next step — only when something is genuinely concerning.",
  },
];

// The six categories are fixed and must match the product (analysis.py / PRD §5.3).
const DANGERS = [
  { icon: "💔", title: "Self-harm", body: "Language signalling depression, suicidal thoughts, or self-harm — so you can step in early." },
  { icon: "🎭", title: "Grooming", body: "Predatory adults building trust, isolating, or pushing a child toward secrecy or private chat." },
  { icon: "🪧", title: "Bullying", body: "Targeted cruelty, threats, and harassment aimed at your child — incoming or outgoing." },
  { icon: "💊", title: "Drugs", body: "Conversations about drugs, alcohol, vaping, or where to get them." },
  { icon: "👤", title: "Stranger contact", body: "Unknown adults reaching out, requests to meet, or move the conversation off-platform." },
  { icon: "🪪", title: "Personal info sharing", body: "Your child handing out their address, school, phone number, or photos to people they shouldn't." },
];

// PLACEHOLDER testimonials — illustrative sample copy. Replace with real,
// consented parent quotes before any public launch.
const TESTIMONIALS = [
  { quote: "I didn't want to read my daughter's every message — I just wanted to know if something was actually wrong. This is exactly that.", name: "Maria", detail: "parent of two, 11 & 14" },
  { quote: "It flagged a stranger emailing my son within the first week. One alert, with a clear summary and what to do. That was worth everything.", name: "James", detail: "dad of a 12-year-old" },
  { quote: "Finally something that respects my kid's privacy and still gives me peace of mind. He knows it's for safety, not snooping.", name: "Priya", detail: "parent of a 9-year-old" },
];

const FAQS = [
  {
    q: "Is this spying on my kid?",
    a: "No. SafeMail never shows you the contents of normal emails. The AI reads messages in the moment to assess risk, then discards the raw text — we only ever store a short summary when something is genuinely concerning. Your child knows it's there for safety, not surveillance.",
  },
  {
    q: "How do I get an invite?",
    a: "SafeMail is in invite-only alpha right now. Enter your email in any \"Request an invite\" box above and we'll add you to the list — you'll be able to create your account as soon as your spot opens up.",
  },
  {
    q: "What does it cost?",
    a: "It's free during the alpha. No credit card required to get started.",
  },
  {
    q: "Does it work with a school Google account?",
    a: "Yes. SafeMail works with any Gmail or Google Workspace (including G Suite for Education) account, as long as you can complete the one-time Google sign-in.",
  },
  {
    q: "Will my child know it's there?",
    a: "We recommend being open about it — SafeMail is built for trust, not secrecy. The whole point is that you only get alerted for real safety concerns, so your child keeps their normal privacy.",
  },
  {
    q: "What data do you actually store?",
    a: "The raw body of an email is never written to our database. It lives in memory just long enough to be analysed, then it's gone. We keep only the AI-generated summary, the category, the severity, and basic metadata for alerts that matter.",
  },
  {
    q: "How fast are alerts?",
    a: "Typically within five minutes of an email arriving. SafeMail checks for new mail continuously in the background.",
  },
];

/* ------------------------------------------------------------------ */
/*  Shared bits                                                         */
/* ------------------------------------------------------------------ */

function EmailCaptureCTA({ buttonLabel = "Request an invite" }: { buttonLabel?: string }) {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "submitting" | "done" | "error">("idle");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = email.trim();
    if (!trimmed) return;
    setStatus("submitting");
    try {
      await joinWaitlist(trimmed);
      setStatus("done");
    } catch {
      setStatus("error");
    }
  };

  if (status === "done") {
    return (
      <div
        role="status"
        style={{
          display: "flex", alignItems: "center", gap: 10, maxWidth: 440,
          background: "#f0fdf4", border: "1px solid #bbf7d0", color: "#166534",
          borderRadius: 10, padding: "13px 16px", fontSize: 15, fontWeight: 500,
        }}
      >
        <span style={{ fontSize: 18 }}>✓</span>
        You're on the list — we'll email you an invite as a spot opens up.
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 440 }}>
      <form className="lp-capture" onSubmit={submit}>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          aria-label="Email address"
          required
          disabled={status === "submitting"}
        />
        <button type="submit" className="lp-btn-primary" disabled={status === "submitting"}>
          {status === "submitting" ? "Adding…" : buttonLabel}
        </button>
      </form>
      {status === "error" && (
        <p style={{ color: "#dc2626", fontSize: 13, marginTop: 8 }}>
          Something went wrong. Please try again in a moment.
        </p>
      )}
    </div>
  );
}

function Section({
  id,
  bg,
  children,
  style,
}: {
  id?: string;
  bg?: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <section id={id} style={{ background: bg ?? "transparent", padding: "84px 0", ...style }}>
      <div className="lp-container">{children}</div>
    </section>
  );
}

const Eyebrow = ({ children }: { children: React.ReactNode }) => (
  <div style={{ color: "#2563eb", fontWeight: 700, fontSize: 13, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 12 }}>
    {children}
  </div>
);

/* ------------------------------------------------------------------ */
/*  Sections                                                            */
/* ------------------------------------------------------------------ */

function Brand({ size = 22 }: { size?: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
      <span style={{ fontSize: size + 4 }}>🛡️</span>
      <span style={{ fontSize: size, fontWeight: 700, color: "#0f172a", letterSpacing: "-0.02em" }}>SafeMail</span>
    </div>
  );
}

function Nav() {
  return (
    <nav className="lp-nav">
      <div className="lp-container" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", height: 64 }}>
        <Link to="/" style={{ textDecoration: "none" }}><Brand /></Link>
        <div className="lp-nav-links">
          <a className="lp-nav-link" href="#how-it-works">How it works</a>
          <a className="lp-nav-link" href="#what-we-detect">What we detect</a>
          <a className="lp-nav-link" href="#privacy">Privacy</a>
          <a className="lp-nav-link" href="#faq">FAQ</a>
          <Link className="lp-btn-ghost" to="/login">Sign in</Link>
          <a className="lp-btn-primary" href="#top" style={{ fontSize: 14, padding: "9px 16px" }}>Request an invite</a>
        </div>
      </div>
    </nav>
  );
}

function MockAlertCard() {
  return (
    <div className="lp-card" style={{ boxShadow: "0 24px 48px rgba(15,23,42,0.12)", maxWidth: 380 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 18 }}>🛡️</span>
          <span style={{ fontWeight: 700, fontSize: 14 }}>SafeMail alert</span>
        </div>
        <span style={{ background: "#fef2f2", color: "#dc2626", fontSize: 11, fontWeight: 700, padding: "3px 9px", borderRadius: 999, letterSpacing: "0.04em" }}>
          HIGH SEVERITY
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 16 }}>👤</span>
        <span style={{ fontWeight: 600, fontSize: 14 }}>Possible stranger contact</span>
      </div>
      <p style={{ color: "#475569", fontSize: 13.5, lineHeight: 1.55, marginBottom: 14 }}>
        An unknown adult asked Emma to keep their conversation private and move to a different app. No personal details were shared yet.
      </p>
      <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 9, padding: "10px 12px" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#64748b", letterSpacing: "0.05em", marginBottom: 3 }}>SUGGESTED NEXT STEP</div>
        <div style={{ fontSize: 13, color: "#0f172a" }}>Talk with Emma about who the sender is before she replies.</div>
      </div>
    </div>
  );
}

function Hero() {
  return (
    <section id="top" style={{ background: "linear-gradient(180deg,#f8fafc 0%,#fff 100%)", padding: "72px 0 84px" }}>
      <div className="lp-container">
        <div className="lp-grid-2">
          <div>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 7, background: "#eef2ff", color: "#4338ca", fontSize: 13, fontWeight: 600, padding: "6px 12px", borderRadius: 999, marginBottom: 20 }}>
              <span style={{ width: 7, height: 7, borderRadius: 999, background: "#6366f1", display: "inline-block" }} />
              Invite-only alpha
            </span>
            <h1 className="lp-hero-h1" style={{ fontSize: 52, fontWeight: 800, lineHeight: 1.05, letterSpacing: "-0.03em", color: "#0f172a" }}>
              Your child's inbox is a blind spot. We watch it for you.
            </h1>
            <p style={{ fontSize: 18, color: "#475569", lineHeight: 1.55, marginTop: 20, maxWidth: 520 }}>
              SafeMail uses AI to scan your child's email for grooming, bullying, self-harm and other real dangers — and alerts you <strong>only</strong> when something genuinely concerning is found. You don't read their email. We don't store it.
            </p>
            <div style={{ marginTop: 28 }}>
              <EmailCaptureCTA />
              <p style={{ fontSize: 13, color: "#94a3b8", marginTop: 12 }}>
                Free during the alpha · No credit card · Connect in under 5 minutes
              </p>
            </div>
          </div>
          <div style={{ display: "flex", justifyContent: "center" }}>
            <MockAlertCard />
          </div>
        </div>
      </div>
    </section>
  );
}

function TrustBar() {
  const stats = [
    { big: "< 5 min", small: "from email to alert" },
    { big: "Never stored", small: "raw email is discarded after analysis" },
    { big: "Ages 8–15", small: "built for the kids most at risk" },
  ];
  return (
    <div style={{ borderTop: "1px solid #e2e8f0", borderBottom: "1px solid #e2e8f0", background: "#fff" }}>
      <div className="lp-container" style={{ padding: "28px 24px" }}>
        <div className="lp-grid-3">
          {stats.map((s) => (
            <div key={s.big} style={{ textAlign: "center" }}>
              <div style={{ fontSize: 22, fontWeight: 800, color: "#0f172a", letterSpacing: "-0.02em" }}>{s.big}</div>
              <div style={{ fontSize: 13.5, color: "#64748b", marginTop: 4 }}>{s.small}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Problem() {
  return (
    <Section bg="#fff">
      <div style={{ maxWidth: 760, margin: "0 auto", textAlign: "center" }}>
        <Eyebrow>The problem</Eyebrow>
        <h2 style={{ fontSize: 34, fontWeight: 800, letterSpacing: "-0.02em", lineHeight: 1.15 }}>
          Email is the one place no parent is looking
        </h2>
        <p style={{ fontSize: 17, color: "#475569", lineHeight: 1.65, marginTop: 18 }}>
          Kids use email for school, sign-ups, and talking to people you've never met. Unlike social media, there's no feed to scroll and no profile to check — which is exactly why predators, bullies, and harmful content slip through it.
        </p>
        <p style={{ fontSize: 17, color: "#475569", lineHeight: 1.65, marginTop: 14 }}>
          Until now you've had two bad options: read <em>every</em> email — invasive, exhausting, and corrosive to trust — or read <em>none</em>, and hope. SafeMail is the middle ground: it surfaces only the messages that actually matter.
        </p>
      </div>
    </Section>
  );
}

function HowItWorks() {
  return (
    <Section id="how-it-works" bg="#f8fafc">
      <div style={{ textAlign: "center", marginBottom: 12 }}>
        <Eyebrow>How it works</Eyebrow>
        <h2 style={{ fontSize: 34, fontWeight: 800, letterSpacing: "-0.02em" }}>Set up once. Stay aware without snooping.</h2>
      </div>
      <div className="lp-grid-3" style={{ marginTop: 44 }}>
        {STEPS.map((s, i) => (
          <div key={s.title} className="lp-card" style={{ textAlign: "center" }}>
            <div style={{ fontSize: 36 }}>{s.icon}</div>
            <h3 style={{ fontSize: 18, marginTop: 14 }}>{i + 1}. {s.title}</h3>
            <p style={{ color: "#64748b", marginTop: 8, lineHeight: 1.6, fontSize: 14.5 }}>{s.body}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}

function WhatWeDetect() {
  return (
    <Section id="what-we-detect" bg="#fff">
      <div style={{ textAlign: "center", marginBottom: 12 }}>
        <Eyebrow>What we detect</Eyebrow>
        <h2 style={{ fontSize: 34, fontWeight: 800, letterSpacing: "-0.02em" }}>Six dangers, caught in plain language</h2>
        <p style={{ fontSize: 16, color: "#64748b", marginTop: 14, maxWidth: 620, marginInline: "auto" }}>
          SafeMail is tuned for the things that genuinely put kids at risk — not ads or spam. Every alert comes with a severity and a suggested next step.
        </p>
      </div>
      <div className="lp-grid-6" style={{ marginTop: 44 }}>
        {DANGERS.map((d) => (
          <div key={d.title} className="lp-card lp-card-hover">
            <div style={{ fontSize: 28 }}>{d.icon}</div>
            <h3 style={{ fontSize: 16.5, marginTop: 12 }}>{d.title}</h3>
            <p style={{ color: "#64748b", marginTop: 6, lineHeight: 1.55, fontSize: 14 }}>{d.body}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}

function Privacy() {
  const points = [
    { icon: "🗑️", title: "Raw email is never stored", body: "The body of a message lives in memory only long enough to be analysed, then it's gone. We keep just the AI summary and metadata — and only when it's an alert." },
    { icon: "🎚️", title: "You choose what alerts you", body: "Turn categories on or off so you only hear about what matters to your family. No noise, no firehose." },
    { icon: "🤝", title: "Safety, not surveillance", body: "Your child keeps their everyday privacy. You're notified for genuine safety concerns — nothing else." },
  ];
  return (
    <Section id="privacy" bg="#0f172a" style={{ color: "#fff" }}>
      <div style={{ textAlign: "center", marginBottom: 12 }}>
        <div style={{ color: "#93c5fd", fontWeight: 700, fontSize: 13, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 12 }}>Our privacy promise</div>
        <h2 style={{ fontSize: 34, fontWeight: 800, letterSpacing: "-0.02em", color: "#fff" }}>Built to protect your child — including from us</h2>
      </div>
      <div className="lp-grid-3" style={{ marginTop: 44 }}>
        {points.map((p) => (
          <div key={p.title} style={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 14, padding: 24 }}>
            <div style={{ fontSize: 30 }}>{p.icon}</div>
            <h3 style={{ fontSize: 17, marginTop: 12, color: "#fff" }}>{p.title}</h3>
            <p style={{ color: "#cbd5e1", marginTop: 8, lineHeight: 1.6, fontSize: 14.5 }}>{p.body}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}

function Testimonials() {
  return (
    <Section bg="#f8fafc">
      <div style={{ textAlign: "center", marginBottom: 12 }}>
        <Eyebrow>Loved by careful parents</Eyebrow>
        <h2 style={{ fontSize: 34, fontWeight: 800, letterSpacing: "-0.02em" }}>Peace of mind, without the guilt</h2>
      </div>
      <div className="lp-grid-3" style={{ marginTop: 44 }}>
        {TESTIMONIALS.map((t) => (
          <div key={t.name} className="lp-card" style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ color: "#f59e0b", fontSize: 15, marginBottom: 10 }}>★★★★★</div>
            <p style={{ fontSize: 15, color: "#1e293b", lineHeight: 1.6, flex: 1 }}>"{t.quote}"</p>
            <div style={{ marginTop: 16, fontSize: 13.5 }}>
              <span style={{ fontWeight: 700, color: "#0f172a" }}>{t.name}</span>
              <span style={{ color: "#94a3b8" }}> — {t.detail}</span>
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}

function EarlyAccessBand() {
  return (
    <Section bg="#fff">
      <div style={{ background: "linear-gradient(135deg,#2563eb 0%,#4f46e5 100%)", borderRadius: 24, padding: "56px 40px", textAlign: "center", color: "#fff" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 7, background: "rgba(255,255,255,0.15)", color: "#fff", fontSize: 13, fontWeight: 600, padding: "6px 12px", borderRadius: 999, marginBottom: 18 }}>
          Invite-only · limited spots during the alpha
        </span>
        <h2 style={{ fontSize: 36, fontWeight: 800, letterSpacing: "-0.02em", color: "#fff", maxWidth: 640, marginInline: "auto", lineHeight: 1.15 }}>
          Be the first to protect your kid's inbox
        </h2>
        <p style={{ fontSize: 17, color: "#dbeafe", marginTop: 14, maxWidth: 520, marginInline: "auto" }}>
          We're onboarding families a few at a time. Request an invite and we'll save your spot.
        </p>
        <div style={{ display: "flex", justifyContent: "center", marginTop: 28 }}>
          <div style={{ background: "#fff", borderRadius: 12, padding: 8 }}>
            <EmailCaptureCTA />
          </div>
        </div>
      </div>
    </Section>
  );
}

function FAQ() {
  return (
    <Section id="faq" bg="#fff">
      <div style={{ maxWidth: 760, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 36 }}>
          <Eyebrow>Questions</Eyebrow>
          <h2 style={{ fontSize: 34, fontWeight: 800, letterSpacing: "-0.02em" }}>Frequently asked</h2>
        </div>
        <div className="lp-faq">
          {FAQS.map((f) => (
            <details key={f.q}>
              <summary>{f.q}</summary>
              <p>{f.a}</p>
            </details>
          ))}
        </div>
      </div>
    </Section>
  );
}

function Footer() {
  return (
    <footer style={{ background: "#f8fafc", borderTop: "1px solid #e2e8f0", padding: "48px 0" }}>
      <div className="lp-container" style={{ display: "flex", flexWrap: "wrap", gap: 24, alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <Brand size={18} />
          <p style={{ color: "#94a3b8", fontSize: 13, marginTop: 8, maxWidth: 320 }}>
            AI-powered email safety for families. Alerts only when it matters.
          </p>
        </div>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap", fontSize: 14 }}>
          <a className="lp-nav-link" href="#how-it-works">How it works</a>
          <a className="lp-nav-link" href="#privacy">Privacy</a>
          <a className="lp-nav-link" href="#faq">FAQ</a>
          <Link className="lp-nav-link" to="/login">Sign in</Link>
          <a className="lp-nav-link" href="#">Privacy Policy</a>
          <a className="lp-nav-link" href="#">Terms</a>
        </div>
      </div>
      <div className="lp-container" style={{ marginTop: 28, color: "#94a3b8", fontSize: 12.5 }}>
        © 2026 SafeMail. All rights reserved.
      </div>
    </footer>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                                */
/* ------------------------------------------------------------------ */

export default function Landing() {
  return (
    <div className="lp-root">
      <Nav />
      <Hero />
      <TrustBar />
      <Problem />
      <HowItWorks />
      <WhatWeDetect />
      <Privacy />
      <Testimonials />
      <EarlyAccessBand />
      <FAQ />
      <Footer />
    </div>
  );
}
