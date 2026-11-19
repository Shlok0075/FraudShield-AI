import re
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import case as sql_case, func
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user, require_role
from app.database import get_db
from app.models.case import FraudCase, CaseNote
from app.models.fraud_alert import FraudAlert
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.case import CaseCreate, CaseUpdate, NoteCreate
from app.services.audit_service import log_action

router = APIRouter(prefix='/cases', tags=['cases'])

def _note_dict(n):
    return {'id':n.id,'author_id':n.author_id,'note':n.note,'created_at':n.created_at}

# ---- queues -------------------------------------------------------------------------------
# Every case lands in exactly one queue, derived from its decision/status, so analysts work a
# short "needs review" list instead of one mixed list of everything that was ever escalated:
#   needs_review  the engine could not decide; an analyst must                (act on these)
#   auto_blocked  transaction was blocked automatically; confirm or overturn  (act on these)
#   auto_cleared  closed automatically as a false positive                    (audit sample)
#   closed        a human decided it, or it was closed
QUEUES = ('needs_review', 'auto_blocked', 'auto_cleared', 'closed')
ACTIVE_QUEUES = ('needs_review', 'auto_blocked')
PRIORITIES = ('critical', 'high', 'medium', 'low')
_HUMAN = ('confirmed_fraud', 'false_positive')
_CLEARED = ('auto_cleared', 'auto_clear')
_BLOCKED = ('auto_blocked', 'auto_block')   # lower-case spellings; older code stored AUTO_BLOCK / AUTO_CLEAR


def queue_of(decision, status) -> str:
    """Python mirror of `_queue_expr()`; the tests assert the two always agree."""
    d = (decision or '').lower()
    if d in _HUMAN:
        return 'closed'
    if d in _CLEARED:
        return 'auto_cleared'
    if status == 'closed':
        return 'closed'
    if d in _BLOCKED:
        return 'auto_blocked'
    return 'needs_review'


def _queue_expr():
    d = func.lower(func.coalesce(FraudCase.decision, ''))
    return sql_case(
        (d.in_(_HUMAN), 'closed'),
        (d.in_(_CLEARED), 'auto_cleared'),
        (FraudCase.status == 'closed', 'closed'),
        (d.in_(_BLOCKED), 'auto_blocked'),
        else_='needs_review',
    )


def _priority_rank():
    return sql_case(*[(FraudCase.priority == p, i) for i, p in enumerate(PRIORITIES)], else_=len(PRIORITIES))


def _note_dict(n):
    return {'id':n.id,'author_id':n.author_id,'note':n.note,'created_at':n.created_at}

def _context(db, cases):
    """Alert + transaction for each case, in two batched queries (never one per case)."""
    alerts = {a.id: a for a in db.query(FraudAlert).filter(FraudAlert.id.in_({c.alert_id for c in cases})).all()} if cases else {}
    tx_ids = {a.transaction_id for a in alerts.values()}
    txns = {t.id: t for t in db.query(Transaction).filter(Transaction.id.in_(tx_ids)).all()} if tx_ids else {}
    return alerts, txns

_REPORT_MARK = 'AUTOMATED INVESTIGATION REPORT'

def parse_report(text: str) -> dict:
    """Structure the engine's text report so the UI can show it without making the analyst read a wall of text."""
    def section(name):
        m = re.search(rf'^{name}:\n-+\n(.*?)(?:\n\n|\Z)', text, re.S | re.M)
        return [l.strip() for l in m.group(1).splitlines() if l.strip()] if m else []
    conf = re.search(r'Investigation Confidence:\s*(\d+)%', text)
    risk = re.search(r'Risk Level:\s*(\w+)', text)
    when = re.search(r'Investigated At:\s*(\S+)', text)
    signals = []
    for l in section('EVIDENCE SIGNALS'):
        m = re.match(r'[•*-]\s*(.+?):\s*(\d+)%', l)
        if m: signals.append({'name': m.group(1), 'score': int(m.group(2))})
    checks = [re.sub(r'^\[FRAUD\]\s*', '', l) for l in section('AUTOMATED CHECKS') if l.startswith('[FRAUD]')]
    rec = re.search(r'^RECOMMENDED ACTION:\n(.*?)(?:\n\n|\Z)', text, re.S | re.M)
    return {
        'confidence': int(conf.group(1)) if conf else None,
        'risk_level': risk.group(1) if risk else None,
        'investigated_at': when.group(1) if when else None,
        'signals': signals, 'checks': checks,
        'reasoning': ' '.join(section('REASONING')),
        'recommendation': rec.group(1).strip() if rec else None,
    }

