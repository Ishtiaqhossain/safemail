"""Tests for the email-provider abstraction.

The key guard is that GmailProvider.extract_message_data produces the exact same
message_data dict the pipeline expects (this refactor must not change behavior).
Pure unit tests — no DB, no network.
"""
import base64
import imaplib
from datetime import datetime
from email.message import EmailMessage

import pytest

from app.services.email_providers import get_provider, GmailProvider
from app.services.email_providers.gmail import GmailProvider as GmailProviderImpl
from app.services.email_providers import apple as apple_mod
from app.services.email_providers.apple import AppleMailProvider
from app.services.email_providers import microsoft as ms_mod
from app.services.email_providers.microsoft import MicrosoftProvider
from app.services.email_providers.base import ProviderAuthError


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


def _rfc822(*, sender: str, to: str, subject: str = "Hi", body: str = "hello world",
            msg_id: str | None = "<abc@example.com>") -> bytes:
    m = EmailMessage()
    m["From"] = sender
    m["To"] = to
    m["Subject"] = subject
    m["Date"] = "Wed, 02 Oct 2002 13:00:00 GMT"
    if msg_id:
        m["Message-ID"] = msg_id
    m.set_content(body)
    return m.as_bytes()


class TestAppleProvider:
    def test_registry_and_auth_kind(self):
        p = get_provider("apple")
        assert isinstance(p, AppleMailProvider)
        assert p.auth_kind == "credentials"

    def test_extract_message_data_inbound_matches_canonical_shape(self):
        raw = {"rfc822": _rfc822(sender="friend@example.com", to="kid@icloud.com, other@x.com"),
               "uid": "5", "mailbox": "INBOX"}
        d = AppleMailProvider().extract_message_data(raw, "kid@icloud.com", "conn-1", "child-1")

        assert d["gmail_message_id"] == "<abc@example.com>"
        assert d["gmail_connection_id"] == "conn-1"
        assert d["child_id"] == "child-1"
        assert d["direction"] == "inbound"
        assert d["sender_address"] == "friend@example.com"
        assert d["recipient_addresses"] == ["kid@icloud.com", "other@x.com"]
        assert d["subject"] == "Hi"
        assert "hello world" in d["body_text"]
        assert isinstance(d["received_at"], datetime)
        # Same key set Gmail produces.
        assert set(d.keys()) == {
            "gmail_message_id", "gmail_connection_id", "child_id", "direction",
            "sender_address", "recipient_addresses", "subject", "body_text", "received_at",
        }

    def test_outbound_direction_when_account_is_sender(self):
        raw = {"rfc822": _rfc822(sender="Kid <kid@icloud.com>", to="friend@example.com"),
               "uid": "1", "mailbox": "Sent Messages"}
        d = AppleMailProvider().extract_message_data(raw, "kid@icloud.com", "c", "k")
        assert d["direction"] == "outbound"

    def test_missing_message_id_falls_back_to_uid(self):
        raw = {"rfc822": _rfc822(sender="a@b.com", to="kid@icloud.com", msg_id=None),
               "uid": "42", "mailbox": "INBOX"}
        d = AppleMailProvider().extract_message_data(raw, "kid@icloud.com", "c", "k")
        assert d["gmail_message_id"] == "imap-INBOX-42"

    def test_connect_with_credentials_success(self, monkeypatch):
        class FakeIMAP:
            def __init__(self, *a, **k): pass
            def login(self, u, p): assert u and p
            def logout(self): pass
        monkeypatch.setattr(apple_mod.imaplib, "IMAP4_SSL", FakeIMAP)
        access, refresh, expiry, account = AppleMailProvider().connect_with_credentials("kid@icloud.com", "app-pw")
        assert access == "app-pw"
        assert account == "kid@icloud.com"
        assert isinstance(expiry, datetime)

    def test_connect_with_credentials_bad_password_raises_auth_error(self, monkeypatch):
        class FakeIMAP:
            def __init__(self, *a, **k): pass
            def login(self, u, p): raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] failed")
            def logout(self): pass
        monkeypatch.setattr(apple_mod.imaplib, "IMAP4_SSL", FakeIMAP)
        with pytest.raises(ProviderAuthError):
            AppleMailProvider().connect_with_credentials("kid@icloud.com", "wrong")

    def test_html_only_body_is_stripped(self):
        m = EmailMessage()
        m["From"] = "friend@example.com"
        m["To"] = "kid@icloud.com"
        m["Subject"] = "Hi"
        m["Message-ID"] = "<h@x>"
        m["Date"] = "Wed, 02 Oct 2002 13:00:00 GMT"
        m.set_content("<p>hello <b>world</b></p>", subtype="html")
        raw = {"rfc822": m.as_bytes(), "uid": "1", "mailbox": "INBOX"}
        d = AppleMailProvider().extract_message_data(raw, "kid@icloud.com", "c", "k")
        assert "hello" in d["body_text"] and "world" in d["body_text"]
        assert "<" not in d["body_text"]

    def test_encoded_word_subject_is_decoded(self):
        raw = {"rfc822": _rfc822(sender="a@b.com", to="kid@icloud.com",
                                 subject="=?UTF-8?B?SGVsbG8gV29ybGQ=?="),
               "uid": "1", "mailbox": "INBOX"}
        d = AppleMailProvider().extract_message_data(raw, "kid@icloud.com", "c", "k")
        assert d["subject"] == "Hello World"


