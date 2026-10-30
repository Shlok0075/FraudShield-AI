from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Float, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FraudPrediction(Base):
    """PART 11.6."""
    __tablename__ = "fraud_predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), unique=True)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    explanation: Mapped[list | None] = mapped_column(JSON, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    behavior_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rule_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    triggered_rules: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)
    signal_contributions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    weights_used: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
