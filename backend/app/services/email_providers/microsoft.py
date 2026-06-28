"""Microsoft (Outlook.com / Microsoft 365) implementation of EmailProvider.

OAuth via the Microsoft identity platform (``common`` tenant — covers personal
Outlook.com and work/school M365), read-only mail via Microsoft Graph
(``Mail.Read``). Implemented with httpx only (no new dependency).

Access tokens are short-lived; we refresh via the stored refresh token
(``offline_access`` scope) when the access token is near expiry.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode, quote

import httpx

from app.config import get_settings
from app.services.email_providers.base import EmailProvider, ProviderAuthError, ProviderUnavailable
from app.services.email_providers._html import strip_html

settings = get_settings()

_AUTHORITY = "https://login.microsoftonline.com/common/oauth2/v2.0"
AUTHORIZE_URL = f"{_AUTHORITY}/authorize"
TOKEN_URL = f"{_AUTHORITY}/token"
GRAPH = "https://graph.microsoft.com/v1.0"
# User.Read is required for the GET /me lookup; Mail.Read is the read-only mailbox scope.
SCOPES = ("openid email offline_access "
          "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/User.Read")
HTTP_TIMEOUT = 30.0
_SELECT = "internetMessageId,subject,from,toRecipients,ccRecipients,receivedDateTime,body"
_FOLDERS = ("inbox", "sentitems")  # inbound + outbound, mirroring Gmail's inbox OR sent
_SEP = "\x00"  # joins folder + Graph id in the message token so direction is reliable
_REFRESH_SKEW = timedelta(seconds=120)  # refresh slightly before the token actually expires


class _MSCreds:
    """Carries the stored tokens + expiry so refresh_if_needed can skip the refresh
    round-trip while the access token is still comfortably valid."""

    def __init__(self, access: str, refresh: str, expiry: datetime | None = None):
        self.token = access
        self.refresh_token = refresh
        self.expiry = expiry


class MicrosoftProvider(EmailProvider):
    name = "microsoft"
    auth_kind = "oauth"

    # ── OAuth / connect flow ──────────────────────────────────────────────────
    def authorization_url(self, state: str, redirect_uri: str) -> str:
        self._require_config()
        params = {
            "client_id": settings.microsoft_client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": SCOPES,
            "state": state,
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    def oauth_redirect_uri(self) -> str:
        return settings.microsoft_redirect_uri

    def exchange_code(self, code: str, state: str, redirect_uri: str) -> tuple[str, str, datetime, str]:
        data = self._token_request({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "scope": SCOPES,
        })
        access = data["access_token"]
        refresh = data.get("refresh_token", "")
        expiry = datetime.now(timezone.utc) + timedelta(seconds=int(data.get("expires_in", 3600)))
        email = self._account_email(access)
        return access, refresh, expiry, email

    # ── Ingestion ─────────────────────────────────────────────────────────────
    def build_client(self, access_token: str, refresh_token: str | None = None,
                     account_address: str | None = None, token_expiry: datetime | None = None):
        client = httpx.Client(
            base_url=GRAPH,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=HTTP_TIMEOUT,
        )
        return _MSCreds(access_token, refresh_token or "", token_expiry), client

    def refresh_if_needed(self, creds) -> tuple[str, str, datetime]:
        # Skip the token round-trip while the current access token is still valid.
        if creds.expiry is not None:
            exp = creds.expiry if creds.expiry.tzinfo else creds.expiry.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) < exp - _REFRESH_SKEW:
                return creds.token, creds.refresh_token, creds.expiry
        data = self._token_request({
            "grant_type": "refresh_token",
            "refresh_token": creds.refresh_token,
            "scope": SCOPES,
        })
        access = data["access_token"]
        refresh = data.get("refresh_token") or creds.refresh_token
        expiry = datetime.now(timezone.utc) + timedelta(seconds=int(data.get("expires_in", 3600)))
        return access, refresh, expiry

    def list_message_ids(self, client, max_results: int = 50) -> list[str]:
        ids: list[str] = []
        for folder in _FOLDERS:
            # $orderby newest-first so $top keeps the most recent mail, not an arbitrary page.
            r = client.get(f"/me/mailFolders/{folder}/messages",
                           params={"$top": max_results, "$orderby": "receivedDateTime desc",
                                   "$select": "id"})
            self._raise_for_graph(r)
            # Encode the folder into the token so direction can be inferred reliably downstream.
            ids += [f"{folder}{_SEP}{m['id']}" for m in r.json().get("value", [])]
        return ids

    def fetch_message(self, client, message_id: str) -> dict:
        folder, _, gid = message_id.partition(_SEP)
        # Graph message ids can contain '/', '+', '=' — encode so they stay a single path segment.
        r = client.get(f"/me/messages/{quote(gid, safe='')}", params={"$select": _SELECT})
        self._raise_for_graph(r)
        data = r.json()
        data["_folder"] = folder
        return data

    def extract_message_data(self, raw: dict, account_address: str,
                             connection_id: str, child_id: str) -> dict:
        sender = ((raw.get("from") or {}).get("emailAddress") or {}).get("address", "") or ""
        recipients = [
            addr for key in ("toRecipients", "ccRecipients")
            for r in (raw.get(key) or [])
            if (addr := ((r.get("emailAddress") or {}).get("address")))
        ]
        body = raw.get("body") or {}
        content = body.get("content", "") or ""
        body_text = strip_html(content) if body.get("contentType") == "html" else content

        # Folder is authoritative (handles work/school accounts where the stored
        # address is the UPN but messages carry the primary SMTP); fall back to
        # address comparison when the folder hint is absent.
        is_outbound = raw.get("_folder") == "sentitems" or account_address.lower() == sender.lower()

        return {
            "gmail_message_id": raw.get("internetMessageId") or raw.get("id"),
            "gmail_connection_id": connection_id,
            "child_id": child_id,
            "direction": "outbound" if is_outbound else "inbound",
            "sender_address": sender,
            "recipient_addresses": recipients,
            "subject": (raw.get("subject", "") or "")[:80],
            "body_text": body_text[: settings.max_body_length],
            "received_at": _parse_iso(raw.get("receivedDateTime")),
        }

    def revoke(self, token: str) -> bool:
        # No simple revoke for a delegated Graph token; deleting the connection
        # stops our access. The user can revoke app access at myaccount.microsoft.com.
        return True

    def close(self, client) -> None:
        try:
            client.close()
        except Exception:
            pass

    # ── Internals ──────────────────────────────────────────────────────────────
    def _require_config(self) -> None:
        if not settings.microsoft_client_id or not settings.microsoft_client_secret:
            raise ProviderUnavailable("Microsoft connections are not configured on this server.")

    def _token_request(self, extra: dict) -> dict:
        self._require_config()
        form = {
            "client_id": settings.microsoft_client_id,
            "client_secret": settings.microsoft_client_secret,
            **extra,
        }
        try:
            r = httpx.post(TOKEN_URL, data=form, timeout=HTTP_TIMEOUT)
        except Exception as e:
            raise ProviderUnavailable(f"Could not reach Microsoft: {e}")
        if r.status_code != 200:
            err = ""
            try:
                err = r.json().get("error", "")
            except Exception:
                pass
            # Bad/expired grant or consent issues → the user must reconnect.
            if err in ("invalid_grant", "invalid_client", "unauthorized_client", "interaction_required"):
                raise ProviderAuthError(f"Microsoft sign-in failed ({err or r.status_code}). Please reconnect.")
            raise ProviderUnavailable(f"Microsoft token request failed ({r.status_code}).")
        return r.json()

    def _account_email(self, access_token: str) -> str:
        try:
            r = httpx.get(f"{GRAPH}/me", headers={"Authorization": f"Bearer {access_token}"},
                          timeout=HTTP_TIMEOUT)
        except Exception as e:
            raise ProviderUnavailable(f"Could not reach Microsoft Graph: {e}")
        self._raise_for_graph(r)
        me = r.json()
        return me.get("mail") or me.get("userPrincipalName") or ""

    @staticmethod
    def _raise_for_graph(resp: httpx.Response) -> None:
        if resp.status_code == 401:
            raise ProviderAuthError("Microsoft access was revoked or expired. Please reconnect.")
        if resp.status_code >= 400:
            raise ProviderUnavailable(f"Microsoft Graph error ({resp.status_code}).")


def _parse_iso(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)
