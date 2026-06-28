"""Tests for the email-provider abstraction.

The key guard is that GmailProvider.extract_message_data produces the exact same
message_data dict the pipeline expects (this refactor must not change behavior).
Pure unit tests — no DB, no network.
"""
import base64
from datetime import datetime

import pytest

from app.services.email_providers import get_provider, GmailProvider
from app.services.email_providers.gmail import GmailProvider as GmailProviderImpl


def _raw_message(*, sender: str, to: str, cc: str = "", subject: str = "Hi",
                 body: str = "hello world", msg_id: str = "msg123") -> dict:
    return {
        "id": msg_id,
        "payload": {
            "headers": [
                {"name": "From", "value": sender},
                {"name": "To", "value": to},
                {"name": "Cc", "value": cc},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Wed, 02 Oct 2002 13:00:00 GMT"},
            ],
            "body": {"data": base64.urlsafe_b64encode(body.encode()).decode()},
        },
    }


class TestRegistry:
    def test_google_resolves(self):
        assert isinstance(get_provider("google"), GmailProvider)

    def test_unknown_raises(self):
        with pytest.raises(ValueError):
            get_provider("not_a_provider")


class TestExtractMessageData:
    def test_inbound_message_shape(self):
        raw = _raw_message(sender="friend@example.com", to="kid@gmail.com, other@x.com", cc="cc@x.com")
        data = GmailProviderImpl().extract_message_data(raw, "kid@gmail.com", "conn-1", "child-1")

        assert data == {
            "gmail_message_id": "msg123",
            "gmail_connection_id": "conn-1",
            "child_id": "child-1",
            "direction": "inbound",
            "sender_address": "friend@example.com",
            "recipient_addresses": ["kid@gmail.com", "other@x.com", "cc@x.com"],
            "subject": "Hi",
            "body_text": "hello world",
            "received_at": data["received_at"],  # datetime asserted below
        }
        assert isinstance(data["received_at"], datetime)

    def test_outbound_direction_when_account_is_sender(self):
        raw = _raw_message(sender="Kid <kid@gmail.com>", to="friend@example.com")
        data = GmailProviderImpl().extract_message_data(raw, "kid@gmail.com", "c", "k")
        assert data["direction"] == "outbound"

    def test_subject_truncated_to_80(self):
        raw = _raw_message(sender="a@b.com", to="kid@gmail.com", subject="x" * 200)
        data = GmailProviderImpl().extract_message_data(raw, "kid@gmail.com", "c", "k")
        assert len(data["subject"]) == 80

    def test_missing_headers_safe(self):
        raw = {"id": "m1", "payload": {"headers": [], "body": {}}}
        data = GmailProviderImpl().extract_message_data(raw, "kid@gmail.com", "c", "k")
        assert data["sender_address"] == ""
        assert data["recipient_addresses"] == []
        assert data["body_text"] == ""
        assert data["direction"] == "inbound"


class TestShimDelegates:
    def test_legacy_shim_still_works(self):
        # app/services/gmail.py is a back-compat shim over GmailProvider.
        from app.services import gmail as shim
        raw = _raw_message(sender="a@b.com", to="kid@gmail.com")
        data = shim.extract_message_data(raw, "kid@gmail.com", "c", "k")
        assert data["gmail_message_id"] == "msg123"
        assert callable(shim.revoke_token) and callable(shim.build_gmail_service)
