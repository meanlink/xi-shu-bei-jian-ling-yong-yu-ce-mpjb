from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.config.database import get_db
from src.models import Job, Warehouse, StockBalance, Transfer, TransferEvent
from src.schemas.transfer import StockInput, TransferInput, QtyInput, RequestIdInput
from src.middlewares.auth import current_user, admin_only
from src.services import transfers
from src.services.audit import record
from src.utils.serialization import warehouse_dict, transfer_dict, transfer_event_dict
router=APIRouter()
def _detail(db,t):
    d=transfer_dict(t)
    job=db.get(Job,t.job_id)
    names={w.id:w.name for w in db.scalars(select(Warehouse))}
    d['job_name']=job.name if job else ''
    d['from_warehouse_name']=names.get(t.from_warehouse_id,'')
    d['to_warehouse_name']=names.get(t.to_warehouse_id,'')
    d['events']=[transfer_event_dict(e) for e in db.scalars(select(TransferEvent).where(TransferEvent.transfer_id==t.id).order_by(TransferEvent.id))]
    d['conservation']=transfers.conservation(db,t)
    return d
def _run(db,u,action,fn,*args):
    """执行一次调拨落账：重放与并发冲突都按既有台账返回，不重复增减。"""
    try:
        t,replayed=fn(db,*args)
        if not replayed:
            record(db,u.email,action,{'id':args[0] if args else t.id})
            db.commit()
        return {**_detail(db,t),'replayed':replayed}
    except IntegrityError:
        db.rollback()
        t=transfers.get_transfer(db,args[0])
        return {**_detail(db,t),'replayed':True}
@router.get('/warehouses')
def warehouses(db=Depends(get_db),u=Depends(current_user)):
    out=[]
    for w in db.scalars(select(Warehouse).order_by(Warehouse.id)):
        stocks=list(db.scalars(select(StockBalance).where(StockBalance.warehouse_id==w.id).order_by(StockBalance.part)))
        out.append(warehouse_dict(w,stocks))
    return out
@router.post('/stocks')
def register(data:StockInput,db=Depends(get_db),u=Depends(admin_only)):
    s=transfers.register_stock(db,data.warehouse_id,data.part.strip(),data.on_hand)
    record(db,u.email,'stock.register',{'warehouse_id':data.warehouse_id,'part':data.part,'on_hand':data.on_hand})
    db.commit()
    return {'warehouse_id':s.warehouse_id,'part':s.part,'on_hand':s.on_hand,'updated_at':s.updated_at}
@router.get('/transfers')
def listing(status:str='',db=Depends(get_db),u=Depends(current_user)):
    q=select(Transfer).order_by(Transfer.id.desc())
    if status:
        if status not in ('pending','in_transit','partial','returning','closed'):raise HTTPException(422,'未知的调拨状态')
        q=q.where(Transfer.status==status)
    names={w.id:w.name for w in db.scalars(select(Warehouse))}
    out=[]
    for t in db.scalars(q.limit(200)):
        d=transfer_dict(t)
        d['from_warehouse_name']=names.get(t.from_warehouse_id,'')
        d['to_warehouse_name']=names.get(t.to_warehouse_id,'')
        out.append(d)
    return out
@router.post('/transfers',status_code=201)
def create(data:TransferInput,db=Depends(get_db),u=Depends(admin_only)):
    try:
        t,replayed=transfers.create(db,data,u)
        if not replayed:
            record(db,u.email,'transfer.create',{'id':t.id,'job_id':t.job_id,'qty':t.quantity})
            db.commit()
        return {**_detail(db,t),'replayed':replayed}
    except IntegrityError:
        db.rollback()
        t=db.scalar(select(Transfer).where(Transfer.client_ref==data.request_id))
        if not t:raise HTTPException(409,'调拨单创建冲突，请刷新后重试')
        return {**_detail(db,t),'replayed':True}
@router.get('/transfers/{id}')
def detail(id:int,db=Depends(get_db),u=Depends(current_user)):
    return _detail(db,transfers.get_transfer(db,id))
@router.post('/transfers/{id}/ship')
def ship(id:int,data:RequestIdInput,db=Depends(get_db),u=Depends(admin_only)):
    return _run(db,u,'transfer.ship',transfers.ship,id,data.request_id,u.email)
@router.post('/transfers/{id}/receive')
def receive(id:int,data:QtyInput,db=Depends(get_db),u=Depends(admin_only)):
    return _run(db,u,'transfer.receive',transfers.receive,id,data.qty,data.request_id,u.email)
@router.post('/transfers/{id}/recall')
def recall(id:int,data:QtyInput,db=Depends(get_db),u=Depends(admin_only)):
    return _run(db,u,'transfer.recall',transfers.recall,id,data.qty,data.request_id,u.email)
@router.post('/transfers/{id}/return')
def confirm_return(id:int,data:QtyInput,db=Depends(get_db),u=Depends(admin_only)):
    return _run(db,u,'transfer.return',transfers.confirm_return,id,data.qty,data.request_id,u.email)
