import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.auth.dependencies import require_role
from app.database import get_db
from app.models.feedback import FraudFeedback
from app.models.fraud_prediction import FraudPrediction
from app.models.transaction import Transaction
from app.services.audit_service import log_action
from pydantic import BaseModel, Field

router=APIRouter(prefix='/feedback',tags=['feedback'])
class FeedbackCreate(BaseModel):
    prediction_id:int=Field(gt=0)
    case_id:int|None=None
    label:str=Field(pattern='^(confirmed_fraud|false_positive|unresolved)$')
    reason:str|None=None

@router.post('',status_code=201)
def create_feedback(payload:FeedbackCreate,request:Request,db:Session=Depends(get_db),current_user=Depends(require_role(['admin','analyst']))):
    pred=db.get(FraudPrediction,payload.prediction_id)
    if not pred: raise HTTPException(404,'Prediction not found')
    txn=db.get(Transaction,pred.transaction_id)
    snapshot={'amount':float(txn.amount),'risk_score':pred.risk_score,'probability':pred.probability,'anomaly_score':pred.anomaly_score,'behavior_score':pred.behavior_score,'rule_score':pred.rule_score,'model_version':pred.model_version}
    f=FraudFeedback(prediction_id=pred.id,case_id=payload.case_id,reviewer_id=current_user.id,label=payload.label,reason=payload.reason,feature_snapshot=snapshot)
    db.add(f); db.commit(); db.refresh(f)
    log_action(db,current_user.id,'feedback.create','prediction',pred.id,request.client.host if request.client else None)
    return {'id':f.id,'label':f.label,'prediction_id':f.prediction_id,'feature_snapshot':snapshot}

@router.get('')
def list_feedback(db:Session=Depends(get_db),current_user=Depends(require_role(['admin','analyst']))):
    return [{'id':f.id,'prediction_id':f.prediction_id,'case_id':f.case_id,'label':f.label,'reason':f.reason,'created_at':f.created_at} for f in db.query(FraudFeedback).order_by(FraudFeedback.created_at.desc()).limit(200).all()]

@router.post('/retraining-manifest')
def retraining_manifest(db:Session=Depends(get_db),current_user=Depends(require_role(['admin']))):
    rows=db.query(FraudFeedback).order_by(FraudFeedback.created_at.asc()).all()
    out=Path('ml/models/feedback_retraining_manifest.json')
    out.parent.mkdir(parents=True,exist_ok=True)
    payload={'generated_by':current_user.email,'records':len(rows),'labels':{'confirmed_fraud':sum(r.label=='confirmed_fraud' for r in rows),'false_positive':sum(r.label=='false_positive' for r in rows),'unresolved':sum(r.label=='unresolved' for r in rows)},'feedback_ids':[r.id for r in rows]}
    out.write_text(json.dumps(payload,indent=2))
    return payload
