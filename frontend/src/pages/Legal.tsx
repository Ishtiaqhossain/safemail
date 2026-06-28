import { Link } from "react-router-dom";
import "./landing.css";

/* ------------------------------------------------------------------ */
/*  EDIT THESE before submitting for Google verification.               */
/*  These are the only facts the documents reference that depend on     */
/*  your real business details — change them and the docs update.       */
/* ------------------------------------------------------------------ */
const COMPANY_NAME = "SafeMail";
const CONTACT_EMAIL = "ishtiaq.jishan@gmail.com"; // must be a real, monitored inbox
const JURISDICTION = "the State of California, United States"; // governing law
const EFFECTIVE_DATE = "June 20, 2026";

/* ------------------------------------------------------------------ */
/*  Shared layout — reuses the landing-page styles (landing.css).       */
/* ------------------------------------------------------------------ */

function LegalShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="lp-root">
      <nav className="lp-nav">
        <div
          className="lp-container"
          style={{ display: "flex", alignItems: "center", justifyContent: "space-between", height: 64 }}
        >
          <Link to="/" className="lp-nav-link" style={{ fontWeight: 800, fontSize: 18, color: "#0f172a" }}>
            {COMPANY_NAME}
          </Link>
          <div className="lp-nav-links">
            <Link className="lp-nav-link" to="/privacy">Privacy</Link>
            <Link className="lp-nav-link" to="/terms">Terms</Link>
            <Link className="lp-btn-ghost" to="/login">Sign in</Link>
          </div>
        </div>
      </nav>

      <div className="lp-container" style={{ maxWidth: 820, padding: "56px 24px 80px" }}>
        <h1 style={{ fontSize: 40, fontWeight: 800, letterSpacing: "-0.03em", color: "#0f172a", marginBottom: 8 }}>
          {title}
        </h1>
        <p style={{ color: "#64748b", fontSize: 14, marginBottom: 40 }}>
          Effective {EFFECTIVE_DATE}
        </p>
        <div className="legal-body" style={{ color: "#334155", fontSize: 16, lineHeight: 1.7 }}>
          {children}
        </div>
        <p style={{ marginTop: 56, color: "#94a3b8", fontSize: 13 }}>
          © 2026 {COMPANY_NAME}. All rights reserved. ·{" "}
          <Link className="lp-nav-link" to="/privacy">Privacy</Link> ·{" "}
          <Link className="lp-nav-link" to="/terms">Terms</Link>
        </p>
      </div>
    </div>
  );
}

function H2({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{ fontSize: 22, fontWeight: 700, color: "#0f172a", margin: "36px 0 12px" }}>{children}</h2>
  );
}

/* ================================================================== */
/*  PRIVACY POLICY                                                      */
/* ================================================================== */

