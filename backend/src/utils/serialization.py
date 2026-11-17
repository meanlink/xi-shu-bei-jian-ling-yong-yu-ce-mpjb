import hashlib, json
def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
def dataset_dict(d):
    return {'id':d.id, 'name':d.name, 'source':d.source, 'rows':len(d.records), 'checksum':d.checksum, 'created_at':d.created_at}
def job_dict(j):
    return {k:getattr(j,k) for k in ['id','name','dataset_id','params','status','result','error','approved','created_at','finished_at']}
def report_dict(r):
    return {k:getattr(r,k) for k in ['id','name','job_id','destination','interval_seconds','next_run','enabled']}
def delivery_dict(d):
    return {k:getattr(d,k) for k in ['id','report_id','created_at','checksum','filename','destination']}
def warehouse_dict(w, stocks):
    return {'id':w.id,'code':w.code,'name':w.name,'stocks':[{'part':s.part,'on_hand':s.on_hand,'updated_at':s.updated_at} for s in stocks]}
def transfer_dict(t):
    d={k:getattr(t,k) for k in ['id','job_id','part','from_warehouse_id','to_warehouse_id','quantity','shipped_qty','received_qty','recalled_qty','returned_qty','status','note','created_at','updated_at']}
    d['in_transit_qty']=t.shipped_qty-t.received_qty-t.recalled_qty
    d['returning_qty']=t.recalled_qty-t.returned_qty
    return d
def transfer_event_dict(e):
    return {k:getattr(e,k) for k in ['id','kind','qty','actor','at','snapshot']}
