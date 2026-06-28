"""Apple / iCloud Mail implementation of EmailProvider.

iCloud Mail has no third-party OAuth, so this is a credentials provider: the
parent supplies the child's iCloud address + an **app-specific password**
(generated at appleid.apple.com). We connect over IMAP, read-only (EXAMINE +
BODY.PEEK so we never set the \\Seen flag), and normalize messages into the same
message_data shape Gmail produces.

The app-specific password is stored Fernet-encrypted in the connection's
access_token (the same at-rest protection as OAuth tokens). It does not expire,
so refresh is a no-op; "revoke" is best-effort (the password can only be revoked
by the user at appleid.apple.com — deleting the connection stops our access).
"""
from __future__ import annotations

import email
import imaplib
from datetime import datetime, timezone, timedelta
from email.utils import getaddresses

from app.config import get_settings
from app.services.email_providers.base import EmailProvider
from app.services.email_providers.gmail import _parse_date  # reuse RFC-2822 date parsing

settings = get_settings()

IMAP_HOST = "imap.mail.me.com"
IMAP_PORT = 993
IMAP_TIMEOUT = 30
# Far-future expiry: an app-specific password has no expiry, but token_expiry is
# NOT NULL on the model.
_NO_EXPIRY = lambda: datetime.now(timezone.utc) + timedelta(days=3650)  # noqa: E731
# Folders we monitor (inbound + outbound), mirroring Gmail's "in:inbox OR in:sent".
_MAILBOXES = ("INBOX", "Sent Messages")
_UID_SEP = "\x00"


class _StaticCreds:
    """Stand-in for an OAuth credentials object — IMAP has nothing to refresh."""
    expired = False

    def __init__(self, token: str, refresh_token: str):
        self.token = token
        self.refresh_token = refresh_token
        self.expiry = _NO_EXPIRY()


class AppleMailProvider(EmailProvider):
    name = "apple"
    auth_kind = "credentials"

    # ── Connect ────────────────────────────────────────────────────────────────
    def connect_with_credentials(self, account_address: str, secret: str) -> tuple[str, str, datetime, str]:
        client = None
        try:
            client = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=IMAP_TIMEOUT)
            client.login(account_address, secret)
        except imaplib.IMAP4.error:
            raise ValueError(
                "Could not sign in to iCloud Mail. Check the email address and the "
                "app-specific password (generate one at appleid.apple.com)."
            )
        except Exception:
            raise ValueError("Could not reach iCloud Mail right now. Please try again.")
        finally:
            if client is not None:
                try:
                    client.logout()
                except Exception:
                    pass
        return secret, "", _NO_EXPIRY(), account_address

    # ── Ingestion ────────────────────────────────────────────────────────────────
    def build_client(self, access_token: str, refresh_token: str | None = None,
                     account_address: str | None = None):
        client = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=IMAP_TIMEOUT)
        client.login(account_address, access_token)
        return _StaticCreds(access_token, refresh_token or ""), client

    def refresh_if_needed(self, creds) -> tuple[str, str, datetime]:
        # Nothing to refresh for an app-specific password.
        return creds.token, creds.refresh_token, creds.expiry

    def list_message_ids(self, client, max_results: int = 50) -> list[str]:
        ids: list[str] = []
        for mailbox in _MAILBOXES:
            try:
                typ, _ = client.select(f'"{mailbox}"', readonly=True)
                if typ != "OK":
                    continue
                typ, data = client.uid("search", None, "ALL")
                if typ != "OK" or not data or not data[0]:
                    continue
                for uid in data[0].split()[-max_results:]:
                    ids.append(f"{mailbox}{_UID_SEP}{uid.decode()}")
            except Exception:
                continue
        return ids

    def fetch_message(self, client, message_id: str) -> dict:
        mailbox, uid = message_id.split(_UID_SEP, 1)
        client.select(f'"{mailbox}"', readonly=True)
        # BODY.PEEK[] fetches the full RFC822 message without setting \Seen.
        typ, data = client.uid("fetch", uid, "(BODY.PEEK[])")
        if typ != "OK" or not data or not data[0]:
            raise RuntimeError(f"IMAP fetch failed for {message_id}")
        return {"rfc822": data[0][1], "uid": uid, "mailbox": mailbox}

    def extract_message_data(self, raw: dict, account_address: str,
                             connection_id: str, child_id: str) -> dict:
        msg = email.message_from_bytes(raw["rfc822"])
        sender = msg.get("From", "") or ""
        direction = "outbound" if account_address.lower() in sender.lower() else "inbound"
        recipients = [addr for _, addr in getaddresses([msg.get("To", ""), msg.get("Cc", "")]) if addr]
        message_id = msg.get("Message-ID") or f"imap-{raw.get('mailbox','')}-{raw.get('uid','')}"

        return {
            "gmail_message_id": message_id,
            "gmail_connection_id": connection_id,
            "child_id": child_id,
            "direction": direction,
            "sender_address": sender,
            "recipient_addresses": recipients,
            "subject": (msg.get("Subject", "") or "")[:80],
            "body_text": _extract_text(msg)[: settings.max_body_length],
            "received_at": _parse_date(msg.get("Date")),
        }

    def revoke(self, token: str) -> bool:
        # An app-specific password can only be revoked by the user at
        # appleid.apple.com; deleting the connection stops our access. No-op here.
        return True


def _extract_text(msg: email.message.Message) -> str:
    """First text/plain part (mirrors Gmail's text/plain-only body extraction)."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
        return ""
    payload = msg.get_payload(decode=True)
    if payload:
        return payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")
    return ""
