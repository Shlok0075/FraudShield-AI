from collections import defaultdict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.auth.dependencies import require_role
from app.database import get_db
from app.models.merchant import Merchant
from app.models.transaction import Transaction
from app.models.fraud_prediction import FraudPrediction

router=APIRouter(prefix='/merchants',tags=['merchant-risk'])

def calculate(db, merchant):
    txns=db.query(Transaction).filter(Transaction.merchant_id==merchant.id).all()
    ids={t.id for t in txns}
    preds=db.query(FraudPrediction).filter(FraudPrediction.transaction_id.in_(ids)).all() if ids else []
    fraud=sum(1 for p in preds if p.risk_level in ('HIGH','CRITICAL'))
    avg=sum(float(t.amount) for t in txns)/len(txns) if txns else 0
    # Risk is descriptive analytics, not a model probability.
    rate=fraud/len(txns) if txns else 0
    score=min(100.0, rate*100*5 + min(20.0,len(txns)/100))
    merchant.risk_score=round(score,2)
    return {'id':merchant.id,'name':merchant.name,'category':merchant.category,'transactions':len(txns),'fraud_count':fraud,'fraud_rate':round(rate,4),'average_amount':round(avg,2),'risk_score':merchant.risk_score}

@router.get('')
def list_merchants(db:Session=Depends(get_db),current_user=Depends(require_role(['admin','analyst']))):
    rows=[calculate(db,m) for m in db.query(Merchant).all()]
    db.commit(); return sorted(rows,key=lambda x:x['risk_score'],reverse=True)

@router.get('/{merchant_id}')
def merchant(merchant_id:int,db:Session=Depends(get_db),current_user=Depends(require_role(['admin','analyst']))):
    m=db.get(Merchant,merchant_id)
    if not m: return {'error':'Merchant not found'}
    row=calculate(db,m); db.commit(); return row
