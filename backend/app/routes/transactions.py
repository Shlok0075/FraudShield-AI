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
from app.models.case import FraudCase
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
