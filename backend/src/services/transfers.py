"""跨库调拨台账：发运扣出库转在途、分批收货只增收库、撤回先转退运、原库确认才恢复可用。

并发裁决：所有计数与库存变更用原子条件 UPDATE（WHERE 余量足够），先落账者生效，
后到者因条件不满足被 409 拒绝；已收部分不计入可撤回量，不会退运。
幂等：每个操作携带 request_id，命中既有台账事件即按重放返回，不重复增减；
唯一约束 (transfer_id, request_id) 兜底并发重试，建单以 client_ref 唯一约束去重。
守恒：每次落账的库存与计数变更在同一事务提交，中断回滚不产生半状态；
conservation() 重放逐笔事件校验各库可用量与在途量始终守恒。
"""
import time
from fastapi import HTTPException
from sqlalchemy import select, update
from src.models import Job, Warehouse, StockBalance, Transfer, TransferEvent

ACTIVE = ('in_transit', 'partial', 'returning')  # 仍有在途量可办理的状态

def status_of(t):
    """由计数推导状态：待发/在途/部分收货/退运/结清。"""
    if t.shipped_qty <= 0:
        return 'pending'
    if t.received_qty + t.returned_qty >= t.shipped_qty and t.returned_qty >= t.recalled_qty:
        return 'closed'
    if t.recalled_qty > t.returned_qty:
        return 'returning'
    if t.received_qty > 0:
        return 'partial'
    return 'in_transit'

def get_transfer(db, transfer_id):
    t = db.get(Transfer, transfer_id)
    if not t:
        raise HTTPException(404, '调拨单不存在')
    return t

def _stock(db, warehouse_id, part, create=False):
    s = db.scalar(select(StockBalance).where(StockBalance.warehouse_id == warehouse_id, StockBalance.part == part).with_for_update())
    if not s:
        if not create:
            raise HTTPException(409, '该库尚无此备件存量登记，请先登记现存量')
        s = StockBalance(warehouse_id=warehouse_id, part=part, on_hand=0, updated_at=time.time())
        db.add(s)
        db.flush()
    return s

def register_stock(db, warehouse_id, part, on_hand):
    """登记（盘点设定）某库某备件现存量。"""
    if not db.get(Warehouse, warehouse_id):
        raise HTTPException(404, '库房不存在')
    s = _stock(db, warehouse_id, part, create=True)
    s.on_hand = on_hand
    s.updated_at = time.time()
    db.flush()
    return s

def _replayed(db, transfer_id, request_id):
    return db.scalar(select(TransferEvent).where(TransferEvent.transfer_id == transfer_id, TransferEvent.request_id == request_id))

def _snapshot(db, t):
    f = db.scalar(select(StockBalance).where(StockBalance.warehouse_id == t.from_warehouse_id, StockBalance.part == t.part).execution_options(populate_existing=True))
    o = db.scalar(select(StockBalance).where(StockBalance.warehouse_id == t.to_warehouse_id, StockBalance.part == t.part).execution_options(populate_existing=True))
    return {
        'from_on_hand': f.on_hand if f else None,
        'to_on_hand': o.on_hand if o else None,
        'in_transit': t.shipped_qty - t.received_qty - t.recalled_qty,
        'returning': t.recalled_qty - t.returned_qty,
        'shipped': t.shipped_qty, 'received': t.received_qty,
        'recalled': t.recalled_qty, 'returned': t.returned_qty,
    }

def _record_event(db, t, kind, qty, request_id, actor):
    db.add(TransferEvent(transfer_id=t.id, kind=kind, qty=qty, request_id=request_id,
                         actor=actor, at=time.time(), snapshot=_snapshot(db, t)))
    db.flush()

def _bump_stock(db, stock_id, delta, floor=None):
    """原子增减库存；floor 为允许的下限，不足时拒绝（先落账者已占用）。"""
    conditions = [StockBalance.id == stock_id]
    if floor is not None:
        conditions.append(StockBalance.on_hand + delta >= floor)
    res = db.execute(update(StockBalance).where(*conditions)
                     .values(on_hand=StockBalance.on_hand + delta, updated_at=time.time())
                     .execution_options(synchronize_session=False))
    if res.rowcount != 1:
        raise HTTPException(409, '库房可用量不足，他人可能已先行落账；请刷新后重试')

def _bump_counter(db, t, **deltas):
    """原子条件计数更新：仅当更新后仍满足守恒不变量才落账。

    不变量：received + recalled <= shipped（已收与撤回合计不超发运，已收部分不退运），
    returned <= recalled（退回不超撤回）。并发下先提交者占用在途量，
    后到者 rowcount=0 被拒，实现先落账者裁决。
    """
    received = deltas.get('received_qty', 0)
    recalled = deltas.get('recalled_qty', 0)
    returned = deltas.get('returned_qty', 0)
    conditions = [Transfer.id == t.id]
    if received or recalled:
        conditions.append(Transfer.received_qty + Transfer.recalled_qty + received + recalled <= Transfer.shipped_qty)
    if returned:
        conditions.append(Transfer.returned_qty + returned <= Transfer.recalled_qty)
    values = {k: getattr(Transfer, k) + v for k, v in deltas.items() if v}
    values['updated_at'] = time.time()
    res = db.execute(update(Transfer).where(*conditions).values(**values).execution_options(synchronize_session=False))
    if res.rowcount != 1:
        raise HTTPException(409, '在途数量不足或状态已变化，他人可能已先行落账；请刷新后重试')
    db.expire(t)

def _set_status(db, t):
    db.refresh(t)
    t.status = status_of(t)
    db.flush()

