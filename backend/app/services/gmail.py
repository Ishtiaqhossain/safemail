"""Backward-compatibility shim.

The Gmail logic now lives in ``app/services/email_providers/gmail.py``
(``GmailProvider``). These module-level functions are kept so existing imports
keep working; new code should use ``app.services.email_providers.get_provider``.
"""
from app.services.email_providers.gmail import (  # noqa: F401
    GmailProvider, _decode_body, _parse_date, GOOGLE_REVOKE_URL,
)

_provider = GmailProvider()


def build_gmail_service(access_token: str, refresh_token: str):
    return _provider.build_client(access_token, refresh_token)


def refresh_if_needed(creds):
    return _provider.refresh_if_needed(creds)


def list_message_ids(service, max_results: int = 50) -> list[str]:
    return _provider.list_message_ids(service, max_results)


def fetch_message(service, message_id: str) -> dict:
    return _provider.fetch_message(service, message_id)


def extract_message_data(raw: dict, gmail_address: str, connection_id: str, child_id: str) -> dict:
    return _provider.extract_message_data(raw, gmail_address, connection_id, child_id)


def revoke_token(token: str) -> bool:
    return _provider.revoke(token)
