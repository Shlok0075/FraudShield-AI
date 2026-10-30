from collections import defaultdict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.auth.dependencies import require_role
from app.database import get_db
from app.models.transaction import Transaction
from app.models.device import Device
from app.models.merchant import Merchant

router=APIRouter(prefix='/graph',tags=['graph-risk'])
@router.get('/risk')
def graph_risk(db:Session=Depends(get_db),current_user=Depends(require_role(['admin','analyst']))):
    device_users=defaultdict(set); merchant_users=defaultdict(set); user_devices=defaultdict(set)
    devices={d.id:d for d in db.query(Device).all()}
    for t in db.query(Transaction).all():
        if t.device_id and t.user_id is not None:
            device_users[t.device_id].add(t.user_id); user_devices[t.user_id].add(t.device_id)
        if t.merchant_id and t.user_id is not None: merchant_users[t.merchant_id].add(t.user_id)
    nodes=[]; edges=[]
    for uid,devs in user_devices.items():
        nodes.append({'id':f'user:{uid}','type':'user','risk':min(100,len(devs)*10)})
        for did in devs:
            nodes.append({'id':f'device:{did}','type':'device','risk':min(100,max(0,(len(device_users[did])-1)*25))})
            edges.append({'source':f'user:{uid}','target':f'device:{did}','type':'uses'})
    for mid,users in merchant_users.items():
        nodes.append({'id':f'merchant:{mid}','type':'merchant','risk':min(100,len(users)*2)})
        for uid in list(users)[:50]: edges.append({'source':f'user:{uid}','target':f'merchant:{mid}','type':'shops'})
    # deduplicate nodes
    seen=set(); uniq=[]
    for n in nodes:
        if n['id'] not in seen: seen.add(n['id']); uniq.append(n)
    return {'nodes':uniq,'edges':edges,'shared_devices':sorted([{'device_id':d,'users':len(u)} for d,u in device_users.items() if len(u)>1],key=lambda x:-x['users'])[:20]}
