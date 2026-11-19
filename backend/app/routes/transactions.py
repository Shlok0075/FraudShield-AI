"""
FraudShield AI - Transaction & Prediction routes (PART 12.4-12.7, Week 8)
=============================================================================
POST /transactions/predict : validate -> build features -> predict ->
  decide -> persist transaction+prediction -> maybe create alert -> emit
  WebSocket events -> return full result.
GET  /transactions          : paginated list with filters.
GET  /transactions/{id}/detail : full detail + explanation + user history.
PATCH /transactions/{id}/action : admin/analyst action, writes audit log.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_role
from app.database import get_db
from app.ml.model_service import ModelService
from app.models.device import Device
from app.models.fraud_alert import FraudAlert
from app.models.case import CaseNote, FraudCase
from app.routes.cases import _investigation, queue_of
from app.models.fraud_prediction import FraudPrediction
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.transaction import (
    PredictionResponse,
    TransactionActionRequest,
    TransactionCreate,
    TransactionListResponse,
    TransactionOut,
)
from app.services.audit_service import log_action
from app.services.feature_engineering import build_features
from app.services.prediction_pipeline import ingest_transaction
from app.utils.rate_limit import limiter
from app.websocket.socket_server import emit_new_alert, emit_new_transaction

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("/predict", response_model=PredictionResponse)
@limiter.limit("60/minute")
async def predict_transaction(
    request: Request,
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Validate -> score -> persist -> alert -> broadcast.

    The pipeline itself lives in `services.prediction_pipeline` so this endpoint
    and the built-in live feed cannot drift apart.
    """
    result = await ingest_transaction(db, payload.model_dump())
    return PredictionResponse(**result)


@router.get("", response_model=TransactionListResponse)
def list_transactions(
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Transaction)
    if status_filter:
        query = query.filter(Transaction.status == status_filter)
    total = query.count()
    items = (
        query.order_by(Transaction.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return TransactionListResponse(items=items, total=total, page=page, page_size=page_size)


_OUTCOMES = {
    "auto_cleared": ("cleared", "Cleared automatically", "Every signal was low, so the system closed the alert as a false positive."),
    "auto_blocked": ("blocked", "Blocked automatically", "The system blocked this transaction. An analyst confirms fraud or overturns the block."),
    "needs_review": ("review", "Waiting for an analyst", "The system could not decide on its own. It is in the Needs review queue."),
    "closed": ("closed", "Decided by an analyst", "An analyst made the final decision."),
}


def automated_outcome(db: Session, txn: Transaction) -> dict:
    """What the system did with this transaction, so nobody has to pick a status by hand."""
    alert = db.query(FraudAlert).filter(FraudAlert.transaction_id == txn.id).first()
    if alert is None:
        return {"state": "allowed", "label": "Allowed automatically",
                "detail": "No alert was raised, so no action is needed.",
                "alert_id": None, "case_id": None, "queue": None, "can_decide": False, "investigation": None}
    case = db.query(FraudCase).filter(FraudCase.alert_id == alert.id).first()
    if case is None:
        return {"state": "pending", "label": "Investigation pending",
                "detail": "The automated investigator will pick this up on its next sweep.",
                "alert_id": alert.id, "case_id": None, "queue": None, "can_decide": False, "investigation": None}
    queue = queue_of(case.decision, case.status)
    state, label, detail = _OUTCOMES[queue]
    if queue == "closed" and case.decision:
        label = f"Decided by an analyst: {case.decision.replace('_', ' ')}"
    notes = db.query(CaseNote).filter(CaseNote.case_id == case.id).order_by(CaseNote.created_at.asc(), CaseNote.id.asc()).all()
    return {"state": state, "label": label, "detail": detail, "alert_id": alert.id, "case_id": case.id,
            "queue": queue, "can_decide": queue != "closed", "investigation": _investigation(notes)}


@router.get("/{transaction_id}/detail")
def transaction_detail(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    txn = db.get(Transaction, transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Transaction not found"}})
    prediction = db.query(FraudPrediction).filter(FraudPrediction.transaction_id == txn.id).first()

    related = (
        db.query(Transaction)
        .filter(Transaction.user_id == txn.user_id, Transaction.id != txn.id)
        .order_by(Transaction.created_at.desc())
        .limit(5)
        .all()
    )

    return {
        "transaction": TransactionOut.model_validate(txn).model_dump(),
        "prediction": {
            "probability": prediction.probability,
            "risk_score": prediction.risk_score,
            "risk_level": prediction.risk_level,
            "model_version": prediction.model_version,
            "decision": prediction.decision,
            "anomaly_score": prediction.anomaly_score,
            "behavior_score": prediction.behavior_score,
            "rule_score": prediction.rule_score,
            "triggered_rules": prediction.triggered_rules,
            "reasons": prediction.reasons,
            "signal_contributions": prediction.signal_contributions,
            "weights_used": prediction.weights_used,
            "explanation": prediction.explanation,
        } if prediction else None,
        "related_transactions": [TransactionOut.model_validate(r).model_dump() for r in related],
        "outcome": automated_outcome(db, txn),
        "user_recent_history_count": len(related),
    }


@router.patch("/{transaction_id}/action")
def transaction_action(
    transaction_id: int,
    payload: TransactionActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "analyst"])),
):
    txn = db.get(Transaction, transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Transaction not found"}})

    new_status_map = {
        "mark_reviewed": "reviewed",
        "mark_false_positive": "false_positive",
        "escalate": "escalated",
        "resolve": "resolved",
    }
    new_status = new_status_map[payload.action]
    txn.status = new_status
    db.commit()

    log_action(
        db, current_user.id, f"transaction.{payload.action}", "transaction", txn.id,
        request.client.host if request.client else None,
    )
    return {"transaction_id": txn.id, "new_status": new_status}
