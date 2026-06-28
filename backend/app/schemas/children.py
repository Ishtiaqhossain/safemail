import uuid
from datetime import datetime
from pydantic import BaseModel


class ChildCreate(BaseModel):
    display_name: str
    birth_year: int | None = None


class ChildUpdate(BaseModel):
    display_name: str | None = None
    birth_year: int | None = None


class GmailConnectionResponse(BaseModel):
    id: uuid.UUID
    provider: str
    gmail_address: str
    status: str
    last_synced_at: datetime | None

    model_config = {"from_attributes": True}


class ChildResponse(BaseModel):
    id: uuid.UUID
    display_name: str
    birth_year: int | None
    created_at: datetime
    gmail_connections: list[GmailConnectionResponse] = []

    model_config = {"from_attributes": True}
