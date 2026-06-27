"""Tests for the agentic self-monitoring system.

These run without a database or a real Claude API key: the Redis probes use a
fake client, and the remediation agent tests mock the Anthropic SDK. They cover
the parts with real logic — probe tripping, the agent tool-use loop, the
advisory/auto gate, the fix-action cap, and the connection guardrail.
"""
import json
from unittest.mock import patch, MagicMock

import pytest

from app.services.monitoring import (
    check_redis, check_queue_backlog, Finding,
)
from app.services import remediation


# ── Fakes ────────────────────────────────────────────────────────────────────

class FakeRedis:
    def __init__(self, *, ping_ok=True, queue_len=0, store=None):
        self._ping_ok = ping_ok
        self._queue_len = queue_len
        self._store = store if store is not None else {}

    def ping(self):
        if not self._ping_ok:
            raise ConnectionError("redis down")
        return True

    def llen(self, _key):
        return self._queue_len

    def get(self, key):
        return self._store.get(key)

    def set(self, key, value):
        self._store[key] = value

    def delete(self, key):
        self._store.pop(key, None)


def _finding():
    return Finding(
        check_name="queue_backlog",
        fingerprint="celery_queue_backlog",
        severity="warning",
        title="Celery queue backlog is high",
        detail="Lots of pending tasks.",
        metrics={"queue_depth": 500},
        remediation_hint="Check the worker is running.",
    )


def _text_block(text):
    b = MagicMock()
    b.type = "text"
    b.text = text
    return b


def _tool_block(name, tool_input, tool_id="tu_1"):
    b = MagicMock()
    b.type = "tool_use"
    b.name = name
    b.input = tool_input
    b.id = tool_id
    return b


def _response(content, stop_reason, in_tok=100, out_tok=50):
    r = MagicMock()
    r.content = content
    r.stop_reason = stop_reason
    r.usage.input_tokens = in_tok
    r.usage.output_tokens = out_tok
    return r


# ── Probes ───────────────────────────────────────────────────────────────────

class TestRedisProbes:
    def test_redis_down_is_critical(self):
        f = check_redis(FakeRedis(ping_ok=False))
        assert f is not None
        assert f.severity == "critical"
        assert f.fingerprint == "redis_down"

    def test_redis_up_is_clean(self):
        assert check_redis(FakeRedis(ping_ok=True)) is None

    def test_queue_backlog_trips_above_threshold(self):
        # Default threshold is 200.
        f = check_queue_backlog(FakeRedis(queue_len=500))
        assert f is not None
        assert f.fingerprint == "celery_queue_backlog"
        assert f.metrics["queue_depth"] == 500

    def test_queue_backlog_quiet_below_threshold(self):
        assert check_queue_backlog(FakeRedis(queue_len=5)) is None


# ── Remediation agent ────────────────────────────────────────────────────────

class TestRemediationAgent:
    def test_advisory_mode_offers_no_fix_tools(self, monkeypatch):
        monkeypatch.setattr(remediation.settings, "auto_remediation_enabled", False)
        with patch("app.services.remediation.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = _response(
                [_text_block("Looks like the worker is slow; a human should check it.")],
                "end_turn",
            )
            result = remediation.remediate(_finding(), db=MagicMock(), redis_client=FakeRedis())

        assert result["mode"] == "advisory"
        assert result["status"] == "diagnosed"
        # The fix tools must NOT be offered to the model in advisory mode.
        tools = MockClient.return_value.messages.create.call_args.kwargs["tools"]
        tool_names = {t["name"] for t in tools}
        assert "requeue_gmail_polling" not in tool_names
        assert "poll_connection_now" not in tool_names
        assert "escalate" in tool_names

    def test_auto_mode_executes_fix_action(self, monkeypatch):
        monkeypatch.setattr(remediation.settings, "auto_remediation_enabled", True)
        with patch("app.services.remediation.anthropic.Anthropic") as MockClient, \
             patch("app.tasks.ingestion.poll_all_connections") as MockTask:
            MockClient.return_value.messages.create.side_effect = [
                _response([_tool_block("requeue_gmail_polling", {})], "tool_use"),
                _response([_text_block("Re-enqueued polling to confirm the worker drains it.")], "end_turn"),
            ]
            result = remediation.remediate(_finding(), db=MagicMock(), redis_client=FakeRedis())

        MockTask.delay.assert_called_once()
        assert result["mode"] == "auto"
        assert result["status"] == "attempted"
        assert any(a["tool"] == "requeue_gmail_polling" for a in result["actions"])

    def test_escalation_sets_status(self, monkeypatch):
        monkeypatch.setattr(remediation.settings, "auto_remediation_enabled", True)
        with patch("app.services.remediation.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.side_effect = [
                _response([_tool_block("escalate",
                                       {"reason": "bad api key", "recommended_action": "rotate key"})],
                          "tool_use"),
                _response([_text_block("This needs a human — escalating.")], "end_turn"),
            ]
            result = remediation.remediate(_finding(), db=MagicMock(), redis_client=FakeRedis())

        assert result["status"] == "escalated"
        assert any(a["tool"] == "escalate" for a in result["actions"])

    def test_api_error_degrades_gracefully(self, monkeypatch):
        import anthropic
        monkeypatch.setattr(remediation.settings, "auto_remediation_enabled", True)
        with patch("app.services.remediation.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.side_effect = anthropic.APIError(
                "boom", request=MagicMock(), body=None
            )
            result = remediation.remediate(_finding(), db=MagicMock(), redis_client=FakeRedis())

        assert result["status"] == "failed"
        assert "boom" in result["diagnosis"]


