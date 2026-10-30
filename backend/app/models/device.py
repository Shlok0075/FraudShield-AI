from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Device(Base):
    """PART 11.4. user_id is a synthetic actor id (see Transaction model's
    docstring) -- not an FK into the real `users` login table."""
    __tablename__ = "devices"
    __table_args__ = (Index("ix_devices_user_device", "user_id", "device_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(nullable=True)
    device_id: Mapped[str] = mapped_column(String(255), nullable=False)
    device_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
