"""
FraudShield AI - Audit log routes (PART 12.18, Week 12 Day 5). Admin-only.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit import AuditLogListResponse, AuditLogOut

router = APIRouter(prefix="/audit", tags=["audit"])


def _target_label(row: AuditLog, users: dict[int, str]) -> str | None:
    """Render a row's target as something an operator can read at a glance."""
    if row.target_type == "user" and row.target_id is not None:
        return f"user {users.get(row.target_id, f'#{row.target_id}')}"
    if row.target_type in ("transaction", "case", "alert") and row.target_id is not None:
        return f"{row.target_type} #{row.target_id}"
    return None


@router.get("", response_model=AuditLogListResponse)
def list_audit_logs(
    user_id: int | None = None,
    action: str | None = None,
    page: int = 1,
    page_size: int = Query(default=20, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    query = db.query(AuditLog)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        # Accept a prefix so `auth` filters the whole auth family, and `auth.login_failed`
        # narrows to exactly that event.
        if action.endswith("*"):
            query = query.filter(AuditLog.action.like(f"{action[:-1]}%"))
        else:
            query = query.filter(AuditLog.action == action)

    total = query.count()
    items = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Resolve the display fields the UI would otherwise have to guess at: a raw
    # `user_id` of 1 is meaningless, and every login row previously showed a
    # blank target.
    user_ids = {i for i in (r.user_id for r in items) if i is not None}
    users = dict(db.query(User.id, User.email).filter(User.id.in_(user_ids)).all()) if user_ids else {}

    out = []
    for row in items:
        out.append(AuditLogOut(
            id=row.id,
            user_id=row.user_id,
            user_email=users.get(row.user_id) if row.user_id is not None else None,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            target_label=_target_label(row, users),
            detail=row.detail,
            ip_address=row.ip_address,
            created_at=row.created_at,
        ))

    actions = sorted({a for (a,) in db.query(AuditLog.action).distinct().all()})
    return AuditLogListResponse(items=out, total=total, page=page,
                                page_size=page_size, actions=actions)
