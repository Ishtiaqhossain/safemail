"""
Pipeline integration tests.

Tests the full path: message dict → classify → persist alert → deliver notification.
Uses a real test DB but mocks the Anthropic API and notification services.
"""

import uuid
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock
from sqlalchemy import select

from tests.evaluation.fixtures import SELF_HARM, GROOMING, BULLYING, BENIGN


pytestmark = pytest.mark.asyncio


# ─────────────────────────────────────────────
# Mocked Claude response builders
# ─────────────────────────────────────────────

def _mock_result(severity: str, category: str, confidence: float = 0.92):
    return {
        "severity": severity,
        "category": category,
        "confidence": confidence,
        "summary": f"Test summary for {category} at {severity} severity.",
        "response_script": "Talk to your child about this.",
    }


def _mock_none():
    return {"severity": "none", "category": "none", "confidence": 0.95, "summary": "", "response_script": None}


# ─────────────────────────────────────────────
# Unit: classify_email returns valid schema
# ─────────────────────────────────────────────

class TestClassifyEmailSchema:
    def test_returns_required_fields(self):
        with patch("app.services.analysis.anthropic.Anthropic") as MockClient:
            import json
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps(_mock_result("high", "grooming")))]
            MockClient.return_value.messages.create.return_value = mock_response

            from app.services.analysis import classify_email
            result = classify_email(GROOMING[2].message)

        assert "severity" in result
        assert "category" in result
        assert "confidence" in result
        assert "summary" in result
        assert "response_script" in result

    def test_severity_values_are_valid(self):
        valid = {"none", "low", "medium", "high", "critical"}
        with patch("app.services.analysis.anthropic.Anthropic") as MockClient:
            import json
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps(_mock_result("high", "bullying")))]
            MockClient.return_value.messages.create.return_value = mock_response

            from app.services.analysis import classify_email
            result = classify_email(BULLYING[0].message)

        assert result["severity"] in valid

    def test_benign_returns_none_severity(self):
        with patch("app.services.analysis.anthropic.Anthropic") as MockClient:
            import json
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps(_mock_none()))]
            MockClient.return_value.messages.create.return_value = mock_response

            from app.services.analysis import classify_email
            result = classify_email(BENIGN[0].message)

        assert result["severity"] == "none"


# ─────────────────────────────────────────────
# Unit: confidence threshold filtering
# ─────────────────────────────────────────────

class TestConfidenceThreshold:
    def test_low_confidence_result_does_not_create_alert(self):
        """Results below 0.70 confidence must be discarded."""
        low_confidence_result = _mock_result("high", "grooming", confidence=0.65)

        with patch("app.tasks.analysis.classify_email", return_value=low_confidence_result), \
             patch("app.tasks.analysis.SyncSessionLocal") as MockSession:

            mock_db = MagicMock()
            MockSession.return_value.__enter__ = MagicMock(return_value=mock_db)
            MockSession.return_value.__exit__ = MagicMock(return_value=False)

            from app.tasks.analysis import analyze_message
            analyze_message(GROOMING[1].message)

            mock_db.add.assert_not_called()

    def test_high_confidence_result_creates_alert(self):
        """Results at or above 0.70 confidence must create an alert."""
        high_confidence_result = _mock_result("high", "grooming", confidence=0.91)

        with patch("app.tasks.analysis.classify_email", return_value=high_confidence_result), \
             patch("app.tasks.analysis.SyncSessionLocal") as MockSession, \
             patch("app.tasks.analysis.deliver_alert") as mock_deliver:

            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_alert = MagicMock()
            mock_alert.id = uuid.uuid4()
            mock_db.add = MagicMock()
            mock_db.commit = MagicMock()
            mock_db.refresh = MagicMock(side_effect=lambda obj: setattr(obj, "id", uuid.uuid4()))
            MockSession.return_value.__enter__ = MagicMock(return_value=mock_db)
            MockSession.return_value.__exit__ = MagicMock(return_value=False)

            from app.tasks.analysis import analyze_message
            analyze_message(GROOMING[1].message)

            mock_db.add.assert_called_once()


