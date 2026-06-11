import base64
from datetime import datetime, timezone, timedelta

import httpx
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from app.config import get_settings

settings = get_settings()

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"


def revoke_token(token: str) -> bool:
    """Revoke a Google OAuth grant. Passing a refresh token revokes the whole
    grant (and its access tokens). Best-effort: returns True on success, False
    on any failure so callers can proceed with local deletion regardless.

    Google returns 200 on success and 400 for an already-invalid/expired token —
    both mean the grant no longer works, so we treat 400 as success too.
    """
    try:
        resp = httpx.post(
            GOOGLE_REVOKE_URL,
            data={"token": token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10.0,
        )
        return resp.status_code in (200, 400)
    except Exception:
        return False


def build_gmail_service(access_token: str, refresh_token: str):
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=SCOPES,
    )
    return creds, build("gmail", "v1", credentials=creds, cache_discovery=False)


def refresh_if_needed(creds: Credentials) -> tuple[str, str, datetime]:
    if creds.expired or creds.expiry is None:
        creds.refresh(Request())
    return creds.token, creds.refresh_token, creds.expiry or (datetime.now(timezone.utc) + timedelta(hours=1))


def list_message_ids(service, max_results: int = 50) -> list[str]:
    result = service.users().messages().list(
        userId="me",
        q="in:inbox OR in:sent",
        maxResults=max_results,
    ).execute()
    return [m["id"] for m in result.get("messages", [])]


def fetch_message(service, message_id: str) -> dict:
    return service.users().messages().get(userId="me", id=message_id, format="full").execute()


def extract_message_data(raw: dict, gmail_address: str, connection_id: str, child_id: str) -> dict:
    headers = {h["name"].lower(): h["value"] for h in raw.get("payload", {}).get("headers", [])}
    body = _decode_body(raw.get("payload", {}))
    sender = headers.get("from", "")
    direction = "outbound" if gmail_address.lower() in sender.lower() else "inbound"

    recipients = [
        a.strip()
        for part in [headers.get("to", ""), headers.get("cc", "")]
        for a in part.split(",")
        if a.strip()
    ]

    return {
        "gmail_message_id": raw["id"],
        "gmail_connection_id": connection_id,
        "child_id": child_id,
        "direction": direction,
        "sender_address": sender,
        "recipient_addresses": recipients,
        "subject": headers.get("subject", "")[:80],
        "body_text": body[: settings.max_body_length],
        "received_at": _parse_date(headers.get("date")),
    }


def _decode_body(payload: dict) -> str:
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
    return ""


def _parse_date(date_str: str | None) -> datetime:
    if not date_str:
        return datetime.now(timezone.utc)
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except Exception:
        return datetime.now(timezone.utc)
