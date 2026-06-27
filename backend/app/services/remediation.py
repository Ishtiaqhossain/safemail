"""The agentic core of the self-monitoring system.

Given a health Finding, an LLM agent investigates it with a constrained set of
read-only tools and — when ``AUTO_REMEDIATION_ENABLED`` is on — may take a small
allowlist of bounded, reversible fix actions (re-enqueue Gmail polling, nudge a
specific connection). Every tool call is recorded and returned so the incident
row keeps a full audit trail.

Design constraints:
- **Bounded.** A hard cap on agent turns; a hard cap on fix actions per run.
- **Safe by default.** Fix tools are only offered to the model when
  ``auto_remediation_enabled`` is true; otherwise the agent runs in advisory
  mode (investigate + recommend), and the only "action" it can take is to
  escalate to a human.
- **Allowlisted.** The agent can only do what a tool lets it. There is no shell,
  no SQL, no arbitrary writes. The fix tools are idempotent or self-limiting.
- **Robust.** Any failure (no API key, API error, bad tool args) degrades to a
  recorded ``failed`` remediation rather than crashing the monitoring cycle.

Runs synchronously inside the Celery worker, using the sync SQLAlchemy session.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta

import anthropic
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.gmail_connection import GmailConnection
from app.models.task_log import TaskLog
from app.services.analysis import token_cost_usd

logger = logging.getLogger(__name__)
settings = get_settings()

# The product already standardizes on this model for its classifier escalation;
# reuse it here so ops cost and behavior are predictable. The agent only runs on
# a *new* incident (not every monitoring cycle), so spend is naturally bounded.
REMEDIATION_MODEL = "claude-sonnet-4-6"

API_TIMEOUT_SECONDS = 30.0
MAX_AGENT_TURNS = 8        # hard ceiling on the investigate/act loop
MAX_FIX_ACTIONS = 3        # hard ceiling on mutating actions per incident

# Runtime override for auto-remediation, set from the agent control pane and
# stored in Redis. When unset, the AUTO_REMEDIATION_ENABLED env var is the default.
AUTO_OVERRIDE_KEY = "monitoring:auto_remediation_override"


def resolve_auto_remediation(redis_client) -> bool:
    """Effective auto-remediation flag: a runtime override (set from the control
    pane) wins; otherwise fall back to the AUTO_REMEDIATION_ENABLED env var."""
    override = get_auto_remediation_override(redis_client)
    return settings.auto_remediation_enabled if override is None else override


def get_auto_remediation_override(redis_client):
    """The runtime override: True / False if set, else None (env default in use)."""
    try:
        v = redis_client.get(AUTO_OVERRIDE_KEY)
    except Exception:
        return None
    if v is None:
        return None
    if isinstance(v, bytes):
        v = v.decode()
    return v == "1"


def set_auto_remediation_override(redis_client, enabled) -> None:
    """enabled True/False pins the override; None clears it (revert to env default)."""
    if enabled is None:
        redis_client.delete(AUTO_OVERRIDE_KEY)
    else:
        redis_client.set(AUTO_OVERRIDE_KEY, "1" if enabled else "0")


SYSTEM_PROMPT = """You are the on-call SRE agent for SafeMail, an AI email-safety \
monitoring service for parents. A health probe has detected a problem. Your job:

1. Investigate using the read-only tools to confirm what is actually wrong and find the root cause.
2. Decide whether a safe, bounded automated fix applies.
   - If fix tools are available to you AND a fix clearly and safely applies, use it. Prefer the
     least invasive action. Never take a mutating action you cannot justify from the evidence.
   - If the problem needs human intervention (bad credentials, infrastructure down, an OAuth grant
     only the parent can renew, anything ambiguous or risky), call `escalate` instead of guessing.
3. When you are done, stop calling tools and reply with a short plain-text diagnosis: what is wrong,
   the most likely root cause, what you did (or why you escalated), and the recommended next step
   for a human operator.