def create(db, data, user):
    """按已批准预测建调拨单，并登记双方库房现存量。预测只读引用，不回写。"""
    existing = db.scalar(select(Transfer).where(Transfer.client_ref == data.request_id))
    if existing:
        return existing, True
    job = db.get(Job, data.job_id)
    if not job or job.status != 'completed' or not job.approved:
        raise HTTPException(409, '调拨单必须基于已完成且获批准的预测')
    part = str(job.params.get('part', ''))
    if not part:
        raise HTTPException(409, '该预测未指定备件，无法建立调拨单')
    if data.from_warehouse_id == data.to_warehouse_id:
        raise HTTPException(422, '出库库与收库库不能相同')
    for wid in (data.from_warehouse_id, data.to_warehouse_id):
        if not db.get(Warehouse, wid):
            raise HTTPException(404, '库房不存在')
    for line in data.stocks:
        if line.warehouse_id not in (data.from_warehouse_id, data.to_warehouse_id):
            raise HTTPException(422, '只能登记调拨双方库房的现存量')
        register_stock(db, line.warehouse_id, part, line.on_hand)
    now = time.time()
    t = Transfer(client_ref=data.request_id, job_id=job.id, part=part,
                 from_warehouse_id=data.from_warehouse_id, to_warehouse_id=data.to_warehouse_id,
                 quantity=data.quantity, status='pending', note=data.note,
                 created_by=user.id, created_at=now, updated_at=now)
    db.add(t)
    db.flush()
    _record_event(db, t, 'create', t.quantity, data.request_id, user.email)
    return t, False

def ship(db, transfer_id, request_id, actor):
    """发运：扣出库库可用量，整单转在途。重试同 request_id 不重复扣减。"""
    t = get_transfer(db, transfer_id)
    if _replayed(db, transfer_id, request_id):
        return t, True
    if t.status != 'pending':
        raise HTTPException(409, '仅待发调拨单可以发运')
    s = _stock(db, t.from_warehouse_id, t.part)
    res = db.execute(update(Transfer).where(Transfer.id == t.id, Transfer.shipped_qty == 0)
                     .values(shipped_qty=t.quantity, updated_at=time.time())
                     .execution_options(synchronize_session=False))
    if res.rowcount != 1:
        raise HTTPException(409, '该调拨单已发运，请勿重复操作')
    db.expire(t)
    _bump_stock(db, s.id, -t.quantity, floor=0)
    _set_status(db, t)
    _record_event(db, t, 'ship', t.quantity, request_id, actor)
    return t, False

def receive(db, transfer_id, qty, request_id, actor):
    """收货：可分批，累计不超发运，只增加收库可用量。"""
    t = get_transfer(db, transfer_id)
    if _replayed(db, transfer_id, request_id):
        return t, True
    if t.status not in ACTIVE:
        raise HTTPException(409, '当前状态不可收货')
    _bump_counter(db, t, received_qty=qty)
    s = _stock(db, t.to_warehouse_id, t.part, create=True)
    _bump_stock(db, s.id, qty)
    _set_status(db, t)
    _record_event(db, t, 'receive', qty, request_id, actor)
    return t, False

def recall(db, transfer_id, qty, request_id, actor):
    """撤回未收部分：先转退运在途，不动任何库房可用量；已收部分不可撤回。"""
    t = get_transfer(db, transfer_id)
    if _replayed(db, transfer_id, request_id):
        return t, True
    if t.status not in ACTIVE:
        raise HTTPException(409, '当前状态不可撤回')
    _bump_counter(db, t, recalled_qty=qty)
    _set_status(db, t)
    _record_event(db, t, 'recall', qty, request_id, actor)
    return t, False

def confirm_return(db, transfer_id, qty, request_id, actor):
    """原库确认退回：退运在途转回原库可用量。"""
    t = get_transfer(db, transfer_id)
    if _replayed(db, transfer_id, request_id):
        return t, True
    if t.status != 'returning':
        raise HTTPException(409, '当前没有退运在途的备件')
    _bump_counter(db, t, returned_qty=qty)
    s = _stock(db, t.from_warehouse_id, t.part, create=True)
    _bump_stock(db, s.id, qty)
    _set_status(db, t)
    _record_event(db, t, 'return', qty, request_id, actor)
    return t, False

def conservation(db, t):
    """重放逐笔台账，校验计数、状态与各库可用量/在途量守恒。"""
    events = list(db.scalars(select(TransferEvent).where(TransferEvent.transfer_id == t.id).order_by(TransferEvent.id)))
    sums = {'ship': 0, 'receive': 0, 'recall': 0, 'return': 0}
    for e in events:
        if e.kind in sums:
            sums[e.kind] += e.qty
    in_transit = t.shipped_qty - t.received_qty - t.recalled_qty
    returning = t.recalled_qty - t.returned_qty
    checks = [
        ('计数与逐笔台账一致', sums['ship'] == t.shipped_qty and sums['receive'] == t.received_qty
         and sums['recall'] == t.recalled_qty and sums['return'] == t.returned_qty),
        ('收货与撤回合计不超发运', t.received_qty + t.recalled_qty <= t.shipped_qty),
        ('退回不超撤回', t.returned_qty <= t.recalled_qty),
        ('在途与退运量非负', in_transit >= 0 and returning >= 0),
        ('状态与台账推导一致', t.status == status_of(t)),
    ]
    return {'ok': all(ok for _, ok in checks),
            'checks': [{'label': label, 'ok': ok} for label, ok in checks],
            'in_transit': in_transit, 'returning': returning}