export function PrivacyPage() {
  return (
    <LegalShell title="Privacy Policy">
      <p>
        {COMPANY_NAME} ("we", "us") provides an AI-powered email-safety service that lets a
        parent or guardian ("you") monitor a child's email account for signs of danger. This
        policy explains what data we access, how we use it, and the choices you have. We built the
        service to collect as little as possible: <strong>we never store the raw text of any email.</strong>
      </p>

      <H2>Information we collect</H2>
      <p>
        <strong>Account data.</strong> When you register, we store your email address and a
        securely hashed (bcrypt) password. We do not store your password in plain text.
      </p>
      <p>
        <strong>Child profile data.</strong> A display name you choose for the child and the email
        address you connect for monitoring.
      </p>
      <p>
        <strong>Connected mailbox data.</strong> With your explicit authorization, we request{" "}
        <strong>read-only</strong> access to the child's email account so we can analyze incoming and
        outgoing messages for safety risks. How access is granted depends on the provider:
      </p>
      <ul>
        <li>
          <strong>Gmail / Google Workspace</strong> — a Google OAuth sign-in using the{" "}
          <code>gmail.readonly</code> scope, plus your email address (<code>userinfo.email</code>) to
          label the connection.
        </li>
        <li>
          <strong>Apple Mail (iCloud)</strong> — a read-only IMAP connection authenticated with an
          app-specific password you generate at Apple.
        </li>
      </ul>
      <p>
        We read message content <em>only transiently, in memory,</em> to analyze it. We do{" "}
        <strong>not</strong> retain email bodies, attachments, contact lists, or message contents
        after analysis. We expect to support additional providers over time; access for any new
        provider will likewise be read-only and limited to what analysis requires.
      </p>
      <p>
        <strong>Alert data we do store.</strong> After analysis, we keep only the AI-generated
        summary, the detected category and severity, and limited metadata (sender/recipient
        addresses, subject line, timestamp, and direction). This is what powers your alert feed.
      </p>

      <H2>How we use information</H2>
      <p>
        We use the data solely to operate the safety service: to detect potentially dangerous
        situations across six categories — self-harm, grooming, bullying, drugs and alcohol,
        stranger contact, and sharing of personal information — and to notify you when something
        genuinely warrants attention. We also use aggregate, non-identifying usage statistics to
        monitor and improve detection quality and to manage operating costs. We do{" "}
        <strong>not</strong> sell your data or use it for advertising.
      </p>

      <H2>How email analysis works</H2>
      <p>
        Connected messages are sent to our AI provider (Anthropic's Claude API) for classification
        and summarization. Only the message text needed for that analysis is transmitted, over
        encrypted connections, and only the resulting summary and metadata are returned to and
        stored by us. Email content is not used to train third-party models.
      </p>

      <H2>Service providers (subprocessors)</H2>
      <ul>
        <li><strong>Google</strong> — a source of monitored email, via the Gmail API.</li>
        <li><strong>Apple</strong> — a source of monitored email, via iCloud IMAP.</li>
        <li><strong>Anthropic (Claude API)</strong> — AI classification and summarization of message content.</li>
        <li><strong>SendGrid</strong> — delivery of alert and account emails.</li>
        <li><strong>Firebase Cloud Messaging</strong> — optional push notifications.</li>
        <li><strong>Our cloud hosting provider</strong> — runs the application database and servers.</li>
      </ul>

      <H2>Data security &amp; retention</H2>
      <p>
        Email-access credentials — Google OAuth tokens and Apple app-specific passwords — are
        encrypted at rest (Fernet/AES) before being written to our database and are never exposed in
        our interface or logs. Access to authentication endpoints is rate-limited and session tokens
        can be revoked. We retain account, child, and alert records for as long as your account is
        active. When you disconnect an email account or delete your account, the associated stored
        records and credentials are deleted; for Google connections the OAuth grant is also revoked
        with Google.
      </p>

      <H2>Your choices &amp; rights</H2>
      <p>
        You can disconnect a child's email account at any time from your dashboard or settings, which
        removes our stored credentials and stops monitoring. You can delete your account, which
        removes your stored data. For <strong>Gmail</strong>, you may also revoke our access from your
        Google Account's security settings at{" "}
        <a className="lp-nav-link" href="https://myaccount.google.com/permissions" target="_blank" rel="noreferrer">
          myaccount.google.com/permissions
        </a>. For <strong>Apple Mail</strong>, revoke the app-specific password at{" "}
        <a className="lp-nav-link" href="https://appleid.apple.com" target="_blank" rel="noreferrer">
          appleid.apple.com
        </a>. For any data request, contact us at{" "}
        <a className="lp-nav-link" href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
      </p>

      <H2>Children's privacy</H2>
      <p>
        The service is purchased and operated by a parent or legal guardian, who must have the
        authority to consent to monitoring of the child's account. Our accounts are for adults; we do
        not knowingly let children register as account holders. The monitored child's email content is
        processed only to generate safety alerts for the responsible adult, and is never stored.
      </p>

      <H2>Google API Limited Use disclosure</H2>
      <p>
        {COMPANY_NAME}'s use and transfer of information received from Google APIs adheres to the{" "}
        <a
          className="lp-nav-link"
          href="https://developers.google.com/terms/api-services-user-data-policy"
          target="_blank"
          rel="noreferrer"
        >
          Google API Services User Data Policy
        </a>
        , including the Limited Use requirements. Specifically, data obtained through Gmail scopes is
        used only to provide and improve the user-facing email-safety features described above; is not
        transferred to others except as necessary to provide those features, to comply with applicable
        law, or as part of a merger or acquisition; is not used for advertising; and is not used or
        transferred to determine creditworthiness or for lending. No humans read the email content
        except where required for security, to comply with the law, or where you have given explicit
        consent.
      </p>

      <H2>Changes to this policy</H2>
      <p>
        We may update this policy as the service evolves. Material changes will be reflected by an
        updated effective date and, where appropriate, a direct notice.
      </p>

      <H2>Contact</H2>
      <p>
        Questions about this policy or your data? Email{" "}
        <a className="lp-nav-link" href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
      </p>
    </LegalShell>
  );
}

/* ================================================================== */
/*  TERMS OF SERVICE                                                    */
/* ================================================================== */

export function TermsPage() {
  return (
    <LegalShell title="Terms of Service">
      <p>
        These Terms of Service ("Terms") govern your use of {COMPANY_NAME} (the "Service"). By
        creating an account or using the Service, you agree to these Terms. If you do not agree, do
        not use the Service.
      </p>

      <H2>1. Eligibility &amp; accounts</H2>
      <p>
        You must be at least 18 years old and the parent or legal guardian of the child whose email
        account you connect, with the legal authority to consent to monitoring that account. You are
        responsible for keeping your login credentials secure and for all activity under your account.
        Access may be invite-only; we may grant or decline access at our discretion.
      </p>

      <H2>2. What the Service does</H2>
      <p>
        The Service connects to a child's Gmail account with read-only access, analyzes incoming and
        outgoing messages using AI, and notifies you when it detects content that may indicate a
        safety risk. You authorize us to access the connected account for this purpose for as long as
        the connection remains active.
      </p>

      <H2>3. Not an emergency service</H2>
      <p>
        <strong>
          {COMPANY_NAME} is a monitoring aid, not an emergency, crisis, or law-enforcement service.
        </strong>{" "}
        AI detection is probabilistic: it may miss harmful content (false negatives) or flag harmless
        content (false positives). Do not rely on the Service as your sole means of protecting a child.
        If you believe a child is in danger, contact local emergency services or an appropriate
        crisis line immediately.
      </p>

      <H2>4. Acceptable use</H2>
      <p>
        You agree to use the Service only to monitor a child for whom you are the responsible
        guardian, and only in compliance with applicable law. You may not use the Service to monitor
        any person without the legal right to do so, to access accounts you are not authorized to
        access, or to interfere with, reverse-engineer, or disrupt the Service.
      </p>

      <H2>5. Your data</H2>
      <p>
        Our handling of your information is described in our{" "}
        <Link className="lp-nav-link" to="/privacy">Privacy Policy</Link>, which is incorporated into
        these Terms. As described there, we do not store raw email content — only AI-generated
        summaries and metadata.
      </p>

      <H2>6. Third-party services</H2>
      <p>
        The Service relies on third parties including Google, Anthropic, SendGrid, and our hosting
        provider. Your use of connected Google services is also subject to Google's terms. We are not
        responsible for the availability or actions of third-party services.
      </p>

      <H2>7. Disclaimers</H2>
      <p>
        The Service is provided "as is" and "as available," without warranties of any kind, express or
        implied, including merchantability, fitness for a particular purpose, and non-infringement. We
        do not warrant that the Service will be uninterrupted, error-free, or that it will detect any
        particular risk.
      </p>

      <H2>8. Limitation of liability</H2>
      <p>
        To the maximum extent permitted by law, {COMPANY_NAME} will not be liable for any indirect,
        incidental, special, consequential, or punitive damages, or for any loss arising from missed
        or erroneous detections, even if advised of the possibility. Our total liability for any claim
        relating to the Service will not exceed the amount you paid us in the twelve months before the
        claim.
      </p>

      <H2>9. Termination</H2>
      <p>
        You may stop using the Service and delete your account at any time. We may suspend or terminate
        access if you violate these Terms or to protect the Service or its users. On termination, your
        stored data and OAuth grants are deleted and revoked as described in the Privacy Policy.
      </p>

      <H2>10. Governing law</H2>
      <p>
        These Terms are governed by the laws of {JURISDICTION}, without regard to conflict-of-laws
        rules.
      </p>

      <H2>11. Changes</H2>
      <p>
        We may update these Terms from time to time. Continued use of the Service after changes take
        effect constitutes acceptance of the updated Terms.
      </p>

      <H2>12. Contact</H2>
      <p>
        Questions about these Terms? Email{" "}
        <a className="lp-nav-link" href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
      </p>
    </LegalShell>
  );
}
