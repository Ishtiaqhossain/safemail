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


def send_alert_email(parent_email: str, child_name: str, alert: dict) -> None:
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


def send_verification_email(to_email: str, verify_url: str) -> None:
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
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    safe_child = html.escape(child_name)
    safe_gmail = html.escape(gmail_address)

    html_body = f"""
<div style="font-family:sans-serif;max-width:480px;margin:0 auto">
  <h2 style="color:#0f172a">Action needed: reconnect {safe_child}'s Gmail</h2>
  <p>SafeMail has lost access to <strong>{safe_gmail}</strong>, so we are no
     longer monitoring {safe_child}'s email. This usually happens when the Google
     permission is revoked or expires.</p>
  <p style="color:#b91c1c;font-weight:600">Until you reconnect, no safety alerts will be sent for this account.</p>
  <p style="margin:24px 0">
    <a href="{reconnect_url}"
       style="background:#2563eb;color:#fff;padding:10px 24px;border-radius:6px;text-decoration:none;font-weight:600">
      Reconnect Gmail
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
