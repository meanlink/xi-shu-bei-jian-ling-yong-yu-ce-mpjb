import time, json
from sqlalchemy import select, func
from src.config.database import Session
from migrations.initial import migrate
from src.models import User, Dataset, Job, Report, Delivery, Audit, Warehouse, StockBalance, Transfer, TransferEvent
from src.services.business import metadata, seed_records, analyze
from src.services.reports import deliver
from src.utils.security import hash_password
from src.utils.serialization import checksum
def seed():
    migrate()
    with Session() as db:
        for role,name in [('admin','林知 · 业务负责人'),('analyst','陈舟 · 分析员'),('viewer','周禾 · 观察员')]:
            email=role+'@demo.local'
            if not db.scalar(select(User).where(User.email==email)):
                db.add(User(email=email,name=name,role=role,password=hash_password('Demo123!')))
        db.flush()
        m=metadata()
        d=db.scalar(select(Dataset).where(Dataset.name==m['dataset_name']))
        if not d:
            rows=seed_records()
            d=Dataset(name=m['dataset_name'],source=m['short']+'-202611.csv',records=rows,checksum=checksum(rows),created_at=time.time())
            db.add(d); db.flush()
        if not db.scalar(select(Job).where(Job.name=='基线复核 · '+m['name'])):
            params={p['key']:p['default'] for p in m.get('parameters',[])}
            result=analyze(d.records,params)
            json.dumps(result,ensure_ascii=False,allow_nan=False)
            admin=db.scalar(select(User).where(User.role=='admin'))
            j=Job(name='基线复核 · '+m['name'],dataset_id=d.id,params=params,status='completed',result=result,created_by=admin.id,created_at=time.time()-3600,finished_at=time.time()-3595,approved=True)
            db.add(j);db.flush()
            r=Report(name='每日业务复核简报',job_id=j.id,destination='业务复核组 · 本地收件箱',interval_seconds=86400,next_run=time.time()+86400,enabled=True)
            db.add(r);db.flush();deliver(db,r)
            db.add(Audit(actor='seed',action='demo.baseline',detail={'dataset':d.id},at=time.time()))
        warehouses={}
        for code,name in [('JW-CEN','江湾中心库'),('JW-EAST','东场维保站'),('JW-WEST','西场维保站')]:
            w=db.scalar(select(Warehouse).where(Warehouse.code==code))
            if not w:
                w=Warehouse(code=code,name=name); db.add(w); db.flush()
            warehouses[code]=w
        for code,part,on_hand in [('JW-CEN','R17',40),('JW-CEN','G22',25),('JW-EAST','R17',6),('JW-EAST','G22',4),('JW-WEST','R17',3),('JW-WEST','G22',9)]:
            w=warehouses[code]
            if not db.scalar(select(StockBalance).where(StockBalance.warehouse_id==w.id,StockBalance.part==part)):
                db.add(StockBalance(warehouse_id=w.id,part=part,on_hand=on_hand,updated_at=time.time()))
        db.flush()
        job=db.scalar(select(Job).where(Job.name=='基线复核 · '+m['name']))
        if job and not db.scalar(select(Transfer).where(Transfer.client_ref=='seed-transfer-1')):
            admin=db.scalar(select(User).where(User.role=='admin'))
            now=time.time()
            t=Transfer(client_ref='seed-transfer-1',job_id=job.id,part='R17',from_warehouse_id=warehouses['JW-CEN'].id,to_warehouse_id=warehouses['JW-EAST'].id,quantity=12,status='pending',note='预测 R17 两周缺口，中心库向东场维保站调拨补位',created_by=admin.id,created_at=now,updated_at=now)
            db.add(t); db.flush()
            db.add(TransferEvent(transfer_id=t.id,kind='create',qty=12,request_id='seed-transfer-1',actor='seed',at=now,snapshot={'from_on_hand':40,'to_on_hand':6,'in_transit':0,'returning':0,'shipped':0,'received':0,'recalled':0,'returned':0}))
            db.add(Audit(actor='seed',action='transfer.create',detail={'id':t.id},at=now))
        db.commit()
        counts={model.__tablename__:db.scalar(select(func.count()).select_from(model)) for model in [User,Dataset,Job,Report,Delivery,Audit,Warehouse,StockBalance,Transfer,TransferEvent]}
        print(json.dumps(counts,ensure_ascii=False))
        return counts
if __name__=='__main__':seed()
