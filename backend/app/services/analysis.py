import json
import anthropic
from app.config import get_settings

settings = get_settings()

# Model and pricing — single source of truth shared by the analysis pipeline,
# the admin LLM-stats endpoint, and the developer classifier playground.
MODEL_NAME = "claude-sonnet-4-6"
INPUT_TOKEN_PRICE_PER_M = 3.00   # USD per million input tokens
OUTPUT_TOKEN_PRICE_PER_M = 15.00  # USD per million output tokens


def token_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return round(
        input_tokens / 1_000_000 * INPUT_TOKEN_PRICE_PER_M
        + output_tokens / 1_000_000 * OUTPUT_TOKEN_PRICE_PER_M,
        4,
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


CATEGORY_SEVERITY_GUIDE = """
Category guidance:
- self_harm: low=vague sadness, medium=hopelessness, high=self-harm references, critical=explicit suicide plan
- grooming: low=unusual adult contact, medium=requests to move to private channel, high=sexual language, critical=explicit solicitation
- bullying: low=mild teasing, medium=sustained targeting, high=threats, critical=coordinated harassment
- drugs_alcohol: low=references others using, medium=expressing interest, high=offer/solicitation, critical=active arrangement to obtain
- stranger_contact: low=unknown adult casual contact, medium=unusual questions about location/school, high=requests for photos, critical=requests to meet in person
- personal_info_sharing: low=first name only, medium=school name, high=home address or phone, critical=full identity + location
"""


def classify_email(message: dict) -> dict:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    user_content = (
        f"Direction: {message['direction']}\n"
        f"From: {message['sender_address']}\n"
        f"To: {', '.join(message['recipient_addresses'])}\n"
        f"Subject: {message['subject']}\n\n"
        f"Body:\n{message['body_text']}\n\n"
        f"{CATEGORY_SEVERITY_GUIDE}"
    )

    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    parsed = json.loads(_strip_code_fences(response.content[0].text))
    result = _normalize_classification(parsed)
    result["input_tokens"] = response.usage.input_tokens
    result["output_tokens"] = response.usage.output_tokens
    return result
