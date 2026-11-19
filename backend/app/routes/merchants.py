from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.auth.dependencies import require_role
from app.database import get_db
from app.models.merchant import Merchant
from app.models.transaction import Transaction
from app.models.fraud_prediction import FraudPrediction

router = APIRouter(prefix='/merchants', tags=['merchant-risk'])


def _stats(db: Session, merchant_ids=None) -> dict[int, dict]:
    """Per-merchant volume, average amount and HIGH/CRITICAL count in two grouped queries.

    This used to load every transaction and prediction of each merchant into Python, one merchant
    at a time (2N+1 queries), and then wrote the risk score back on every page view.
    """
    base = db.query(Transaction.merchant_id, func.count(Transaction.id), func.avg(Transaction.amount)) \
        .filter(Transaction.merchant_id.is_not(None))
    risky = db.query(Transaction.merchant_id, func.count(FraudPrediction.id)) \
        .join(FraudPrediction, FraudPrediction.transaction_id == Transaction.id) \
        .filter(Transaction.merchant_id.is_not(None), FraudPrediction.risk_level.in_(('HIGH', 'CRITICAL')))
    if merchant_ids is not None:
        base = base.filter(Transaction.merchant_id.in_(merchant_ids))
        risky = risky.filter(Transaction.merchant_id.in_(merchant_ids))
    out = {mid: {'transactions': n, 'average_amount': float(avg or 0), 'fraud_count': 0}
           for mid, n, avg in base.group_by(Transaction.merchant_id).all()}
    for mid, n in risky.group_by(Transaction.merchant_id).all():
        if mid in out:
            out[mid]['fraud_count'] = n
    return out


def _row(m: Merchant, s: dict | None) -> dict:
    n = s['transactions'] if s else 0
    fraud = s['fraud_count'] if s else 0
    rate = fraud / n if n else 0
    # Risk is descriptive analytics, not a model probability.
    score = round(min(100.0, rate * 100 * 5 + min(20.0, n / 100)), 2)
    return {'id': m.id, 'name': m.name, 'category': m.category, 'transactions': n, 'fraud_count': fraud,
            'fraud_rate': round(rate, 4), 'average_amount': round(s['average_amount'], 2) if s else 0,
            'risk_score': score}


def _persist(db: Session, merchants, rows) -> None:
    """The dashboard's top-merchants panel reads Merchant.risk_score, so keep it current,
    but only touch rows whose score actually changed."""
    changed = False
    for m, r in zip(merchants, rows):
        if m.risk_score != r['risk_score']:
            m.risk_score = r['risk_score']; changed = True
    if changed:
        db.commit()


@router.get('')
def list_merchants(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
                   current_user=Depends(require_role(['admin', 'analyst']))):
    merchants = db.query(Merchant).all()
    if not merchants:
        return []
    stats = _stats(db, [m.id for m in merchants])
    rows = [_row(m, stats.get(m.id)) for m in merchants]
    _persist(db, merchants, rows)
    return sorted(rows, key=lambda x: x['risk_score'], reverse=True)[:limit]


@router.get('/{merchant_id}')
def merchant(merchant_id: int, db: Session = Depends(get_db),
             current_user=Depends(require_role(['admin', 'analyst']))):
    m = db.get(Merchant, merchant_id)
    if not m:
        raise HTTPException(status_code=404, detail={'error': {'code': 'NOT_FOUND', 'message': 'Merchant not found'}})
    row = _row(m, _stats(db, [m.id]).get(m.id))
    _persist(db, [m], [row])
    return row
