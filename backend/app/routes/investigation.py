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
from sqlalchemy import func
from app.config.settings import settings
from app.services.auto_investigator import auto_investigator, sweep_once
from app.services.investigation_service import run_investigation

router = APIRouter(prefix="/investigation", tags=["investigation"])


@router.post("/auto")
def auto_investigate_open_alerts(
    request: Request,
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(["admin"])),
):
    """Run one sweep now: investigate open alerts (up to `limit`) and escalate stale cases."""
    return sweep_once(db, limit=max(1, min(limit, 1000)), min_age_s=0)


@router.get("/stats")
def investigation_stats(
    db: Session = Depends(get_db),
    current_user=Depends(require_role(["admin", "analyst"])),
):
    """How much the automation is doing, and how often analysts overrule it.

    `analyst_overrides` counts cases whose automatic verdict a human later reversed:
    an auto-cleared case reopened as confirmed fraud is the number to watch.
    """
    by_decision = dict(db.query(FraudCase.decision, func.count(FraudCase.id))
                       .group_by(FraudCase.decision).all())
    by_alert = dict(db.query(FraudAlert.status, func.count(FraudAlert.id))
                    .group_by(FraudAlert.status).all())
    auto_done = by_decision.get("auto_cleared", 0) + by_decision.get("auto_blocked", 0)
    human_done = by_decision.get("confirmed_fraud", 0) + by_decision.get("false_positive", 0)
    return {
        "cases_by_decision": {str(k or "none"): v for k, v in by_decision.items()},
        "alerts_by_status": by_alert,
        "auto_handled": auto_done,
        "analyst_decided": human_done,
        "open_alerts_waiting": by_alert.get("open", 0),
        "sweeper": auto_investigator.status(),
        "policy": {"auto_resolve_enabled": settings.AUTO_RESOLVE_ENABLED,
                   "shadow_mode": settings.AUTO_RESOLVE_SHADOW},
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

    result = run_investigation(db, alert_id, emit=True, force=True)
    return result
