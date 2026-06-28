"""Gmail / Google implementation of EmailProvider.

This is the existing Gmail logic (previously in app/services/gmail.py and the
OAuth bits in app/routers/auth.py) moved behind the provider interface, with no
behavior change.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone, timedelta

import httpx
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import Flow

from app.config import get_settings
from app.services.email_providers.base import EmailProvider

settings = get_settings()

GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# Full scopes requested at consent (read mail + identify the account's address).
OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]
# The Gmail API service client itself only needs read access.
_SERVICE_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _client_config() -> dict:
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uris": [settings.google_redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": GOOGLE_TOKEN_URI,
        }
    }


class GmailProvider(EmailProvider):
    name = "google"

    # ── OAuth / connect flow ──────────────────────────────────────────────────
    def authorization_url(self, state: str, redirect_uri: str) -> str:
        flow = Flow.from_client_config(_client_config(), scopes=OAUTH_SCOPES, redirect_uri=redirect_uri)
        auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent", state=state)
        return auth_url

    def exchange_code(self, code: str, state: str, redirect_uri: str) -> tuple[str, str, datetime, str]:
        flow = Flow.from_client_config(
            _client_config(), scopes=OAUTH_SCOPES, redirect_uri=redirect_uri, state=state,
        )
        flow.fetch_token(code=code)
        creds = flow.credentials
        userinfo = build("oauth2", "v2", credentials=creds, cache_discovery=False)
        email = userinfo.userinfo().get().execute()["email"]
        expiry = creds.expiry or (datetime.now(timezone.utc) + timedelta(hours=1))
        return creds.token, creds.refresh_token, expiry, email

    # ── Ingestion ─────────────────────────────────────────────────────────────
    def build_client(self, access_token: str, refresh_token: str):
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=GOOGLE_TOKEN_URI,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=_SERVICE_SCOPES,
        )
        return creds, build("gmail", "v1", credentials=creds, cache_discovery=False)

    def refresh_if_needed(self, creds) -> tuple[str, str, datetime]:
        if creds.expired or creds.expiry is None:
            creds.refresh(Request())
        return creds.token, creds.refresh_token, creds.expiry or (datetime.now(timezone.utc) + timedelta(hours=1))

    def list_message_ids(self, client, max_results: int = 50) -> list[str]:
        result = client.users().messages().list(
            userId="me", q="in:inbox OR in:sent", maxResults=max_results,
        ).execute()
        return [m["id"] for m in result.get("messages", [])]

    def fetch_message(self, client, message_id: str) -> dict:
        return client.users().messages().get(userId="me", id=message_id, format="full").execute()

    def extract_message_data(self, raw: dict, account_address: str,
                             connection_id: str, child_id: str) -> dict:
        headers = {h["name"].lower(): h["value"] for h in raw.get("payload", {}).get("headers", [])}
        body = _decode_body(raw.get("payload", {}))
        sender = headers.get("from", "")
        direction = "outbound" if account_address.lower() in sender.lower() else "inbound"

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

    def revoke(self, token: str) -> bool:
        """Revoke a Google grant. 200 = success, 400 = already-invalid (both fine)."""
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
