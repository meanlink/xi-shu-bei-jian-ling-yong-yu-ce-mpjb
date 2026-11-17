import {api} from './client.js';
export const datasets={list:()=>api('/datasets'),get:id=>api('/datasets/'+id),create:data=>api('/datasets',{method:'POST',body:JSON.stringify(data)})};
export const jobs={list:()=>api('/jobs'),get:id=>api('/jobs/'+id),create:data=>api('/jobs',{method:'POST',body:JSON.stringify(data)}),approve:id=>api('/jobs/'+id+'/approve',{method:'POST'})};
export const reports={list:()=>api('/reports'),create:data=>api('/reports',{method:'POST',body:JSON.stringify(data)}),toggle:id=>api('/reports/'+id+'/toggle',{method:'POST'}),deliveries:()=>api('/deliveries')};
export const warehouses={list:()=>api('/warehouses')};
export const stocks={register:data=>api('/stocks',{method:'POST',body:JSON.stringify(data)})};
const post=(path,data)=>api(path,{method:'POST',body:JSON.stringify(data)});
export const transfers={
 list:status=>api('/transfers'+(status?'?status='+status:'')),
 get:id=>api('/transfers/'+id),
 create:data=>post('/transfers',data),
 ship:(id,request_id)=>post('/transfers/'+id+'/ship',{request_id}),
 receive:(id,qty,request_id)=>post('/transfers/'+id+'/receive',{qty,request_id}),
 recall:(id,qty,request_id)=>post('/transfers/'+id+'/recall',{qty,request_id}),
 confirmReturn:(id,qty,request_id)=>post('/transfers/'+id+'/return',{qty,request_id})};
