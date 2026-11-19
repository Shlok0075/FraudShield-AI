"""
FraudShield AI — Automated Investigation Service.

Persists investigation results to the database.

Policy (what runs without a human):
  AUTO_CLEAR  every signal low, no rule/check fired -> case closed as `auto_cleared`, alert marked
              false_positive.
  AUTO_BLOCK  model very sure AND corroborated      -> transaction `blocked`, alert escalated, case
              stays OPEN as `auto_blocked`. Confirming fraud is deliberately an analyst decision.
  REVIEW      anything else                         -> alert escalated, case open for an analyst.

Safety rails: AUTO_RESOLVE_ENABLED / AUTO_RESOLVE_SHADOW settings, a real non-login system user
for attribution, every automatic action audit-logged, and a human's decision is never overwritten.
"""

from __future__ import annotations

import math
import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.config.settings import settings
from app.models.case import CaseNote, FraudCase
from app.models.fraud_alert import FraudAlert
from app.models.fraud_prediction import FraudPrediction
from app.models.transaction import Transaction
from app.models.user import User
from app.services.audit_service import log_action
from app.websocket.socket_server import emit_investigation_complete
from fraudpipe.investigation_engine import InvestigationResult, get_investigation_engine

SYSTEM_EMAIL = "system@fraudshield.ai"
HUMAN_DECISIONS = ("confirmed_fraud", "false_positive")

_DEFAULT_CONTEXT = {
    "amount": 0.0, "implied_speed_kmh": None, "txn_count_1m": 0, "txn_count_1h": 0,
    "txn_count_5m": 0, "amount_vs_user_avg": None, "amount_zscore": None,
    "counterparty_fraud_rate_prior": 0.0, "unusual_hour": 0, "user_txn_count_prior": 0,
    "device_id": None, "location": None,
}


def get_system_user(db: Session) -> User:
    """The account automated actions are attributed to.

    Looked up by e-mail (the old code used `User.id == 1`, i.e. whichever real person registered
    first, and wrote `resolved_by = -1`, which violates the users foreign key on Postgres). The
    account can never log in: its password is random and thrown away, and its role is the
    least-privileged `user`. A system account created by older versions had role `admin` and a
    password that was hard-coded in the source; it is demoted and re-keyed here.
    """
    user = db.execute(select(User).where(User.email == SYSTEM_EMAIL)).scalar_one_or_none()
    if user is None:
        user = User(email=SYSTEM_EMAIL, password_hash=hash_password(secrets.token_urlsafe(32)), role="user")
        db.add(user)
    elif user.role != "user":
        user.role = "user"
        user.password_hash = hash_password(secrets.token_urlsafe(32))
    db.commit()
    db.refresh(user)
    return user


