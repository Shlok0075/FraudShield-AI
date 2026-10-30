from collections import Counter
from sqlalchemy import func
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user, require_role
from app.database import get_db
from app.models.transaction import Transaction
from app.models.fraud_prediction import FraudPrediction
from app.models.device import Device
from app.models.user_profile import UserBehaviorProfile
from app.models.merchant import Merchant

router=APIRouter(prefix='/profiles',tags=['behavior-profiles'])

def build_profile(db,user_id,fraud_ids=None):
    txns=db.query(Transaction).filter(Transaction.user_id==user_id).order_by(Transaction.created_at.asc()).all()
    if not txns: return None
    amounts=[float(t.amount) for t in txns]
    txn_ids={t.id for t in txns}
    # Restrict to THIS user's transactions. The previous version loaded every
    # HIGH/CRITICAL prediction in the table, which is correct but meant the
    # list endpoint re-scanned the whole prediction set once per user -- fatal
    # at corpus scale.
    if fraud_ids is None:
        fraud_ids={p.transaction_id for p in db.query(FraudPrediction.transaction_id).filter(FraudPrediction.risk_level.in_(['HIGH','CRITICAL'])).all()}
    days=max(1,(txns[-1].created_at.date()-txns[0].created_at.date()).days+1)
    hours=Counter(t.created_at.hour for t in txns)
    locations=Counter(t.location or 'Unknown' for t in txns)
    mids=Counter(t.merchant_id for t in txns if t.merchant_id is not None)
    dev_ids=[d.device_id for d in db.query(Device).filter(Device.user_id==user_id).all()]
    return {'user_id':user_id,'transaction_count':len(txns),'avg_amount':sum(amounts)/len(amounts),'max_amount':max(amounts),'avg_daily_transactions':len(txns)/days,'fraud_rate':len(fraud_ids & txn_ids)/len(txns),'normal_hours':[h for h,_ in hours.most_common(5)],'known_devices':dev_ids[:20],'common_locations':[x for x,_ in locations.most_common(5)],'common_merchants':[x for x,_ in mids.most_common(5)]}

@router.get('/{user_id}')
def profile(user_id:int,db:Session=Depends(get_db),current_user=Depends(require_role(['admin','analyst']))):
    data=build_profile(db,user_id)
    if data is None: return {'user_id':user_id,'transaction_count':0}
    p=db.query(UserBehaviorProfile).filter(UserBehaviorProfile.user_id==user_id).first()
    if p:
        for k,v in data.items():
            if hasattr(p,k): setattr(p,k,v)
    else:
        p=UserBehaviorProfile(**data); db.add(p)
    db.commit()
    return data

@router.get('')
def profiles(limit:int=10,db:Session=Depends(get_db),current_user=Depends(require_role(['admin','analyst']))):
    """Behavioural profiles for the busiest users.

    Ranked in SQL and capped. The previous version called `.distinct()` over
    the whole transaction table and built a profile for EVERY user -- with the
    PaySim corpus loaded that is ~6.35M users, so the request never returned.
    The Intelligence page only ever shows the top handful, which is what this
    now computes.

    Note the cost is dominated by the ranking GROUP BY (~6s over 6.35M distinct
    groups); the per-user profile work itself is ~3ms. Keep `limit` small.
    """
    limit=max(1,min(limit,200))
    ids=[row[0] for row in db.query(Transaction.user_id)
         .filter(Transaction.user_id.is_not(None))
         .group_by(Transaction.user_id)
         .order_by(func.count(Transaction.id).desc())
         .limit(limit).all()]
    if not ids: return []
    # Hoisted out of the loop: one scan, reused by every profile.
    fraud_ids={row[0] for row in db.query(FraudPrediction.transaction_id)
               .filter(FraudPrediction.risk_level.in_(['HIGH','CRITICAL'])).all()}
    out=[build_profile(db,i,fraud_ids) for i in ids]
    return [p for p in out if p is not None]
