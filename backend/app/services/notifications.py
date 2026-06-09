import json
from app.config import get_settings

settings = get_settings()

SEVERITY_LABELS = {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM", "low": "LOW"}
CATEGORY_LABELS = {
    "self_harm": "Self-Harm",
    "grooming": "Grooming",
    "bullying": "Bullying / Harassment",
    "drugs_alcohol": "Drugs / Alcohol",
    "stranger_contact": "Stranger Contact",
    "personal_info_sharing": "Personal Information Sharing",
}


def send_alert_email(parent_email: str, child_name: str, alert: dict) -> None:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    severity = SEVERITY_LABELS.get(alert["severity"], alert["severity"].upper())
    category = CATEGORY_LABELS.get(alert["category"], alert["category"])

    html = f"""
<h2>SafeMail Safety Alert</h2>
<p><strong>Severity:</strong> {severity}<br>
<strong>Category:</strong> {category}<br>
<strong>Child:</strong> {child_name}</p>
<h3>What we found</h3>
<p>{alert["ai_summary"]}</p>
<h3>Suggested next step</h3>
<p>{alert.get("ai_response_script") or "Review the email in your child's Gmail account."}</p>
<p><em>We do not include the original email in this alert to protect your child's privacy.</em></p>
"""

    message = Mail(
        from_email="alerts@safemail.com",
        to_emails=parent_email,
        subject=f"[SafeMail] {severity} Alert — {child_name}'s Email",
        html_content=html,
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
