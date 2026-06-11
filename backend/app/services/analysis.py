import json
import anthropic
from app.config import get_settings

settings = get_settings()

# ── Model cascade ──────────────────────────────────────────────────────────────
# A cheap model triages every email; anything it does not confidently clear as
# benign is escalated to the stronger model, which makes the authoritative call.
# Most email is obviously safe, so the majority never pays for the strong model.
TRIAGE_MODEL = "claude-haiku-4-5"
ESCALATION_MODEL = "claude-sonnet-4-6"
CASCADE_MODELS = (TRIAGE_MODEL, ESCALATION_MODEL)

# Back-compat: callers/admin that imported a single "the classifier" model.
MODEL_NAME = ESCALATION_MODEL

# Escalate unless triage returns severity "none" with at least this confidence.
# Tunable against tests/evaluation — raising it escalates more (safer, costlier).
ESCALATION_CONFIDENCE = 0.85

# Per-request timeout (seconds): a hung API call must not pin a Celery worker.
# Retries are handled with discrimination at the task layer, so the SDK's own
# retries are disabled (max_retries=0) to avoid double-retrying.
API_TIMEOUT_SECONDS = 30.0

# Per-model pricing, USD per million tokens. Single source of truth for cost.
PRICING = {
    "claude-haiku-4-5":  {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
}
# Legacy single-rate constants (escalation model) kept for the admin endpoint.
INPUT_TOKEN_PRICE_PER_M = PRICING[ESCALATION_MODEL]["input"]
OUTPUT_TOKEN_PRICE_PER_M = PRICING[ESCALATION_MODEL]["output"]


def token_cost_usd(input_tokens: int, output_tokens: int, model: str = ESCALATION_MODEL) -> float:
    rates = PRICING.get(model, PRICING[ESCALATION_MODEL])
    return round(
        input_tokens / 1_000_000 * rates["input"]
        + output_tokens / 1_000_000 * rates["output"],
        6,
    )


def _make_client() -> anthropic.Anthropic:
    # Constructed per call (cheap relative to API latency) so the API key is only
    # needed at call time, not import time, and so tests can patch the class.
    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=API_TIMEOUT_SECONDS,
        max_retries=0,
    )


SYSTEM_PROMPT = """You are a child safety classifier for a parental monitoring service.
Analyze the provided email and determine if it contains content that poses a safety risk to a minor.
Be precise — false positives erode parent trust. Normal school, social, or commercial emails should return severity "none".

Respond ONLY with valid JSON matching this exact schema — no markdown, no explanation:
{
  "severity": "none" | "low" | "medium" | "high" | "critical",
  "category": "none" | "self_harm" | "grooming" | "bullying" | "drugs_alcohol" | "stranger_contact" | "personal_info_sharing",
  "confidence": <float 0.0–1.0>,
  "summary": "<1-2 sentences describing the concern written for a parent. Empty string if severity is none.>",
  "response_script": "<suggested next step for the parent, or null if severity is none>"
}"""

CATEGORY_SEVERITY_GUIDE = """
Category guidance:
- self_harm: low=vague sadness, medium=hopelessness, high=self-harm references, critical=explicit suicide plan
- grooming: low=unusual adult contact, medium=requests to move to private channel, high=sexual language, critical=explicit solicitation
- bullying: low=mild teasing, medium=sustained targeting, high=threats, critical=coordinated harassment
- drugs_alcohol: low=references others using, medium=expressing interest, high=offer/solicitation, critical=active arrangement to obtain
- stranger_contact: low=unknown adult casual contact, medium=unusual questions about location/school, high=requests for photos, critical=requests to meet in person
- personal_info_sharing: low=first name only, medium=school name, high=home address or phone, critical=full identity + location
"""

# The instructions are constant, so they live in the system prompt as a single
# cached prefix (prompt caching, OWASP-irrelevant cost optimization). NOTE: prompt
# caching only activates once the prefix exceeds the model minimum (Sonnet 4.6:
# 2048 tokens, Haiku 4.5: 4096). This prompt is well under that today, so caching
# is a no-op until the prompt grows — the marker is correct and future-proof, and
# the real cost win right now is the cascade above. Only the per-email content is
# variable and goes in the user message.
_SYSTEM_BLOCKS = [{
    "type": "text",
    "text": SYSTEM_PROMPT + "\n" + CATEGORY_SEVERITY_GUIDE,
    "cache_control": {"type": "ephemeral"},
}]