class TestAutoRemediationToggle:
    def test_override_on_wins_over_env(self, monkeypatch):
        monkeypatch.setattr(remediation.settings, "auto_remediation_enabled", False)
        r = FakeRedis(store={remediation.AUTO_OVERRIDE_KEY: "1"})
        assert remediation.resolve_auto_remediation(r) is True
        assert remediation.get_auto_remediation_override(r) is True

    def test_override_off_wins_over_env(self, monkeypatch):
        monkeypatch.setattr(remediation.settings, "auto_remediation_enabled", True)
        r = FakeRedis(store={remediation.AUTO_OVERRIDE_KEY: "0"})
        assert remediation.resolve_auto_remediation(r) is False
        assert remediation.get_auto_remediation_override(r) is False

    def test_no_override_falls_back_to_env(self, monkeypatch):
        monkeypatch.setattr(remediation.settings, "auto_remediation_enabled", True)
        r = FakeRedis()  # empty store
        assert remediation.get_auto_remediation_override(r) is None
        assert remediation.resolve_auto_remediation(r) is True

    def test_set_and_clear_override(self):
        r = FakeRedis()
        remediation.set_auto_remediation_override(r, True)
        assert remediation.get_auto_remediation_override(r) is True
        remediation.set_auto_remediation_override(r, None)  # clear → env default
        assert remediation.get_auto_remediation_override(r) is None


class TestFixToolGuardrails:
    def test_poll_connection_now_refuses_non_active(self):
        conn = MagicMock()
        conn.status = "error"
        conn.id = "abc"
        db = MagicMock()
        db.get.return_value = conn
        out = remediation._exec_poll_connection_now(db, {"connection_id": "abc"})
        assert "error" in out
        assert "not active" in out["error"]

    def test_poll_connection_now_enqueues_active(self):
        conn = MagicMock()
        conn.status = "active"
        conn.id = "abc"
        db = MagicMock()
        db.get.return_value = conn
        with patch("app.tasks.ingestion.poll_connection") as MockTask:
            out = remediation._exec_poll_connection_now(db, {"connection_id": "abc"})
        MockTask.delay.assert_called_once_with("abc")
        assert out["enqueued"] == "poll_connection"

    def test_fix_action_cap_enforced(self, monkeypatch):
        """The agent can ask for more fix actions than allowed; the loop caps them."""
        monkeypatch.setattr(remediation.settings, "auto_remediation_enabled", True)
        monkeypatch.setattr(remediation, "MAX_FIX_ACTIONS", 1)
        with patch("app.services.remediation.anthropic.Anthropic") as MockClient, \
             patch("app.tasks.ingestion.poll_all_connections") as MockTask:
            MockClient.return_value.messages.create.side_effect = [
                _response([_tool_block("requeue_gmail_polling", {}, "t1")], "tool_use"),
                _response([_tool_block("requeue_gmail_polling", {}, "t2")], "tool_use"),
                _response([_text_block("done")], "end_turn"),
            ]
            result = remediation.remediate(_finding(), db=MagicMock(), redis_client=FakeRedis())

        # Only the first fix actually ran; the second hit the cap.
        assert MockTask.delay.call_count == 1
        capped = [a for a in result["actions"]
                  if isinstance(a["result"], dict) and a["result"].get("error")]
        assert len(capped) == 1
