from datetime import datetime, timezone
from sqlalchemy import DateTime, Float, String, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class DriftSnapshot(Base):
    __tablename__ = 'drift_snapshots'
    id: Mapped[int] = mapped_column(primary_key=True)
    metric: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
