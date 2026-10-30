from datetime import datetime, timezone
from sqlalchemy import DateTime, String, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class SecurityEvent(Base):
    __tablename__ = 'security_events'
    id: Mapped[int] = mapped_column(primary_key=True)
    check_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
