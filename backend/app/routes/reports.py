"""
FraudShield AI - Reporting routes (PART 3.5, PART 12.17, Week 15)
=====================================================================
GET /reports/export?format=csv -- queries filtered transactions/alerts,
builds a Pandas DataFrame, and returns a CSV file download.
"""
import io

import pandas as pd
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import require_role
from app.database import get_db
from app.models.fraud_prediction import FraudPrediction
from app.models.transaction import Transaction
from app.models.user import User

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/export")
def export_report(
    format: str = Query(default="csv", pattern="^(csv)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["admin", "analyst"])),
):
    rows = (
        db.query(
            Transaction.id, Transaction.user_id, Transaction.amount,
            Transaction.currency, Transaction.status, Transaction.created_at,
            FraudPrediction.risk_score, FraudPrediction.risk_level,
        )
        .outerjoin(FraudPrediction, FraudPrediction.transaction_id == Transaction.id)
        .all()
    )
    df = pd.DataFrame(rows, columns=[
        "transaction_id", "user_id", "amount", "currency", "status",
        "created_at", "risk_score", "risk_level",
    ])
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=fraudshield_report.csv"},
    )