Principles: be conservative — a wrong automated action is worse than escalating. The available fix \
actions are idempotent and safe to repeat. Do not recommend or attempt anything outside the tools \
you are given. Keep the final diagnosis concise (a few sentences)."""


# ── Tool schemas ────────────────────────────────────────────────────────────────

_READ_TOOLS = [
    {
        "name": "get_recent_task_logs",
        "description": "Read recent Celery task log rows to inspect failures and their error "
                       "messages. Use this to find the common cause behind a failure spike.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_name": {"type": "string",
                              "description": "Filter to one task, e.g. 'poll_connection' or "
                                             "'analyze_message'. Omit for all tasks."},
                "status": {"type": "string", "enum": ["success", "failure"],
                           "description": "Filter by status. Omit for both."},
                "limit": {"type": "integer", "description": "Max rows (default 10, max 30)."},
            },
        },
    },
    {
        "name": "get_connection_summary",
        "description": "Get a summary of Gmail connections: counts by status and the list of "
                       "connections that are stale (active but not synced recently) or in error.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_queue_depth",
        "description": "Get the current Celery queue backlog (number of pending tasks).",
        "input_schema": {"type": "object", "properties": {}},
    },
]

_FIX_TOOLS = [
    {
        "name": "requeue_gmail_polling",
        "description": "Enqueue a fresh poll cycle for ALL active Gmail connections. Idempotent: a "
                       "Redis dedup set prevents the same email being analyzed twice, so this is "
                       "safe to run. Use when polling has stalled and you want to confirm the worker "
                       "can drain new work.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "poll_connection_now",
        "description": "Enqueue an immediate poll for ONE active connection by id. Safe and "
                       "idempotent. Use to nudge a specific stale connection that is still active "
                       "(NOT one in 'error' state — those need the parent to reconnect).",
        "input_schema": {
            "type": "object",
            "properties": {
                "connection_id": {"type": "string", "description": "The connection id to poll."},
            },
            "required": ["connection_id"],
        },
    },
]

_ESCALATE_TOOL = {
    "name": "escalate",
    "description": "Declare that this incident needs a human. Use when no safe automated fix "
                   "applies, or when you are not confident. Provide the reason and the recommended "
                   "human action.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "Why this needs a human."},
            "recommended_action": {"type": "string", "description": "What the operator should do."},
        },
        "required": ["reason", "recommended_action"],
    },
}


def _make_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=API_TIMEOUT_SECONDS)


# ── Tool execution ──────────────────────────────────────────────────────────────

def _exec_get_recent_task_logs(db: Session, args: dict) -> dict:
    limit = min(int(args.get("limit") or 10), 30)
    q = db.query(TaskLog)
    if args.get("task_name"):
        q = q.filter(TaskLog.task_name == args["task_name"])
    if args.get("status"):
        q = q.filter(TaskLog.status == args["status"])
    rows = q.order_by(TaskLog.created_at.desc()).limit(limit).all()
    return {
        "rows": [
            {
                "task_name": r.task_name,
                "status": r.status,
                "error": (r.error[:300] if r.error else None),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "meta": r.meta,
            }
            for r in rows
        ]
    }


def _exec_get_connection_summary(db: Session, _args: dict) -> dict:
    rows = db.query(GmailConnection).all()
    by_status: dict[str, int] = {}
    for c in rows:
        by_status[c.status] = by_status.get(c.status, 0) + 1

    stale_cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=settings.health_stale_connection_minutes
    )
    stale, errored = [], []
    for c in rows:
        if c.status == "error":
            errored.append({"connection_id": str(c.id), "gmail_address": c.gmail_address})
        elif c.status == "active":
            last = c.last_synced_at
            if last is not None and last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if last is None or last < stale_cutoff:
                stale.append({
                    "connection_id": str(c.id),
                    "gmail_address": c.gmail_address,
                    "last_synced_at": last.isoformat() if last else None,
                })
    return {"counts_by_status": by_status, "stale": stale, "errored": errored}


def _exec_get_queue_depth(redis_client, _args: dict) -> dict:
    try:
        return {"pending": redis_client.llen("celery")}
    except Exception as exc:
        return {"error": str(exc)}


def _exec_requeue_gmail_polling(_db: Session, _args: dict) -> dict:
    # Import here to avoid a circular import (tasks import services).
    from app.tasks.ingestion import poll_all_connections
    poll_all_connections.delay()
    return {"enqueued": "poll_all_connections", "note": "Idempotent — dedup set prevents reprocessing."}


def _exec_poll_connection_now(db: Session, args: dict) -> dict:
    cid = args.get("connection_id")
    conn = db.get(GmailConnection, cid) if cid else None
    if not conn:
        return {"error": f"No connection with id {cid}."}
    if conn.status != "active":
        # Guardrail: refuse to poll a non-active connection. An 'error' connection
        # has a revoked/expired grant and would just fail again — that needs the
        # parent, not a retry.
        return {"error": f"Connection {cid} is '{conn.status}', not active; not polling. "
                         "Error-state connections require the parent to reconnect."}
    from app.tasks.ingestion import poll_connection
    poll_connection.delay(str(conn.id))
    return {"enqueued": "poll_connection", "connection_id": str(conn.id)}


def _dispatch_tool(name: str, args: dict, *, db: Session, redis_client) -> dict:
    if name == "get_recent_task_logs":
        return _exec_get_recent_task_logs(db, args)
    if name == "get_connection_summary":
        return _exec_get_connection_summary(db, args)
    if name == "get_queue_depth":
        return _exec_get_queue_depth(redis_client, args)
    if name == "requeue_gmail_polling":
        return _exec_requeue_gmail_polling(db, args)
    if name == "poll_connection_now":
        return _exec_poll_connection_now(db, args)
    return {"error": f"Unknown tool {name}"}


_FIX_TOOL_NAMES = {"requeue_gmail_polling", "poll_connection_now"}


# ── The agent loop ──────────────────────────────────────────────────────────────

def remediate(finding, *, db: Session, redis_client) -> dict:
    """Investigate (and maybe fix) one Finding. Returns an audit record:

        {
          "mode": "auto" | "advisory",
          "status": "succeeded"|"attempted"|"escalated"|"diagnosed"|"failed",
          "diagnosis": str,
          "actions": [{"tool", "input", "result"} ...],
          "model": str, "turns": int,
          "input_tokens": int, "output_tokens": int, "cost_usd": float,
        }

    Never raises: any failure is captured as status="failed" with an error note,
    so the caller can still open the incident and alert.
    """
    auto = resolve_auto_remediation(redis_client)
    mode = "auto" if auto else "advisory"

    tools = list(_READ_TOOLS) + [_ESCALATE_TOOL]
    if auto:
        tools += _FIX_TOOLS

    fix_availability = (
        "AVAILABLE — use one if a safe, bounded fix clearly applies."
        if auto else
        "NOT available (advisory mode — investigate and recommend; escalate if a human is needed)."
    )
    user_msg = (
        f"A health probe tripped. Investigate and respond.\n\n"
        f"Check: {finding.check_name}\n"
        f"Severity: {finding.severity}\n"
        f"Title: {finding.title}\n"
        f"Detail: {finding.detail}\n"
        f"Metrics: {json.dumps(finding.metrics, default=str)}\n"
        f"Probe's remediation hint: {finding.remediation_hint}\n\n"
        f"Automated fix actions are {fix_availability}"
    )

    messages = [{"role": "user", "content": user_msg}]
    actions: list[dict] = []
    in_tokens = out_tokens = 0
    escalated = False

    try:
        client = _make_client()
    except Exception as exc:
        return _degraded(mode, f"Could not construct the Anthropic client: {exc}")

    turns = 0
    final_text = ""
    try:
        for turns in range(1, MAX_AGENT_TURNS + 1):
            resp = client.messages.create(
                model=REMEDIATION_MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )
            in_tokens += resp.usage.input_tokens
            out_tokens += resp.usage.output_tokens

            text_parts = [b.text for b in resp.content if b.type == "text"]
            if text_parts:
                final_text = "\n".join(text_parts).strip()

            if resp.stop_reason != "tool_use":
                break

            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            messages.append({"role": "assistant", "content": resp.content})

            tool_results = []
            for tu in tool_uses:
                if tu.name == "escalate":
                    escalated = True
                    result = {"acknowledged": True}
                    actions.append({"tool": "escalate", "input": dict(tu.input), "result": result})
                elif tu.name in _FIX_TOOL_NAMES:
                    # Enforce the fix-action ceiling regardless of what the model asks.
                    # Count only successful fixes so a transient error doesn't burn the budget.
                    taken = sum(1 for a in actions if a["tool"] in _FIX_TOOL_NAMES
                                and not (isinstance(a["result"], dict) and a["result"].get("error")))
                    if taken >= MAX_FIX_ACTIONS:
                        result = {"error": "Fix-action limit reached for this incident."}
                    else:
                        result = _dispatch_tool(tu.name, dict(tu.input), db=db, redis_client=redis_client)
                    # Record every fix attempt (including capped ones) for the audit trail.
                    actions.append({"tool": tu.name, "input": dict(tu.input), "result": result})
                else:
                    result = _dispatch_tool(tu.name, dict(tu.input), db=db, redis_client=redis_client)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(result, default=str),
                })
            messages.append({"role": "user", "content": tool_results})
        else:
            # Loop exhausted without a natural stop.
            final_text = (final_text + "\n\n[Agent reached its turn limit before concluding.]").strip()
    except anthropic.APIError as exc:
        return _degraded(mode, f"Claude API error during remediation: {exc}",
                         actions=actions, in_tokens=in_tokens, out_tokens=out_tokens)
    except Exception as exc:
        logger.exception("Remediation agent crashed")
        return _degraded(mode, f"Remediation agent error: {exc}",
                         actions=actions, in_tokens=in_tokens, out_tokens=out_tokens)

    fixes = [a for a in actions if a["tool"] in _FIX_TOOL_NAMES
             and not (isinstance(a["result"], dict) and a["result"].get("error"))]
    if fixes:
        status = "attempted"      # action taken; next cycle's probe confirms resolution
    elif escalated:
        status = "escalated"
    else:
        status = "diagnosed"

    return {
        "mode": mode,
        "status": status,
        "diagnosis": final_text or "(no diagnosis produced)",
        "actions": actions,
        "model": REMEDIATION_MODEL,
        "turns": turns,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "cost_usd": token_cost_usd(in_tokens, out_tokens, REMEDIATION_MODEL),
    }


def _degraded(mode: str, message: str, *, actions=None, in_tokens=0, out_tokens=0) -> dict:
    logger.error("Remediation degraded: %s", message)
    return {
        "mode": mode,
        "status": "failed",
        "diagnosis": message,
        "actions": actions or [],
        "model": REMEDIATION_MODEL,
        "turns": 0,
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "cost_usd": token_cost_usd(in_tokens, out_tokens, REMEDIATION_MODEL),
    }
