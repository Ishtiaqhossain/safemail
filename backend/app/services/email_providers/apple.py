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
import html
import imaplib
import re
from datetime import datetime, timezone, timedelta
from email.header import decode_header, make_header
from email.utils import getaddresses

from app.config import get_settings
from app.services.email_providers.base import EmailProvider, ProviderAuthError, ProviderUnavailable
from app.services.email_providers.gmail import _parse_date  # reuse RFC-2822 date parsing

settings = get_settings()

IMAP_HOST = "imap.mail.me.com"
IMAP_PORT = 993
IMAP_TIMEOUT = 30
# Folders we monitor (inbound + outbound), mirroring Gmail's "in:inbox OR in:sent".
# INBOX is required; the Sent folder is best-effort (name varies / may be absent).
_REQUIRED_MAILBOX = "INBOX"
_OPTIONAL_MAILBOXES = ("Sent Messages",)
_SEP = "\x00"


def _no_expiry() -> datetime:
    # An app-specific password has no expiry, but token_expiry is NOT NULL.
    return datetime.now(timezone.utc) + timedelta(days=3650)


class _StaticCreds:
    """Stand-in for an OAuth credentials object — IMAP has nothing to refresh."""
    expired = False

    def __init__(self, token: str, refresh_token: str):
        self.token = token
        self.refresh_token = refresh_token
        self.expiry = _no_expiry()


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
            raise ProviderAuthError(
                "Could not sign in to iCloud Mail. Check the email address and the "
                "app-specific password (generate one at appleid.apple.com)."
            )
        except OSError:
            raise ProviderUnavailable("Could not reach iCloud Mail right now. Please try again.")
        finally:
            if client is not None:
                try:
                    client.logout()
                except Exception:
                    pass
        return secret, "", _no_expiry(), account_address

    # ── Ingestion ────────────────────────────────────────────────────────────────
    def build_client(self, access_token: str, refresh_token: str | None = None,
                     account_address: str | None = None):
        try:
            client = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=IMAP_TIMEOUT)
        except OSError as e:
            raise ProviderUnavailable(f"Could not reach iCloud Mail: {e}")
        try:
            client.login(account_address, access_token)
        except imaplib.IMAP4.error as e:
            self._safe_logout(client)
            raise ProviderAuthError(f"iCloud login failed: {e}")
        except OSError as e:
            self._safe_logout(client)
            raise ProviderUnavailable(f"Could not reach iCloud Mail: {e}")
        return _StaticCreds(access_token, refresh_token or ""), client

    def refresh_if_needed(self, creds) -> tuple[str, str, datetime]:
        return creds.token, creds.refresh_token, creds.expiry  # nothing to refresh

    def list_message_ids(self, client, max_results: int = 50) -> list[str]:
        # INBOX is required — let failures propagate to the poller (retry / error).
        ids = self._mailbox_ids(client, _REQUIRED_MAILBOX, max_results)
        # Sent is best-effort: a missing/renamed folder must not blank out the poll.
        for mailbox in _OPTIONAL_MAILBOXES:
            try:
                ids += self._mailbox_ids(client, mailbox, max_results)
            except Exception:
                continue
        return ids

    def _mailbox_ids(self, client, mailbox: str, max_results: int) -> list[str]:
        typ, _ = client.select(f'"{mailbox}"', readonly=True)
        if typ != "OK":
            raise ProviderUnavailable(f"IMAP select failed for {mailbox}: {typ}")
        uidv = self._uidvalidity(client)
        typ, data = client.uid("search", None, "ALL")
        if typ != "OK":
            raise ProviderUnavailable(f"IMAP search failed for {mailbox}: {typ}")
        uids = data[0].split() if data and data[0] else []
        # Dedup id carries mailbox + UIDVALIDITY + UID; combined with the per-
        # connection namespace in ingestion this is globally unique and survives
        # UIDVALIDITY changes.
        return [f"{mailbox}{_SEP}{uidv}{_SEP}{uid.decode()}" for uid in uids[-max_results:]]

    @staticmethod
    def _uidvalidity(client) -> str:
        try:
            _, data = client.response("UIDVALIDITY")
            if data and data[0]:
                return data[0].decode() if isinstance(data[0], bytes) else str(data[0])
        except Exception:
            pass
        return "0"

    def fetch_message(self, client, message_id: str) -> dict:
        mailbox, _uidv, uid = message_id.split(_SEP, 2)
        typ, _ = client.select(f'"{mailbox}"', readonly=True)
        if typ != "OK":
            raise ProviderUnavailable(f"IMAP select failed for {mailbox}: {typ}")
        # BODY.PEEK[] fetches the full RFC822 message without setting \Seen.
        typ, data = client.uid("fetch", uid, "(BODY.PEEK[])")
        if typ != "OK" or not data or not data[0]:
            raise ProviderUnavailable(f"IMAP fetch failed for {message_id}")
        return {"rfc822": data[0][1], "uid": uid, "mailbox": mailbox}

    def extract_message_data(self, raw: dict, account_address: str,
                             connection_id: str, child_id: str) -> dict:
        msg = email.message_from_bytes(raw["rfc822"])
        sender = msg.get("From", "") or ""
        from_addrs = [addr.lower() for _, addr in getaddresses([sender]) if addr]
        direction = "outbound" if account_address.lower() in from_addrs else "inbound"
        recipients = [addr for _, addr in getaddresses([msg.get("To", ""), msg.get("Cc", "")]) if addr]
        message_id = msg.get("Message-ID") or f"imap-{raw.get('mailbox','')}-{raw.get('uid','')}"

        return {
            "gmail_message_id": message_id,
            "gmail_connection_id": connection_id,
            "child_id": child_id,
            "direction": direction,
            "sender_address": sender,
            "recipient_addresses": recipients,
            "subject": _decode_header(msg.get("Subject", "") or "")[:80],
            "body_text": _extract_text(msg)[: settings.max_body_length],
            "received_at": _parse_date(msg.get("Date")),
        }

    def revoke(self, token: str) -> bool:
        # An app-specific password can only be revoked by the user at
        # appleid.apple.com; deleting the connection stops our access. No-op here.
        return True

    def close(self, client) -> None:
        self._safe_logout(client)

    @staticmethod
    def _safe_logout(client) -> None:
        try:
            client.logout()
        except Exception:
            pass


def _decode_header(value: str) -> str:
    """Decode RFC 2047 encoded-word headers (e.g. =?UTF-8?B?...?=)."""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _decode_payload(part: email.message.Message) -> str:
    payload = part.get_payload(decode=True)
    if not payload:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace")


def _extract_text(msg: email.message.Message) -> str:
    """Prefer text/plain; fall back to stripped text/html (common for iCloud mail)."""
    plain, html_body = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_filename():
                continue
            ctype = part.get_content_type()
            if ctype == "text/plain" and not plain:
                plain = _decode_payload(part)
            elif ctype == "text/html" and not html_body:
                html_body = _decode_payload(part)
    elif msg.get_content_type() == "text/html":
        html_body = _decode_payload(msg)
    else:
        plain = _decode_payload(msg)

    if plain.strip():
        return plain
    if html_body.strip():
        return _strip_html(html_body)
    return plain or html_body


def _strip_html(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return html.unescape(re.sub(r"\s+", " ", s)).strip()
