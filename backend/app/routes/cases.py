from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user, require_role
from app.database import get_db
from app.models.case import FraudCase, CaseNote
from app.models.fraud_alert import FraudAlert
from app.models.user import User
from app.schemas.case import CaseCreate, CaseUpdate, NoteCreate
from app.services.audit_service import log_action

router = APIRouter(prefix='/cases', tags=['cases'])

def _note_dict(n):
    return {'id':n.id,'author_id':n.author_id,'note':n.note,'created_at':n.created_at}

def _case_dict(db, c, notes=None):
    """`notes` lets list views pass notes they already fetched in ONE batched query."""
    if notes is None:
        notes = db.query(CaseNote).filter(CaseNote.case_id == c.id).order_by(CaseNote.created_at.asc()).all()
    return {'id':c.id,'alert_id':c.alert_id,'assigned_to':c.assigned_to,'status':c.status,'priority':c.priority,'decision':c.decision,'summary':c.summary,'created_at':c.created_at,'updated_at':c.updated_at,'closed_at':c.closed_at,'notes':[_note_dict(n) for n in notes]}

@router.get('')
def list_cases(status_filter: str|None=None,
               limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
               db:Session=Depends(get_db), current_user:User=Depends(require_role(['admin','analyst']))):
    q=db.query(FraudCase)
    if status_filter: q=q.filter(FraudCase.status==status_filter)
    cases=q.order_by(FraudCase.updated_at.desc(), FraudCase.id.desc()).offset(offset).limit(limit).all()
    # One query for every case's notes instead of one per case. This used to be an N+1: 5,000
    # cases meant 5,002 SQL round trips (1.5s even against a local database, many seconds
    # with a hosted Postgres where each round trip costs milliseconds).
    by_case: dict[int, list] = {c.id: [] for c in cases}
    if by_case:
        for n in (db.query(CaseNote).filter(CaseNote.case_id.in_(by_case))
                  .order_by(CaseNote.created_at.asc(), CaseNote.id.asc()).all()):
            by_case[n.case_id].append(n)
    return [_case_dict(db, c, by_case[c.id]) for c in cases]

@router.post('', status_code=201)
def create_case(payload:CaseCreate, request:Request, db:Session=Depends(get_db), current_user:User=Depends(require_role(['admin','analyst']))):
    alert=db.get(FraudAlert,payload.alert_id)
    if not alert: raise HTTPException(404,'Alert not found')
    existing=db.query(FraudCase).filter(FraudCase.alert_id==alert.id).first()
    if existing: return _case_dict(db,existing)
    c=FraudCase(alert_id=alert.id,assigned_to=payload.assigned_to or current_user.id,priority=payload.priority,summary=payload.summary)
    db.add(c); db.commit(); db.refresh(c)
    log_action(db,current_user.id,'case.create','case',c.id,request.client.host if request.client else None)
    return _case_dict(db,c)

@router.get('/{case_id}')
def get_case(case_id:int, db:Session=Depends(get_db), current_user:User=Depends(require_role(['admin','analyst']))):
    c=db.get(FraudCase,case_id)
    if not c: raise HTTPException(404,'Case not found')
    return _case_dict(db,c)

@router.patch('/{case_id}')
def update_case(case_id:int,payload:CaseUpdate,request:Request,db:Session=Depends(get_db),current_user:User=Depends(require_role(['admin','analyst']))):
    c=db.get(FraudCase,case_id)
    if not c: raise HTTPException(404,'Case not found')
    data=payload.model_dump(exclude_unset=True)
    for k,v in data.items(): setattr(c,k,v)
    if c.status=='closed' or c.decision in ('confirmed_fraud','false_positive'):
        c.closed_at=c.closed_at or datetime.now(timezone.utc)
    db.commit(); db.refresh(c)
    log_action(db,current_user.id,'case.update','case',c.id,request.client.host if request.client else None)
    return _case_dict(db,c)

@router.post('/{case_id}/notes',status_code=201)
def add_note(case_id:int,payload:NoteCreate,request:Request,db:Session=Depends(get_db),current_user:User=Depends(require_role(['admin','analyst']))):
    c=db.get(FraudCase,case_id)
    if not c: raise HTTPException(404,'Case not found')
    n=CaseNote(case_id=c.id,author_id=current_user.id,note=payload.note)
    db.add(n); db.commit(); db.refresh(n)
    log_action(db,current_user.id,'case.add_note','case',c.id,request.client.host if request.client else None)
    return {'id':n.id,'case_id':n.case_id,'author_id':n.author_id,'note':n.note,'created_at':n.created_at}
