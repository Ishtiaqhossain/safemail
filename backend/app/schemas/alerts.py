import uuid
from datetime import datetime
from pydantic import BaseModel


class AlertResponse(BaseModel):
    id: uuid.UUID
    child_id: uuid.UUID
    child_name: str
    direction: str
    sender_address: str
    recipient_addresses: list[str]
    subject_snippet: str | None
    received_at: datetime
    category: str
    severity: str
    confidence: float
    ai_summary: str
    ai_response_script: str | None
    parent_feedback: str | None
    notified_at: datetime | None
    reviewed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertListMeta(BaseModel):
    total: int
    page: int
    per_page: int


class AlertListResponse(BaseModel):
    data: list[AlertResponse]
    meta: AlertListMeta


class AlertUpdateRequest(BaseModel):
    reviewed: bool


class AlertFeedbackRequest(BaseModel):
    feedback: str  # correct | false_positive


class AlertPreferenceRequest(BaseModel):
    disabled_categories: list[str] | None = None
    immediate_severities: list[str] = ["critical", "high"]
    digest_frequency: str = "weekly"


class AlertPreferenceResponse(BaseModel):
    disabled_categories: list[str] | None
    immediate_severities: list[str]
    digest_frequency: str

    model_config = {"from_attributes": True}
