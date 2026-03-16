from datetime import datetime
from pydantic import BaseModel, Field


class BootstrapRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64)
    status: str = Field(default="active", min_length=1, max_length=32)


class AgentSessionResponse(BaseModel):
    session_id: str
    status: str
    created_at: datetime
    last_seen_at: datetime
