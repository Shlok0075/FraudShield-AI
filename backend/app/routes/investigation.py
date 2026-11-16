"""
FraudShield AI — Automated Investigation API routes.

Endpoints:
  POST   /investigate/{alert_id}   Run automated investigation for an alert
  GET    /investigation/{case_id}  Get investigation result for a case
  POST   /investigate/auto         Auto-investigate all open alerts
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.fraud_alert import FraudAlert
from app.models.case import FraudCase
from app.services.investigation_service import run_investigation, SYSTEM_USER_ID

router = APIRouter(prefix="/investigation", tags=["investigation"])


@router.post("/auto")
def auto_investigate_open_alerts(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    """Auto-investigate all open alerts (batch)."""
    open_alerts = db.query(FraudAlert).filter(FraudAlert.status == "open").all()
    results = []
    for alert in open_alerts:
        try:
            result = run_investigation(db, alert.id, emit=True)
            results.append(result)
        except Exception as exc:  # pragma: no cover - best effort
            results.append({"alert_id": alert.id, "error": str(exc)})
    return {
        "investigated": len(results),
        "results": results,
    }


@router.post("/{alert_id}")
def investigate_alert(
    alert_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(["admin", "analyst"])),
):
    """Run automated investigation for a specific alert."""
    alert = db.get(FraudAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Alert not found"}})

    result = run_investigation(db, alert_id, emit=True)
    return result
