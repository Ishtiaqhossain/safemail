import html
import json
from app.config import get_settings

settings = get_settings()

SEVERITY_LABELS = {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM", "low": "LOW"}
CATEGORY_LABELS = {
    "self_harm": "Self-Harm",
    "grooming": "Grooming",
    "bullying": "Bullying",
    "drugs_alcohol": "Drugs & Alcohol",
    "stranger_contact": "Stranger Contact",
    "personal_info_sharing": "Personal Info",
}


def send_alert_email(parent_email: str, child_name: str, alert: dict) -> bool:
    """Returns True if an email was actually sent, False if email is disabled."""
    if not settings.transactional_email_enabled:
        return False
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    severity = SEVERITY_LABELS.get(alert["severity"], str(alert["severity"]).upper())
    category = CATEGORY_LABELS.get(alert["category"], str(alert["category"]))

    # Escape every dynamic value before interpolating into HTML. The summary and
    # response script are model-generated from attacker-controlled email text, so
    # without escaping a crafted email could inject links/markup into the alert
    # email — the most trusted channel the product has.
    summary = html.escape(alert.get("ai_summary") or "")
    script = html.escape(alert.get("ai_response_script") or "Review the email in your child's Gmail account.")
    safe_child = html.escape(child_name)
    safe_severity = html.escape(severity)
    safe_category = html.escape(category)

    html_body = f"""
<h2>SafeMail Safety Alert</h2>
<p><strong>Severity:</strong> {safe_severity}<br>
<strong>Category:</strong> {safe_category}<br>
<strong>Child:</strong> {safe_child}</p>
<h3>What we found</h3>
<p>{summary}</p>
<h3>Suggested next step</h3>
<p>{script}</p>
<p><em>We do not include the original email in this alert to protect your child's privacy.</em></p>
"""

    message = Mail(
        from_email=settings.email_from,
        to_emails=parent_email,
        subject=f"[SafeMail] {severity} Alert — {child_name}'s Email",
        html_content=html_body,
    )
    SendGridAPIClient(settings.sendgrid_api_key).send(message)
    return True


def send_verification_email(to_email: str, verify_url: str) -> None:
    if not settings.transactional_email_enabled:
        return
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    html = f"""
<div style="font-family:sans-serif;max-width:480px;margin:0 auto">
  <h2 style="color:#0f172a">Verify your SafeMail email</h2>
  <p>Thanks for signing up. Click below to verify your email address and activate your account.</p>
  <p style="margin:24px 0">
    <a href="{verify_url}"
       style="background:#2563eb;color:#fff;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:600">
      Verify email address
    </a>
  </p>
  <p style="color:#64748b;font-size:13px">This link expires in 24 hours. If you didn't create a SafeMail account, you can ignore this email.</p>
</div>"""

    message = Mail(
        from_email=settings.email_from,
        to_emails=to_email,
        subject="Verify your SafeMail email address",
        html_content=html,
    )
    SendGridAPIClient(settings.sendgrid_api_key).send(message)


def send_password_reset_email(to_email: str, reset_url: str) -> None:
    if not settings.transactional_email_enabled:
        return
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    html = f"""
<div style="font-family:sans-serif;max-width:480px;margin:0 auto">
  <h2 style="color:#0f172a">Reset your SafeMail password</h2>
  <p>We received a request to reset the password for your account.</p>
  <p style="margin:24px 0">
    <a href="{reset_url}"
       style="background:#2563eb;color:#fff;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:600">
      Reset password
    </a>
  </p>
  <p style="color:#64748b;font-size:13px">This link expires in 30 minutes. If you didn't request a password reset, you can safely ignore this email.</p>
</div>"""

    message = Mail(
        from_email=settings.email_from,
        to_emails=to_email,
        subject="Reset your SafeMail password",
        html_content=html,
    )
    SendGridAPIClient(settings.sendgrid_api_key).send(message)


def send_reconnect_email(to_email: str, child_name: str, gmail_address: str, reconnect_url: str) -> None:
    if not settings.transactional_email_enabled:
        return
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    safe_child = html.escape(child_name)
    safe_gmail = html.escape(gmail_address)

    html_body = f"""
<div style="font-family:sans-serif;max-width:480px;margin:0 auto">
  <h2 style="color:#0f172a">Action needed: reconnect {safe_child}'s email</h2>
  <p>SafeMail has lost access to <strong>{safe_gmail}</strong>, so we are no
     longer monitoring {safe_child}'s email. This usually happens when access is
     revoked or the sign-in / app password expires.</p>
  <p style="color:#b91c1c;font-weight:600">Until you reconnect, no safety alerts will be sent for this account.</p>
  <p style="margin:24px 0">
    <a href="{reconnect_url}"
       style="background:#2563eb;color:#fff;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:600">
      Reconnect email
    </a>
  </p>
  <p style="color:#64748b;font-size:13px">If you intentionally disconnected this account, you can ignore this email.</p>
</div>"""

    message = Mail(
        from_email=settings.email_from,
        to_emails=to_email,
        subject=f"[SafeMail] Reconnect needed — {child_name}'s email is no longer monitored",
        html_content=html_body,
    )
    SendGridAPIClient(settings.sendgrid_api_key).send(message)


SYSTEM_SEVERITY_LABELS = {"critical": "CRITICAL", "warning": "WARNING", "info": "INFO"}


def send_health_alert(to_emails, incident: dict, *, resolved: bool = False) -> None:
    """Email operators about a system-health incident (or its resolution).

    ``to_emails`` is a single address or a list. ``incident`` is a plain dict built
    from a HealthIncident row: title, severity, detail, check_name, diagnosis,
    remediation_status, and a remediation dict. All dynamic values are HTML-escaped
    — the diagnosis is model-generated, so treat it as untrusted (OWASP LLM05).
    """
    if not settings.transactional_email_enabled:
        return
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    severity = SYSTEM_SEVERITY_LABELS.get(incident.get("severity"), str(incident.get("severity", "")).upper())
    title = html.escape(incident.get("title") or "System health incident")
    detail = html.escape(incident.get("detail") or "")
    diagnosis = html.escape(incident.get("diagnosis") or "")
    rem_status = html.escape(str(incident.get("remediation_status") or "none"))

    actions = (incident.get("remediation") or {}).get("actions") or []
    actions_html = ""
    if actions:
        items = "".join(
            f"<li>{html.escape(a.get('tool', ''))}: {html.escape(json.dumps(a.get('result', {})))}</li>"
            for a in actions
        )
        actions_html = f"<h3>Automated actions taken</h3><ul>{items}</ul>"

    monitoring_url = f"{settings.frontend_url}/monitoring"
    heading = "Resolved" if resolved else f"{severity} system alert"
    color = "#16a34a" if resolved else ("#b91c1c" if severity == "CRITICAL" else "#b45309")

    diagnosis_html = f"<h3>Agent diagnosis</h3><p>{diagnosis}</p>" if diagnosis else ""

    html_body = f"""
<div style="font-family:sans-serif;max-width:560px;margin:0 auto">
  <h2 style="color:{color}">SafeMail — {html.escape(heading)}</h2>
  <p><strong>{title}</strong></p>
  <p>{detail}</p>
  {diagnosis_html}
  <p><strong>Remediation status:</strong> {rem_status}</p>
  {actions_html}
  <p style="margin:24px 0">
    <a href="{monitoring_url}"
       style="background:#2563eb;color:#fff;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:600">
      Open the monitoring console
    </a>
  </p>
  <p style="color:#64748b;font-size:13px">This is an automated message from SafeMail's self-monitoring system.</p>
</div>"""

    subject_prefix = "[SafeMail] Resolved" if resolved else f"[SafeMail] {severity}"
    message = Mail(
        from_email=settings.email_from,
        to_emails=to_emails,
        subject=f"{subject_prefix} — {incident.get('title') or 'system health'}",
        html_content=html_body,
    )
    SendGridAPIClient(settings.sendgrid_api_key).send(message)


def send_push_notification(fcm_token: str, child_name: str, alert: dict) -> None:
    if not settings.fcm_service_account_json or not fcm_token:
        return

    import firebase_admin
    from firebase_admin import credentials, messaging

    if not firebase_admin._apps:
        cred = credentials.Certificate(json.loads(settings.fcm_service_account_json))
        firebase_admin.initialize_app(cred)

    msg = messaging.Message(
        token=fcm_token,
        notification=messaging.Notification(
            title=f"Alert for {child_name}",
            body=alert["ai_summary"][:100],
        ),
        data={
            "alert_id": str(alert["id"]),
            "severity": alert["severity"],
            "category": alert["category"],
            "child_name": child_name,
        },
        android=messaging.AndroidConfig(priority="high"),
        apns=messaging.APNSConfig(headers={"apns-priority": "10"}),
    )
    messaging.send(msg)
