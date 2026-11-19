"""
FraudShield AI - Single source of truth for the fraud-scoring pipeline.
=======================================================================
`ingest_transaction` is the whole "score a transaction and act on it" flow:
build features -> predict -> persist transaction/prediction -> create alert
and case -> auto-investigate -> emit WebSocket events.

It lives here rather than inline in `routes/transactions.py` so that the
built-in live feed (`services/live_feed.py`) and the HTTP endpoint drive
*exactly* the same code. When the feed was a separate POST-per-transaction
simulator, any change to the pipeline had to be made twice, and the dashboard
silently diverged from what the endpoint actually did.
"""
import asyncio
import threading
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
from app.services.investigation_service import run_investigation
from app.websocket.socket_server import emit_investigation_complete, emit_new_alert, emit_new_transaction
from fraudpipe.graph_engine import build_graph_features, record_transaction

# Human-facing labels kept for API compatibility, alongside the normalized
# ALLOW/REVIEW/BLOCK decision the pipeline actually makes.
LEGACY_DECISIONS = {"ALLOW": "Allow", "REVIEW": "Monitor", "BLOCK": "Critical Alert"}

CASE_PRIORITY = {"CRITICAL": "critical", "HIGH": "high",
                 "MEDIUM": "medium", "LOW": "low"}


# The scoring work below is blocking (DB queries, XGBoost, SHAP). Running it directly inside an
# `async def` froze the entire event loop for its whole duration (~0.4s per transaction before
# the merchant-count fix), so every dashboard request that arrived meanwhile had to wait. It now
# runs in a worker thread. The lock serialises ingests: the in-memory graph engine and the
# model's explainer are shared and not written for concurrent mutation.
_INGEST_LOCK = threading.Lock()


def _score_and_persist(db: Session, payload: dict) -> tuple[dict, list[tuple[str, dict]]]:
    """Blocking half of the pipeline. Returns (response, websocket_events_to_emit)."""
    # 1. Feature engineering MUST happen before the current transaction/device is
    # persisted. This prevents current-row leakage and lets the shared
    # FeatureEngine correctly identify a genuinely new device.
    features = build_features(db, payload)

    # 2. Build graph-based fraud ring features from live graph.
    graph_features = build_graph_features(db, payload)
    features["_graph_features"] = graph_features

    # 3. ML + anomaly + behavior + rules + graph risk scoring.
    result = ModelService.predict(features)

    # 4. Register the device only AFTER feature computation.
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

    # 5. Persist the transaction.
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

    # 6. Record transaction into live graph for future fraud-ring scoring.
    ts = (txn.created_at or datetime.now(timezone.utc)).timestamp()
    record_transaction(db, txn, device, str(payload["user_id"]),
                       str(payload.get("device_id") or "unknown"),
                       str(payload.get("merchant_id") or "unknown"),
                       ts=ts)

    # 7. Persist the prediction and hybrid signal details.
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
        graph_score=result.get("graph_score"),
        triggered_rules=result.get("triggered_rules", []),
        reasons=result.get("reasons", []),
        signal_contributions=result.get("signal_contributions", {}),
        weights_used=result.get("weights_used", {}),
    )
    db.add(prediction)
    db.commit()

    # 8. Create an alert for REVIEW/BLOCK, plus an investigation case.
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

    # 9. Auto-investigate REVIEW/BLOCK alerts (investigation engine runs synchronously).
    investigation = None
    if result["create_alert"] and result["decision"] in ("REVIEW", "BLOCK"):
        try:
            investigation = run_investigation(
                db, alert.id, emit=False,
                features=features, graph_features=features.get("_graph_features"))
            result["investigation"] = {
                "decision": investigation["decision"],
                "confidence": investigation["confidence"],
                "risk_level": investigation["risk_level"],
                "summary": investigation["summary"],
                "case_id": investigation["case_id"],
            }
        except Exception:
            # Investigation failure must not block the transaction response
            result["investigation"] = None

    # 10. Emit WebSocket events so the dashboard updates instantly.
    txn_payload = {
        "transaction_id": txn.id, "user_id": txn.user_id, "amount": float(txn.amount),
        "risk_level": result["risk_level"], "risk_score": result["risk_score"],
        "status": txn.status,
        "created_at": (txn.created_at or datetime.now(timezone.utc)).isoformat(),
    }
    events: list[tuple[str, dict]] = [("transaction", txn_payload)]
    if alert is not None:
        events.append(("alert", {**txn_payload, "alert_id": alert.id, "severity": alert.severity}))
    if investigation is not None:
        events.append(("investigation", {
            "alert_id": alert.id, "case_id": investigation["case_id"],
            "decision": investigation["decision"], "confidence": investigation["confidence"],
            "risk_level": investigation["risk_level"], "summary": investigation["summary"],
        }))

    response = {
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
        "graph_score": result.get("graph_score"),
        "triggered_rules": result.get("triggered_rules", []),
        "reasons": result.get("reasons", []),
        "signal_contributions": result.get("signal_contributions", {}),
        "weights_used": result.get("weights_used", {}),
        "model_version": result.get("model_version"),
        "explanation": result["explanation"],
        "investigation": investigation,
        "alert_id": alert.id if alert is not None else None,
    }
    return response, events


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
    def work():
        with _INGEST_LOCK:
            return _score_and_persist(db, payload)

    response, events = await asyncio.to_thread(work)
    if emit:
        for kind, body in events:
            if kind == "transaction":
                await emit_new_transaction(body)
            elif kind == "alert":
                await emit_new_alert(body)
            elif kind == "investigation":
                await emit_investigation_complete(body)
    return response
