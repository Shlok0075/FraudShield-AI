"""
FraudShield AI - Alerts routes (PART 12.8-12.9, Week 10 Day 3)
==================================================================
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_role
from app.database import get_db
from app.models.fraud_alert import FraudAlert
from app.models.user import User
from app.schemas.alert import AlertOut, AlertStatusUpdate
from app.services.audit_service import log_action
from app.websocket.socket_server import emit_alert_updated

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
def list_alerts(
    status_filter: str | None = None,
    severity: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(FraudAlert)
    if status_filter:
        query = query.filter(FraudAlert.status == status_filter)
    if severity:
        query = query.filter(FraudAlert.severity == severity)
    return query.order_by(FraudAlert.created_at.desc()).all()


@router.patch("/{alert_id}", response_model=AlertOut)
async def update_alert(
    alert_id: int,
    payload: AlertStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "analyst"])),
):
    alert = db.get(FraudAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Alert not found"}})

    from datetime import datetime, timezone

    alert.status = payload.status
    if payload.status == "resolved":
        alert.resolved_at = datetime.now(timezone.utc)
        alert.resolved_by = current_user.id
    db.commit()
    db.refresh(alert)

    log_action(db, current_user.id, "alert.update_status", "alert", alert.id,
               request.client.host if request.client else None)
    await emit_alert_updated({"alert_id": alert.id, "status": alert.status})
    return alert
