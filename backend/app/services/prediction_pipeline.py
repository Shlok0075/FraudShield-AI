"""
FraudShield AI - Single source of truth for the fraud-scoring pipeline.
=======================================================================
`ingest_transaction` is the whole "score a transaction and act on it" flow:
build features -> predict -> persist transaction/prediction -> create alert
and case -> emit WebSocket events.

It lives here rather than inline in `routes/transactions.py` so that the
built-in live feed (`services/live_feed.py`) and the HTTP endpoint drive
*exactly* the same code. When the feed was a separate POST-per-transaction
simulator, any change to the pipeline had to be made twice, and the dashboard
silently diverged from what the endpoint actually did.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml.model_service import ModelService
from app.models.device import Device
from app.models.fraud_alert import FraudAlert
from app.models.fraud_prediction import FraudPrediction
from app.models.case import FraudCase
from app.models.transaction import Transaction
from app.services.feature_engineering import build_features
from app.websocket.socket_server import emit_new_alert, emit_new_transaction

# Human-facing labels kept for API compatibility, alongside the normalized
# ALLOW/REVIEW/BLOCK decision the pipeline actually makes.
LEGACY_DECISIONS = {"ALLOW": "Allow", "REVIEW": "Monitor", "BLOCK": "Critical Alert"}

CASE_PRIORITY = {"CRITICAL": "critical", "HIGH": "high",
                 "MEDIUM": "medium", "LOW": "low"}


async def ingest_transaction(
    db: Session,
    payload: dict,
    *,
    emit: bool = True,
) -> dict:
    """Run one transaction through the full pipeline and return the result.

    `emit=False` suppresses the WebSocket broadcasts (used by tests and by
    backfills that should not spam connected dashboards).
    """
    # 1. Feature engineering MUST happen before the current transaction/device is
    # persisted. This prevents current-row leakage and lets the shared
    # FeatureEngine correctly identify a genuinely new device.
    features = build_features(db, payload)

    # 2. ML + anomaly + behavioral + deterministic-rule risk scoring.
    result = ModelService.predict(features)

    # 3. Register the device only AFTER feature computation.
    device = db.execute(
        select(Device).where(Device.user_id == payload["user_id"],
                             Device.device_id == payload["device_id"])
    ).scalar_one_or_none()
    if device is None:
        device = Device(user_id=payload["user_id"], device_id=payload["device_id"],
                        device_type="synthetic")
        db.add(device)
        db.commit()
        db.refresh(device)

    # 4. Persist the transaction.
    txn = Transaction(
        user_id=payload["user_id"],
        merchant_id=payload.get("merchant_id"),
        device_id=device.id,
        amount=payload["amount"],
        currency=payload.get("currency") or "INR",
        location=payload.get("location"),
        ip_address=payload.get("ip_address"),
        payment_method=payload.get("payment_method"),
        status="flagged" if result["create_alert"] else "allowed",
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)

    # 5. Persist the prediction and hybrid signal details.
    prediction = FraudPrediction(
        transaction_id=txn.id,
        probability=result["probability"],
        risk_score=result["risk_score"],
        risk_level=result["risk_level"],
        model_version=result["model_version"],
        explanation=result["explanation"],
        anomaly_score=result.get("anomaly_score"),
        behavior_score=result.get("behavior_score"),
        rule_score=result.get("rule_score"),
        triggered_rules=result.get("triggered_rules", []),
        reasons=result.get("reasons", []),
        signal_contributions=result.get("signal_contributions", {}),
        weights_used=result.get("weights_used", {}),
    )
    db.add(prediction)
    db.commit()

    # 6. Create an alert for REVIEW/BLOCK, plus an investigation case.
    alert = None
    if result["create_alert"]:
        alert = FraudAlert(
            transaction_id=txn.id,
            severity=result["alert_severity"],
            status="open",
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        if result["decision"] in ("REVIEW", "BLOCK"):
            case = FraudCase(
                alert_id=alert.id,
                assigned_to=None,
                status="open",
                priority=CASE_PRIORITY.get(result["risk_level"], "medium"),
                summary="Auto-created from hybrid fraud alert.",
            )
            db.add(case)
            db.commit()

    # 7. Emit WebSocket events so the dashboard updates instantly.
    txn_payload = {
        "transaction_id": txn.id, "user_id": txn.user_id, "amount": float(txn.amount),
        "risk_level": result["risk_level"], "risk_score": result["risk_score"],
        "status": txn.status,
        "created_at": (txn.created_at or datetime.now(timezone.utc)).isoformat(),
    }
    if emit:
        await emit_new_transaction(txn_payload)
        if alert is not None:
            await emit_new_alert({**txn_payload, "alert_id": alert.id,
                                  "severity": alert.severity})

    return {
        "transaction_id": txn.id,
        "probability": result["probability"],
        "risk_score": result["risk_score"],
        "final_risk_score": result.get("final_risk_score"),
        "risk_level": result["risk_level"],
        "decision": LEGACY_DECISIONS[result["decision"]],
        "hybrid_decision": result["decision"],
        "anomaly_score": result.get("anomaly_score"),
        "behavior_score": result.get("behavior_score"),
        "rule_score": result.get("rule_score"),
        "triggered_rules": result.get("triggered_rules", []),
        "reasons": result.get("reasons", []),
        "signal_contributions": result.get("signal_contributions", {}),
        "weights_used": result.get("weights_used", {}),
        "model_version": result.get("model_version"),
        "explanation": result["explanation"],
        "alert_id": alert.id if alert is not None else None,
    }
