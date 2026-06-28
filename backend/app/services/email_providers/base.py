"""Provider-agnostic interface for an inbound email source.

Each concrete provider (Gmail, Apple/iCloud; Outlook/etc. in future) implements
this Strategy so the ingestion loop and the connect flow stay provider-neutral.

Two auth models are supported (``auth_kind``):
- ``"oauth"``      — redirect flow: ``authorization_url`` + ``exchange_code`` (Gmail).
- ``"credentials"`` — the parent supplies an address + secret (e.g. an IMAP
  app-specific password): ``connect_with_credentials`` (Apple/iCloud).

The one hard contract is ``extract_message_data``: it MUST return a dict with the
exact keys the rest of the pipeline consumes (see the Alert model and
app/services/analysis.py): gmail_message_id, gmail_connection_id, child_id,
direction, sender_address, recipient_addresses, subject, body_text, received_at.
(The "gmail_" key names are legacy identifiers kept to avoid a large rename — they
carry no Gmail-specific meaning.)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class ProviderAuthError(Exception):
    """Credentials are bad / the grant is revoked — the parent must reconnect.
    The ingestion loop flips the connection to 'error' and emails the parent;
    the connect endpoint maps it to HTTP 400."""


class ProviderUnavailable(Exception):
    """A transient failure reaching the provider (DNS/TLS/timeout/5xx) — retry.
    The connect endpoint maps it to HTTP 503; ingestion retries."""


class EmailProvider(ABC):
    #: Stable provider key stored on the connection row (e.g. "google", "apple").
    name: str
    #: "oauth" | "credentials" — which connect flow this provider uses.
    auth_kind: str = "oauth"

    # ── OAuth connect flow (override for auth_kind == "oauth") ─────────────────
    def authorization_url(self, state: str, redirect_uri: str) -> str:
        raise NotImplementedError(f"{self.name!r} is not an OAuth provider")

    def exchange_code(self, code: str, state: str, redirect_uri: str) -> tuple[str, str, datetime, str]:
        raise NotImplementedError(f"{self.name!r} is not an OAuth provider")

    # ── Credentials connect flow (override for auth_kind == "credentials") ─────
    def connect_with_credentials(self, account_address: str, secret: str) -> tuple[str, str, datetime, str]:
        """Validate the supplied credentials and return what to store:
        (access_token, refresh_token, token_expiry, account_email).
        Raise ValueError with a user-facing message on bad credentials."""
        raise NotImplementedError(f"{self.name!r} is not a credentials provider")

    # ── Ingestion (all providers implement) ────────────────────────────────────
    @abstractmethod
    def build_client(self, access_token: str, refresh_token: str | None = None,
                     account_address: str | None = None):
        """Return ``(credentials, client)`` for the provider's API/connection."""

    @abstractmethod
    def refresh_if_needed(self, creds) -> tuple[str, str, datetime]:
        """Refresh the access token if expired. Returns
        (access_token, refresh_token, token_expiry) — unchanged when no refresh."""

    @abstractmethod
    def list_message_ids(self, client, max_results: int = 50) -> list[str]:
        """Recent message ids from the monitored folders."""

    @abstractmethod
    def fetch_message(self, client, message_id: str) -> dict:
        """Fetch one raw message by id."""

    @abstractmethod
    def extract_message_data(self, raw: dict, account_address: str,
                             connection_id: str, child_id: str) -> dict:
        """Normalize a raw message into the canonical message_data dict."""

    @abstractmethod
    def revoke(self, token: str) -> bool:
        """Best-effort revoke of the grant. True on success (or already-invalid)."""

    def close(self, client) -> None:
        """Release any persistent connection (e.g. IMAP logout). Default no-op
        for stateless HTTP clients like Gmail."""
        return None