def _graph_msg(*, sender: str, to: list[str], cc: list[str] | None = None,
               subject: str = "Hi", content: str = "<p>hello <b>world</b></p>",
               content_type: str = "html", msg_id: str = "<abc@outlook.com>") -> dict:
    return {
        "id": "AAMkAGI=",
        "internetMessageId": msg_id,
        "subject": subject,
        "from": {"emailAddress": {"address": sender, "name": "Someone"}},
        "toRecipients": [{"emailAddress": {"address": a}} for a in to],
        "ccRecipients": [{"emailAddress": {"address": a}} for a in (cc or [])],
        "receivedDateTime": "2026-06-28T13:00:00Z",
        "body": {"contentType": content_type, "content": content},
    }


class _FakeResp:
    def __init__(self, status: int, data: dict):
        self.status_code = status
        self._data = data

    def json(self):
        return self._data


class TestMicrosoftProvider:
    def test_registry_and_auth_kind(self):
        p = get_provider("microsoft")
        assert isinstance(p, MicrosoftProvider)
        assert p.auth_kind == "oauth"

    def test_authorization_url(self, monkeypatch):
        monkeypatch.setattr(ms_mod.settings, "microsoft_client_id", "cid")
        monkeypatch.setattr(ms_mod.settings, "microsoft_client_secret", "sec")
        url = MicrosoftProvider().authorization_url("STATE123", "https://app.example/cb")
        assert url.startswith("https://login.microsoftonline.com/common/oauth2/v2.0/authorize?")
        assert "client_id=cid" in url
        assert "state=STATE123" in url
        assert "Mail.Read" in url and "offline_access" in url

    def test_authorization_url_unconfigured_raises(self, monkeypatch):
        from app.services.email_providers.base import ProviderUnavailable
        monkeypatch.setattr(ms_mod.settings, "microsoft_client_id", "")
        with pytest.raises(ProviderUnavailable):
            MicrosoftProvider().authorization_url("s", "https://app/cb")

    def test_extract_message_data_inbound(self):
        raw = _graph_msg(sender="friend@example.com", to=["kid@outlook.com", "x@y.com"], cc=["cc@y.com"])
        d = MicrosoftProvider().extract_message_data(raw, "kid@outlook.com", "conn-1", "child-1")
        assert d["gmail_message_id"] == "<abc@outlook.com>"
        assert d["gmail_connection_id"] == "conn-1"
        assert d["child_id"] == "child-1"
        assert d["direction"] == "inbound"
        assert d["sender_address"] == "friend@example.com"
        assert d["recipient_addresses"] == ["kid@outlook.com", "x@y.com", "cc@y.com"]
        assert d["subject"] == "Hi"
        assert "hello" in d["body_text"] and "world" in d["body_text"] and "<" not in d["body_text"]
        assert isinstance(d["received_at"], datetime)
        assert set(d.keys()) == {
            "gmail_message_id", "gmail_connection_id", "child_id", "direction",
            "sender_address", "recipient_addresses", "subject", "body_text", "received_at",
        }

    def test_extract_outbound_and_plaintext_body(self):
        raw = _graph_msg(sender="kid@outlook.com", to=["friend@example.com"],
                         content="plain body", content_type="text")
        d = MicrosoftProvider().extract_message_data(raw, "kid@outlook.com", "c", "k")
        assert d["direction"] == "outbound"
        assert d["body_text"] == "plain body"

    def test_extract_outbound_via_sent_folder_when_address_differs(self):
        # Work/school account: stored address is the UPN but the message's from
        # is the primary SMTP — folder must still classify it outbound.
        raw = _graph_msg(sender="kid@contoso.com", to=["friend@example.com"])
        raw["_folder"] = "sentitems"
        d = MicrosoftProvider().extract_message_data(raw, "kid@contoso.onmicrosoft.com", "c", "k")
        assert d["direction"] == "outbound"

    def test_refresh_skipped_when_token_fresh(self):
        # expiry well in the future → no token request, returns the same token.
        from datetime import datetime, timezone, timedelta
        creds, client = MicrosoftProvider().build_client(
            "tok", "rt", token_expiry=datetime.now(timezone.utc) + timedelta(hours=1))
        try:
            access, refresh, expiry = MicrosoftProvider().refresh_if_needed(creds)
            assert access == "tok" and refresh == "rt"
        finally:
            client.close()

    def test_exchange_code(self, monkeypatch):
        monkeypatch.setattr(ms_mod.settings, "microsoft_client_id", "cid")
        monkeypatch.setattr(ms_mod.settings, "microsoft_client_secret", "sec")
        monkeypatch.setattr(ms_mod.httpx, "post",
                            lambda url, data=None, timeout=None: _FakeResp(200, {
                                "access_token": "at", "refresh_token": "rt", "expires_in": 3600}))
        monkeypatch.setattr(ms_mod.httpx, "get",
                            lambda url, headers=None, timeout=None: _FakeResp(200, {"mail": "kid@outlook.com"}))
        access, refresh, expiry, email = MicrosoftProvider().exchange_code("code", "state", "https://app/cb")
        assert access == "at" and refresh == "rt" and email == "kid@outlook.com"
        assert isinstance(expiry, datetime)

    def test_refresh_invalid_grant_raises_auth_error(self, monkeypatch):
        monkeypatch.setattr(ms_mod.settings, "microsoft_client_id", "cid")
        monkeypatch.setattr(ms_mod.settings, "microsoft_client_secret", "sec")
        monkeypatch.setattr(ms_mod.httpx, "post",
                            lambda url, data=None, timeout=None: _FakeResp(400, {"error": "invalid_grant"}))
        creds, client = MicrosoftProvider().build_client("old", "rt")
        try:
            with pytest.raises(ProviderAuthError):
                MicrosoftProvider().refresh_if_needed(creds)
        finally:
            client.close()


class TestShimDelegates:
    def test_legacy_shim_still_works(self):
        # app/services/gmail.py is a back-compat shim over GmailProvider.
        from app.services import gmail as shim
        raw = _raw_message(sender="a@b.com", to="kid@gmail.com")
        data = shim.extract_message_data(raw, "kid@gmail.com", "c", "k")
        assert data["gmail_message_id"] == "msg123"
        assert callable(shim.revoke_token) and callable(shim.build_gmail_service)
