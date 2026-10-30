from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AlertOut(BaseModel):
    id: int
    transaction_id: int
    severity: str
    status: str
    created_at: datetime
    resolved_at: Optional[datetime]

    class Config:
        from_attributes = True


class AlertStatusUpdate(BaseModel):
    status: str = Field(pattern="^(open|reviewed|false_positive|escalated|resolved)$")