def _clean(value: Any) -> Any:
    """NaN -> None so the engine's `is not None` checks behave."""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def run_investigation(
    db: Session,
    alert_id: int,
    *,
    emit: bool = True,
    features: dict | None = None,
    graph_features: dict | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Investigate one alert and apply the auto-resolution policy.

    `features` / `graph_features` are the point-in-time values the scoring pipeline computed for
    this transaction. They are only available when called inline; the background sweeper has to
    rely on the signals stored on the prediction, so its checks that need history cannot fire
    (it therefore errs toward REVIEW, never toward clearing).

    A case a human already decided is left alone unless `force=True`.
    """
    engine = get_investigation_engine()

    alert = db.get(FraudAlert, alert_id)
    if alert is None:
        raise ValueError(f"Alert {alert_id} not found")
    txn = db.get(Transaction, alert.transaction_id)
    if txn is None:
        raise ValueError(f"Transaction {alert.transaction_id} not found")
    prediction = db.execute(
        select(FraudPrediction).where(FraudPrediction.transaction_id == txn.id)
    ).scalar_one_or_none()
    case = db.execute(select(FraudCase).where(FraudCase.alert_id == alert_id)).scalar_one_or_none()

    if not force and case is not None and (case.decision in HUMAN_DECISIONS or case.status == "closed"):
        return {"alert_id": alert_id, "case_id": case.id, "skipped": "case already decided"}

    ctx = dict(_DEFAULT_CONTEXT)
    ctx.update({"amount": float(txn.amount), "device_id": str(txn.device_id), "location": txn.location})
    if features:
        ctx.update({k: _clean(v) for k, v in features.items() if not k.startswith("_")})

    gf = {
        "graph_risk": float(prediction.graph_score or 0.0) if prediction else 0.0,
        "graph_shared_fraud_device": 0.0, "graph_device_farm": 0.0,
        "graph_merchant_farm": 0.0, "graph_merchant_fraud_concentration": 0.0,
    }
    if prediction and prediction.signal_contributions:
        for k, v in prediction.signal_contributions.items():
            if k.startswith("graph_"):
                gf[k] = float(v)
    if graph_features:
        gf.update({k: _clean(v) for k, v in graph_features.items()
                   if k.startswith("graph_") and isinstance(_clean(v), (int, float))})

    result = engine.investigate(
        ml_prob=prediction.probability if prediction else None,
        anomaly_score=prediction.anomaly_score if prediction else None,
        behavior_score=prediction.behavior_score if prediction else None,
        rule_score=prediction.rule_score if prediction else None,
        graph_score=float(prediction.graph_score or 0.0) if prediction else None,
        triggered_rules=(prediction.triggered_rules or []) if prediction else [],
        features=ctx,
        graph_features=gf,
    )

    # What do we actually DO with the verdict?
    acting = settings.AUTO_RESOLVE_ENABLED and not settings.AUTO_RESOLVE_SHADOW
    applied = result.decision if acting else "REVIEW"
    system_user = get_system_user(db)
    now = datetime.now(timezone.utc)

    if case is None:
        case = FraudCase(alert_id=alert_id, assigned_to=None, status="open",
                         priority=result.risk_level.lower(), summary=result.summary)
        db.add(case)
        db.commit()
        db.refresh(case)

    case.summary = result.summary
    if applied == "AUTO_CLEAR":
        case.status, case.decision, case.closed_at = "closed", "auto_cleared", now
        alert.status, alert.resolved_at, alert.resolved_by = "false_positive", now, system_user.id
        txn.status = "allowed"
    elif applied == "AUTO_BLOCK":
        case.status, case.decision, case.priority = "open", "auto_blocked", "critical"
        alert.status = "escalated"
        txn.status = "blocked"
    else:
        case.status, case.decision = "open", "needs_review"
        case.priority = result.risk_level.lower()
        alert.status = "escalated"
    db.add_all([case, alert, txn])

    report = result.details
    if not acting:
        reason = "auto-resolve is disabled" if not settings.AUTO_RESOLVE_ENABLED else "SHADOW MODE"
        report = (f"[{reason}] The engine's verdict was {result.decision}; nothing was changed "
                  f"automatically and the case is waiting for an analyst.\n\n") + report
    db.add(CaseNote(case_id=case.id, author_id=system_user.id, note=report))
    db.commit()

    log_action(db, system_user.id, f"investigation.{applied.lower()}", "alert", alert_id,
               detail=f"verdict={result.decision}; confidence={result.confidence}; acting={acting}")

    if emit:
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            loop.create_task(emit_investigation_complete({
                "alert_id": alert_id, "case_id": case.id, "decision": result.decision,
                "confidence": result.confidence, "risk_level": result.risk_level,
                "summary": result.summary,
            }))
        except Exception:
            pass  # WebSocket emission is best-effort (and there is no loop in a worker thread)

    return {
        "alert_id": alert_id,
        "case_id": case.id,
        "decision": result.decision,
        "applied": applied,
        "acting": acting,
        "confidence": result.confidence,
        "risk_level": result.risk_level,
        "summary": result.summary,
        "details": result.details,
        "evidence": result.evidence,
        "investigated_at": result.evidence["investigated_at"],
    }
