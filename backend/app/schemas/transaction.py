from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TransactionCreate(BaseModel):
    """PART 12.4 -- synthetic schema example used by the simulator/API."""
    user_id: int = Field(gt=0)
    amount: float = Field(gt=0, le=10_000_000)
    merchant_id: Optional[int] = None
    device_id: str = Field(min_length=1, max_length=255)
    location: Optional[str] = None
    ip_address: Optional[str] = None
    payment_method: Optional[str] = "card"
    currency: str = "INR"


class ExplanationItem(BaseModel):
    feature: str
    label: str
    impact: float
    direction: str


class PredictionResponse(BaseModel):
    transaction_id: int
    probability: float
    risk_score: int
    final_risk_score: float | None = None
    risk_level: str
    decision: str
    hybrid_decision: str | None = None
    anomaly_score: float | None = None
    behavior_score: float | None = None
    rule_score: float | None = None
    triggered_rules: list[dict] = []
    reasons: list[str] = []
    signal_contributions: dict[str, float] = {}
    weights_used: dict[str, float] = {}
    model_version: str | None = None
    explanation: list[ExplanationItem]


class TransactionOut(BaseModel):
    id: int
    user_id: Optional[int]
    merchant_id: Optional[int]
    amount: float
    currency: str
    location: Optional[str]
    payment_method: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionListResponse(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int


class TransactionActionRequest(BaseModel):
    action: str = Field(pattern="^(mark_reviewed|mark_false_positive|escalate|resolve)$")