def _investigation(notes):
    """Latest automated report among the case notes (None when the case was never auto-investigated)."""
    for n in reversed(notes):
        if _REPORT_MARK in (n.note or ''):
            return parse_report(n.note)
    return None

def _case_dict(db, c, notes=None, ctx=None):
    """`notes` / `ctx` let list views pass data they already fetched in batched queries."""
    if notes is None:
        notes = db.query(CaseNote).filter(CaseNote.case_id == c.id).order_by(CaseNote.created_at.asc()).all()
    alerts, txns = ctx if ctx is not None else _context(db, [c])
    alert = alerts.get(c.alert_id)
    txn = txns.get(alert.transaction_id) if alert else None
    return {'id':c.id,'alert_id':c.alert_id,'assigned_to':c.assigned_to,'status':c.status,'priority':c.priority,'decision':c.decision,'summary':c.summary,'created_at':c.created_at,'updated_at':c.updated_at,'closed_at':c.closed_at,
            'queue':queue_of(c.decision, c.status),
            'severity':alert.severity if alert else None,
            'transaction_id':alert.transaction_id if alert else None,
            'amount':float(txn.amount) if txn is not None else None,
            'currency':txn.currency if txn is not None else None,
            'investigation':_investigation(notes),
            'notes':[_note_dict(n) for n in notes if _REPORT_MARK not in (n.note or '')]}

@router.get('')
def list_cases(status_filter: str|None=None,
               queue: str|None=Query(None, pattern='^(needs_review|auto_blocked|auto_cleared|closed)$'),
               priority: str|None=Query(None, pattern='^(low|medium|high|critical)$'),
               limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
               db:Session=Depends(get_db), current_user:User=Depends(require_role(['admin','analyst']))):
    q=db.query(FraudCase)
    if status_filter: q=q.filter(FraudCase.status==status_filter)
    if queue: q=q.filter(_queue_expr()==queue)
    if priority: q=q.filter(FraudCase.priority==priority)
    if queue in ACTIVE_QUEUES:
        # Work queue: most severe first, then the one that has waited longest.
        order=(_priority_rank().asc(), FraudCase.created_at.asc(), FraudCase.id.asc())
    else:
        order=(FraudCase.updated_at.desc(), FraudCase.id.desc())
    cases=q.order_by(*order).offset(offset).limit(limit).all()
    # One query for every case's notes instead of one per case. This used to be an N+1: 5,000
    # cases meant 5,002 SQL round trips (1.5s even against a local database, many seconds
    # with a hosted Postgres where each round trip costs milliseconds).
    by_case: dict[int, list] = {c.id: [] for c in cases}
    if by_case:
        for n in (db.query(CaseNote).filter(CaseNote.case_id.in_(by_case))
                  .order_by(CaseNote.created_at.asc(), CaseNote.id.asc()).all()):
            by_case[n.case_id].append(n)
    ctx = _context(db, cases)
    return [_case_dict(db, c, by_case[c.id], ctx) for c in cases]

@router.get('/queues')
def queue_counts(db:Session=Depends(get_db), current_user:User=Depends(require_role(['admin','analyst']))):
    """Size of every queue (and its priority mix) in one grouped query, for the tab badges."""
    qx = _queue_expr()
    rows = db.query(qx, FraudCase.priority, func.count(FraudCase.id)).group_by(qx, FraudCase.priority).all()
    out = {name: {'count': 0, 'by_priority': {p: 0 for p in PRIORITIES}} for name in QUEUES}
    for name, prio, n in rows:
        out[name]['count'] += n
        if prio in out[name]['by_priority']:
            out[name]['by_priority'][prio] += n
    return {'queues': out, 'needs_attention': sum(out[n]['count'] for n in ACTIVE_QUEUES)}

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
    if data.get('decision') in ('confirmed_fraud','false_positive'):
        c.status='closed'   # a human decision always closes the case; nobody has to set the status by hand
    if c.assigned_to is None or ('decision' in data and c.assigned_to!=current_user.id):
        c.assigned_to=current_user.id   # whoever acts on a case owns it
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