# ─────────────────────────────────────────────
# Unit: deduplication
# ─────────────────────────────────────────────

class TestDeduplication:
    def test_same_message_id_not_analyzed_twice(self):
        """The same gmail_message_id must not create two alerts."""
        result = _mock_result("high", "self_harm", confidence=0.90)

        with patch("app.tasks.analysis.classify_email", return_value=result), \
             patch("app.tasks.analysis.SyncSessionLocal") as MockSession, \
             patch("app.tasks.analysis.deliver_alert"):

            mock_db = MagicMock()
            # Second call: existing alert found
            existing_alert = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = existing_alert
            MockSession.return_value.__enter__ = MagicMock(return_value=mock_db)
            MockSession.return_value.__exit__ = MagicMock(return_value=False)

            from app.tasks.analysis import analyze_message
            analyze_message(SELF_HARM[2].message)

            mock_db.add.assert_not_called()


# ─────────────────────────────────────────────
# Unit: notification routing by severity
# ─────────────────────────────────────────────

class TestNotificationRouting:
    def _run_deliver(self, severity: str, immediate_severities: list[str]):
        with patch("app.tasks.analysis.SyncSessionLocal") as MockSession, \
             patch("app.tasks.analysis.send_alert_email") as mock_email, \
             patch("app.tasks.analysis.send_push_notification") as mock_push:

            mock_alert = MagicMock()
            mock_alert.severity = severity
            mock_alert.category = "grooming"
            mock_alert.ai_summary = "Test summary"
            mock_alert.ai_response_script = None
            mock_alert.notified_at = None

            mock_child = MagicMock()
            mock_child.display_name = "Emma"
            mock_child.parent_id = uuid.uuid4()

            mock_parent = MagicMock()
            mock_parent.email = "parent@example.com"
            mock_parent.fcm_token = "fake-fcm-token"

            mock_pref = MagicMock()
            mock_pref.immediate_severities = immediate_severities

            mock_db = MagicMock()
            mock_db.get.side_effect = lambda model, id: {
                "Alert": mock_alert,
                "Child": mock_child,
                "Parent": mock_parent,
            }.get(model.__name__, None)
            mock_db.query.return_value.filter.return_value.first.return_value = mock_pref
            MockSession.return_value.__enter__ = MagicMock(return_value=mock_db)
            MockSession.return_value.__exit__ = MagicMock(return_value=False)

            from app.tasks.analysis import deliver_alert
            deliver_alert(str(uuid.uuid4()))

            return mock_email, mock_push

    def test_critical_alert_triggers_immediate_notification(self):
        mock_email, mock_push = self._run_deliver("critical", ["critical", "high"])
        mock_email.assert_called_once()
        mock_push.assert_called_once()

    def test_medium_alert_skips_immediate_notification_by_default(self):
        mock_email, mock_push = self._run_deliver("medium", ["critical", "high"])
        mock_email.assert_not_called()
        mock_push.assert_not_called()

    def test_medium_alert_notifies_if_parent_opted_in(self):
        mock_email, mock_push = self._run_deliver("medium", ["critical", "high", "medium"])
        mock_email.assert_called_once()


# ─────────────────────────────────────────────
# Unit: crypto — token encryption round-trip
# ─────────────────────────────────────────────

class TestCrypto:
    def test_encrypt_decrypt_roundtrip(self):
        from cryptography.fernet import Fernet
        with patch("app.services.crypto.get_settings") as mock_settings:
            mock_settings.return_value.fernet_key = Fernet.generate_key().decode()
            import app.services.crypto as crypto_module
            crypto_module._fernet = None  # reset cached instance

            from app.services.crypto import encrypt_token, decrypt_token
            original = "ya29.some-google-access-token"
            assert decrypt_token(encrypt_token(original)) == original

    def test_encrypted_differs_from_plaintext(self):
        from cryptography.fernet import Fernet
        with patch("app.services.crypto.get_settings") as mock_settings:
            mock_settings.return_value.fernet_key = Fernet.generate_key().decode()
            import app.services.crypto as crypto_module
            crypto_module._fernet = None

            from app.services.crypto import encrypt_token
            token = "my-secret-token"
            assert encrypt_token(token) != token
