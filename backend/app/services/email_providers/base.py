"""Provider-agnostic interface for an inbound email source.

Each concrete provider (Gmail today; Outlook/IMAP/etc. in future) implements this
Strategy so the ingestion loop and the OAuth connect flow stay provider-neutral.

The one hard contract is ``extract_message_data``: it MUST return a dict with the
exact keys the rest of the pipeline consumes (see GmailProvider / the Alert model
and app/services/analysis.py). Keys: gmail_message_id, gmail_connection_id,
child_id, direction, sender_address, recipient_addresses, subject, body_text,
received_at. (The "gmail_" key names are a legacy naming choice kept to avoid a
large rename — they're just identifiers, not Gmail-specific semantics.)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class EmailProvider(ABC):
    #: Stable provider key stored on the connection row (e.g. "google").
    name: str

    # ── OAuth / connect flow ──────────────────────────────────────────────────
    @abstractmethod
    def authorization_url(self, state: str, redirect_uri: str) -> str:
        """Build the provider's OAuth consent URL with the signed state embedded."""

    @abstractmethod
    def exchange_code(self, code: str, state: str, redirect_uri: str) -> tuple[str, str, datetime, str]:
        """Exchange an OAuth code for tokens. Returns
        (access_token, refresh_token, token_expiry, account_email)."""

    # ── Ingestion ─────────────────────────────────────────────────────────────
    @abstractmethod
    def build_client(self, access_token: str, refresh_token: str):
        """Return ``(credentials, client)`` for the provider's API."""

    @abstractmethod
    def refresh_if_needed(self, creds) -> tuple[str, str, datetime]:
        """Refresh the access token if expired. Returns
        (access_token, refresh_token, token_expiry)."""

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
