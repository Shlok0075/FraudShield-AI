from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditLog(Base):
    """PART 11.8."""
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_created_at_id", "created_at", "id"),   # newest-first paging
        Index("ix_audit_logs_action", "action"),                    # action filter + distinct list
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Free-text context for auth events: which email was attempted, and for a
    # failed login why it was rejected. Never contains a submitted password.
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
