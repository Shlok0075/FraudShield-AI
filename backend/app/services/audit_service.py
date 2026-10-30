"""
FraudShield AI - Audit logging service (PART 3.6 / Week 12 Day 3)
====================================================================
Every state-changing admin action writes a row here: user_id, action,
target, timestamp, ip_address.
"""
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


def log_action(
    db: Session,
    user_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: int | None = None,
    ip_address: str | None = None,
    detail: str | None = None,
) -> AuditLog:
    """Append one audit entry.

    `detail` carries short free-text context (auth events: which email was
    attempted and why it failed). Callers must never put credentials in it.
    """
    entry = AuditLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
        ip_address=ip_address,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
