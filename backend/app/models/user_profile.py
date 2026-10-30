from datetime import datetime, timezone
from sqlalchemy import DateTime, Float, Integer, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class UserBehaviorProfile(Base):
    __tablename__ = 'user_behavior_profiles'
    __table_args__ = (Index('ix_user_profiles_user_id','user_id', unique=True),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_amount: Mapped[float] = mapped_column(Float, default=0.0)
    max_amount: Mapped[float] = mapped_column(Float, default=0.0)
    avg_daily_transactions: Mapped[float] = mapped_column(Float, default=0.0)
    fraud_rate: Mapped[float] = mapped_column(Float, default=0.0)
    normal_hours: Mapped[list | None] = mapped_column(JSON, nullable=True)
    known_devices: Mapped[list | None] = mapped_column(JSON, nullable=True)
    common_merchants: Mapped[list | None] = mapped_column(JSON, nullable=True)
    common_locations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
