"""
FraudShield AI — Automated Investigation Service.

Persists investigation results to the database:
  - Updates FraudAlert status (resolved / escalated)
  - Updates FraudCase (decision, summary, status, closed_at)
  - Creates CaseNote with the full investigation report
  - Triggers WebSocket event so the dashboard updates instantly
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.case import CaseNote, FraudCase
from app.models.fraud_alert import FraudAlert
from app.models.fraud_prediction import FraudPrediction
from app.models.transaction import Transaction
from app.models.user import User
from app.websocket.socket_server import emit_investigation_complete
from fraudpipe.investigation_engine import InvestigationResult, get_investigation_engine

SYSTEM_USER_ID = -1  # sentinel for automated actions


def run_investigation(
    db: Session,
    alert_id: int,
    *,
    emit: bool = True,
) -> dict[str, Any]:
    """Run automated investigation for a given alert.

    Steps:
      1. Load alert → transaction → prediction
      2. Run investigation engine
      3. Persist result to case + alert
      4. Emit WebSocket event
      5. Return investigation result dict
    """
    engine = get_investigation_engine()

    # 1. Load alert + transaction + prediction
    alert = db.get(FraudAlert, alert_id)
    if alert is None:
        raise ValueError(f"Alert {alert_id} not found")

    txn = db.get(Transaction, alert.transaction_id)
    if txn is None:
        raise ValueError(f"Transaction {alert.transaction_id} not found")

    prediction = db.execute(
        select(FraudPrediction).where(FraudPrediction.transaction_id == txn.id)
    ).scalar_one_or_none()

    # 2. Build feature/context dict for investigation
    features = {
        "amount": float(txn.amount),
        "implied_speed_kmh": None,
        "txn_count_1m": 0,
        "txn_count_1h": 0,
        "txn_count_5m": 0,
        "amount_vs_user_avg": None,
        "amount_zscore": None,
        "counterparty_fraud_rate_prior": 0.0,
        "unusual_hour": 0,
        "user_txn_count_prior": 0,
        "device_id": str(txn.device_id),
        "location": txn.location,
    }

    graph_features = {
        "graph_risk": float(prediction.graph_score or 0.0) if prediction else 0.0,
        "graph_shared_fraud_device": 0.0,
        "graph_device_farm": 0.0,
        "graph_merchant_farm": 0.0,
        "graph_merchant_fraud_concentration": 0.0,
    }

    # Merge any graph features stored on the prediction explanation
    if prediction and prediction.signal_contributions:
        for k, v in prediction.signal_contributions.items():
            if k.startswith("graph_"):
                graph_features[k] = float(v)

    # 3. Run investigation engine
    result = engine.investigate(
        ml_prob=prediction.probability if prediction else None,
        anomaly_score=prediction.anomaly_score if prediction else None,
        behavior_score=prediction.behavior_score if prediction else None,
        rule_score=prediction.rule_score if prediction else None,
        graph_score=float(prediction.graph_score or 0.0) if prediction else None,
        triggered_rules=prediction.triggered_rules or [] if prediction else [],
        features=features,
        graph_features=graph_features,
    )

    # 4. Persist to case
    case = db.execute(
        select(FraudCase).where(FraudCase.alert_id == alert_id)
    ).scalar_one_or_none()

    if case is None:
        case = FraudCase(
            alert_id=alert_id,
            assigned_to=None,
            status="open",
            priority=result.risk_level.lower(),
            summary=result.summary,
        )
        db.add(case)
        db.commit()
        db.refresh(case)

    # Update case with investigation result
    case.decision = result.decision
    case.summary = result.summary
    case.status = "closed" if result.decision in ("AUTO_BLOCK", "AUTO_CLEAR") else "open"
    if result.decision in ("AUTO_BLOCK", "AUTO_CLEAR"):
        case.closed_at = datetime.now(timezone.utc)
    db.add(case)

    # 5. Update alert
    if result.decision == "AUTO_BLOCK":
        alert.status = "resolved"
        alert.resolved_by = SYSTEM_USER_ID
        alert.resolved_at = datetime.now(timezone.utc)
    elif result.decision == "AUTO_CLEAR":
        alert.status = "resolved"
        alert.resolved_by = SYSTEM_USER_ID
        alert.resolved_at = datetime.now(timezone.utc)
    else:
        alert.status = "escalated"

    db.add(alert)

    # 6. Create case note with full investigation report
    # Find a system user or use a sentinel
    system_user = db.execute(select(User).where(User.id == abs(SYSTEM_USER_ID))).scalar_one_or_none()
    author_id = system_user.id if system_user else None

    if author_id is None:
        # Create a system user if none exists
        from app.auth.security import hash_password
        system_user = User(
            email="system@fraudshield.ai",
            password_hash=hash_password("system-auto-generated"),
            role="admin",
        )
        db.add(system_user)
        db.commit()
        db.refresh(system_user)
        author_id = system_user.id

    note = CaseNote(
        case_id=case.id,
        author_id=author_id,
        note=result.details,
    )
    db.add(note)
    db.commit()

    # 7. Emit WebSocket event (best-effort, non-blocking)
    if emit:
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(emit_investigation_complete({
                    "alert_id": alert_id,
                    "case_id": case.id,
                    "decision": result.decision,
                    "confidence": result.confidence,
                    "risk_level": result.risk_level,
                    "summary": result.summary,
                }))
        except Exception:
            pass  # WebSocket emission is best-effort

    return {
        "alert_id": alert_id,
        "case_id": case.id,
        "decision": result.decision,
        "confidence": result.confidence,
        "risk_level": result.risk_level,
        "summary": result.summary,
        "details": result.details,
        "evidence": result.evidence,
        "investigated_at": result.evidence["investigated_at"],
    }