# The classifier output is untrusted (it is steered by attacker-controlled email
# text and is a model generation). Constrain it to a known shape before it is
# stored or rendered anywhere — OWASP LLM05: Improper Output Handling.
VALID_SEVERITIES = {"none", "low", "medium", "high", "critical"}
VALID_CATEGORIES = {
    "none", "self_harm", "grooming", "bullying",
    "drugs_alcohol", "stranger_contact", "personal_info_sharing",
}
MAX_SUMMARY_LEN = 600
MAX_SCRIPT_LEN = 600


def _strip_code_fences(text: str) -> str:
    """Tolerate a model that wraps its JSON in a ```json … ``` fence."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _normalize_classification(raw: dict) -> dict:
    """Coerce the model's JSON into a strict, safe shape.

    Enums are whitelisted (anything unexpected becomes "none" so a malformed or
    injected value can never reach the DB or an alert), confidence is clamped to
    [0, 1], and the free-text fields are forced to strings and length-capped.
    """
    severity = raw.get("severity")
    if severity not in VALID_SEVERITIES:
        severity = "none"

    category = raw.get("category")
    if category not in VALID_CATEGORIES:
        category = "none"

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    summary = raw.get("summary") or ""
    if not isinstance(summary, str):
        summary = str(summary)
    summary = summary.strip()[:MAX_SUMMARY_LEN]

    script = raw.get("response_script")
    if script is not None:
        if not isinstance(script, str):
            script = str(script)
        script = script.strip()[:MAX_SCRIPT_LEN] or None

    return {
        "severity": severity,
        "category": category,
        "confidence": confidence,
        "summary": summary,
        "response_script": script,
    }


def _build_user_content(message: dict) -> str:
    return (
        f"Direction: {message['direction']}\n"
        f"From: {message['sender_address']}\n"
        f"To: {', '.join(message['recipient_addresses'])}\n"
        f"Subject: {message['subject']}\n\n"
        f"Body:\n{message['body_text']}"
    )


def _classify_once(model: str, user_content: str) -> dict:
    """Run a single classification pass on one model. Returns the normalized
    result plus per-call usage/model under underscore-prefixed keys."""
    response = _make_client().messages.create(
        model=model,
        max_tokens=512,
        system=_SYSTEM_BLOCKS,
        messages=[{"role": "user", "content": user_content}],
    )
    result = _normalize_classification(json.loads(_strip_code_fences(response.content[0].text)))
    result["_model"] = model
    result["_input_tokens"] = response.usage.input_tokens
    result["_output_tokens"] = response.usage.output_tokens
    return result


def classify_email(message: dict) -> dict:
    """Classify an email via the triage → escalation cascade.

    Returns the normalized classification plus aggregate usage across every call
    the cascade made: input_tokens, output_tokens, cost_usd (per-model accurate),
    model (e.g. "claude-haiku-4-5" or "claude-haiku-4-5+claude-sonnet-4-6"), and
    escalated (bool).
    """
    user_content = _build_user_content(message)

    triage = _classify_once(TRIAGE_MODEL, user_content)
    calls = [triage]

    # Trust triage only when it is confidently benign; otherwise the strong model
    # decides. This bounds recall loss to "triage confidently mis-clears a real
    # threat", which tests/evaluation measures and ESCALATION_CONFIDENCE tunes.
    confidently_benign = (
        triage["severity"] == "none" and triage["confidence"] >= ESCALATION_CONFIDENCE
    )
    final = triage if confidently_benign else _classify_once(ESCALATION_MODEL, user_content)
    if final is not triage:
        calls.append(final)

    input_tokens = sum(c["_input_tokens"] for c in calls)
    output_tokens = sum(c["_output_tokens"] for c in calls)
    cost_usd = round(
        sum(token_cost_usd(c["_input_tokens"], c["_output_tokens"], c["_model"]) for c in calls),
        6,
    )

    return {
        "severity": final["severity"],
        "category": final["category"],
        "confidence": final["confidence"],
        "summary": final["summary"],
        "response_script": final["response_script"],
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "model": "+".join(c["_model"] for c in calls),
        "escalated": len(calls) > 1,
    }
