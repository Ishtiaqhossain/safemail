import json
import anthropic
from app.config import get_settings

settings = get_settings()

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
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    return json.loads(response.content[0].text)
