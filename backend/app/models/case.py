from datetime import datetime, timezone
from sqlalchemy import String, DateTime, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class FraudCase(Base):
    __tablename__ = 'fraud_cases'
    __table_args__ = (Index('ix_fraud_cases_status','status'), Index('ix_fraud_cases_assignee','assigned_to'))
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey('fraud_alerts.id'), unique=True, nullable=False)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default='open')
    priority: Mapped[str] = mapped_column(String(20), default='medium')
    decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class CaseNote(Base):
    __tablename__ = 'case_notes'
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey('fraud_cases.id'), nullable=False, index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
