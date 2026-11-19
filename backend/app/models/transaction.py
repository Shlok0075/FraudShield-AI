from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Numeric, ForeignKey, Index, event, func, select
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Transaction(Base):
    """PART 11.5. NOTE (documented design choice, per PART 11.5's own
    alternative): user_id here is a SYNTHETIC actor id from the
    transaction simulator's small synthetic user pool, not enforced as a
    foreign key into `users` (which holds real dashboard login accounts:
    Admin/Analyst/User). Keeping it a plain indexed integer -- instead of
    an FK -- lets the simulator generate its own synthetic customer ids
    freely without needing a matching login account for every one."""
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_user_id", "user_id"),
        Index("ix_transactions_created_at", "created_at"),
        Index("ix_transactions_status", "status"),
        Index("ix_transactions_merchant_id", "merchant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(nullable=True)
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchants.id"), nullable=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


@event.listens_for(Transaction, "before_insert")
def _assign_live_transaction_id(mapper, connection, target) -> None:
    """Number the live transaction stream from 0 upward.

    The PaySim training corpus lives in this same table but occupies a NEGATIVE
    id range (see ``ml/src/paysim_ingest.py --id-base``) so that it can never
    collide with rows the running app creates. That means we cannot lean on
    SQLite's implicit ``max(rowid) + 1`` allocator: over a wholly negative
    ``id`` column it would keep handing out negative ids forever.

    So live ids get their own allocator: 0, 1, 2, ... The lookup is a single
    subquery evaluated inside the same write transaction as the INSERT, and
    SQLite serialises writers, so two concurrent requests cannot read the same
    MAX and collide. The PK is still the backstop if one ever did.

    Explicit ids supplied by the bulk loader (the corpus) are left untouched.
    """
    if target.id is not None:
        return
    highest = connection.execute(
        select(func.coalesce(func.max(Transaction.id), -1))
        .where(Transaction.id >= 0)
    ).scalar_one()
    target.id = highest + 1
