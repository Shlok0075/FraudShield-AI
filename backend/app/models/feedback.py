from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class FraudFeedback(Base):
    __tablename__ = 'fraud_feedback'
    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey('fraud_predictions.id'), nullable=False, index=True)
    case_id: Mapped[int | None] = mapped_column(ForeignKey('fraud_cases.id'), nullable=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    label: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    feature_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
