import {jobs,warehouses,stocks,transfers} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {TransferStatus,TransferKind} from '../constants/enums.js';
import {esc,date,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
const manage=()=>session.user.role==='admin';
const newKey=()=>window.crypto?.randomUUID?crypto.randomUUID().replaceAll('-',''):'rk-'+Date.now()+'-'+Math.random().toString(16).slice(2);
const chip=s=>'<span class="t-status st-'+esc(s)+'">'+esc(TransferStatus[s]||s)+'</span>';
export async function transferPage(id){
 return id?detailView(id):listView();
}
async function listView(){
 const filter=workspace.transferFilter||'';
 const [ws,allJobs,list]=await Promise.all([warehouses.list(),jobs.list(),transfers.list(filter)]);
 workspace.warehouses=ws;
 const approved=allJobs.filter(j=>j.approved&&j.status==='completed');
 const partParam=(workspace.meta.parameters||[]).find(p=>p.key==='part');
 const partOptions=partParam?partParam.options:[];
 const chips=[['','全部'],['pending','待发'],['in_transit','在途'],['partial','部分收货'],['returning','退运中'],['closed','已结清']];
 const stockRows=ws.map(w=>w.stocks.length?w.stocks.map(s=>'<tr><td>'+esc(w.name)+'</td><td>'+esc(s.part)+'</td><td>'+s.on_hand+'</td><td>'+date(s.updated_at)+'</td></tr>').join(''):'<tr><td>'+esc(w.name)+'</td><td colspan="3">尚未登记现存量</td></tr>').join('');
 const createForm=manage()?'<div class="section-title"><h2>按已批准预测建调拨单</h2></div><form id="transfer-form"><input type="hidden" name="request_id" value="'+newKey()+'"><label>已批准预测<select name="job_id" required>'+approved.map(j=>'<option value="'+j.id+'">'+esc(j.name)+' · '+esc(j.params.part||'')+'</option>').join('')+'</select></label><div class="parameter-grid"><label>出库库<select name="from_warehouse_id">'+ws.map(w=>'<option value="'+w.id+'">'+esc(w.name)+'</option>').join('')+'</select></label><label>收库库<select name="to_warehouse_id">'+ws.map((w,i)=>'<option value="'+w.id+'" '+(i===1?'selected':'')+'>'+esc(w.name)+'</option>').join('')+'</select></label></div><div class="parameter-grid"><label>调拨数量<input type="number" name="quantity" min="1" value="12" required></label><label>备注<input name="note" maxlength="200" placeholder="缺件缘由、借料对话记录"></label></div><div class="parameter-grid"><label>出库库现存量登记<input type="number" name="from_on_hand" min="0" placeholder="留空则不调整"></label><label>收库库现存量登记<input type="number" name="to_on_hand" min="0" placeholder="留空则不调整"></label></div><button type="submit" class="primary" '+(approved.length?'':'disabled')+'>建立调拨单</button><p class="hint">建单同时登记双方库房现存量；备件以预测口径为准。重复提交同一表单不会重复建单。</p></form>':'';
 const stockForm=manage()?'<details class="stock-register"><summary>登记各库现存量（盘点调整）</summary><form id="stock-form"><div class="parameter-grid"><label>库房<select name="warehouse_id">'+ws.map(w=>'<option value="'+w.id+'">'+esc(w.name)+'</option>').join('')+'</select></label><label>备件<select name="part">'+partOptions.map(o=>'<option value="'+esc(o.value)+'">'+esc(o.label)+'</option>').join('')+'</select></label></div><label>现存量<input type="number" name="on_hand" min="0" required></label><button type="submit" class="button small">登记现存量</button></form></details>':'';
 return heading('05 / TRANSFERS','跨库调拨与在途台账','预测缺件后按已批准预测建调拨单：发运扣出库转在途，收货分批只增收库，撤回先转退运、原库确认才恢复可用。','<button class="button" id="refresh-transfers">刷新 ↻</button>')
 +'<div class="transfer-grid"><section class="panel"><div class="section-title"><h2>各库现存量</h2><span>'+ws.length+' 个库房</span></div><div class="table-wrap"><table><thead><tr><th>库房</th><th>备件</th><th>可用量</th><th>登记时间</th></tr></thead><tbody>'+stockRows+'</tbody></table></div>'+stockForm+createForm+'</section>'
 +'<section class="panel"><div class="section-title"><h2>调拨单</h2><span>'+list.length+' 单</span></div><div class="chips">'+chips.map(c=>'<button class="chip'+(filter===c[0]?' on':'')+'" data-filter="'+c[0]+'">'+c[1]+'</button>').join('')+'</div>'
 +(list.length?'<div class="table-wrap"><table><thead><tr><th>单号</th><th>备件</th><th>去向</th><th>计划</th><th>已收</th><th>在途</th><th>退运</th><th>状态</th><th>更新</th></tr></thead><tbody>'+list.map(t=>'<tr class="open-row" data-open="'+t.id+'"><td>#'+t.id+'</td><td>'+esc(t.part)+'</td><td>'+esc(t.from_warehouse_name)+' → '+esc(t.to_warehouse_name)+'</td><td>'+t.quantity+'</td><td>'+t.received_qty+'</td><td>'+t.in_transit_qty+'</td><td>'+t.returning_qty+'</td><td>'+chip(t.status)+'</td><td>'+date(t.updated_at)+'</td></tr>').join('')+'</tbody></table></div>':'<div class="empty">当前筛选下没有调拨单。</div>')
 +'<p class="hint">分析员与观察员只读；办理动作需负责人登录。预测与简报不被调拨改写。</p></section></div>';
}
async function detailView(id){
 const t=await transfers.get(id);
 const con=t.conservation;
 const seg=(v,cls)=>v>0?'<span class="'+cls+'" style="width:'+(v*100/t.quantity).toFixed(2)+'%"></span>':'';
 const flow=t.shipped_qty>0?'<div class="flow-bar">'+seg(t.received_qty,'sg-received')+seg(t.in_transit_qty,'sg-transit')+seg(t.returning_qty,'sg-returning')+seg(t.returned_qty,'sg-returned')+'</div><div class="flow-legend"><span><i class="sg-received"></i>已收 '+t.received_qty+'</span><span><i class="sg-transit"></i>在途 '+t.in_transit_qty+'</span><span><i class="sg-returning"></i>退运在途 '+t.returning_qty+'</span><span><i class="sg-returned"></i>已退回 '+t.returned_qty+'</span></div>':'<p class="hint">尚未发运，发运后在此跟踪在途去向。</p>';
 const numbers=[['计划调拨',t.quantity],['已发运',t.shipped_qty],['已收货',t.received_qty],['在途',t.in_transit_qty],['退运在途',t.returning_qty],['已退回',t.returned_qty]];
 const ops=[];
 if(t.status==='pending')ops.push('<form class="op" id="ship-form"><input type="hidden" name="request_id" value="'+newKey()+'"><h3>发运</h3><p>扣 '+esc(t.from_warehouse_name)+' 可用量 '+t.quantity+'，整单转在途。</p><button class="primary" '+(manage()?'':'disabled')+'>确认发运</button></form>');
 if(t.in_transit_qty>0)ops.push('<form class="op" id="receive-form"><input type="hidden" name="request_id" value="'+newKey()+'"><h3>收货</h3><p>可分批，累计不超发运，只增加 '+esc(t.to_warehouse_name)+' 可用量。</p><label>本次收货<input type="number" name="qty" min="1" max="'+t.in_transit_qty+'" value="'+t.in_transit_qty+'" required></label><button class="primary" '+(manage()?'':'disabled')+'>登记收货</button></form>');
 if(t.in_transit_qty>0)ops.push('<form class="op" id="recall-form"><input type="hidden" name="request_id" value="'+newKey()+'"><h3>撤回未收部分</h3><p>先转退运在途，已收 '+t.received_qty+' 件不退运。</p><label>撤回数量<input type="number" name="qty" min="1" max="'+t.in_transit_qty+'" value="'+t.in_transit_qty+'" required></label><button class="button" '+(manage()?'':'disabled')+'>撤回转退运</button></form>');
 if(t.returning_qty>0)ops.push('<form class="op" id="return-form"><input type="hidden" name="request_id" value="'+newKey()+'"><h3>原库确认退回</h3><p>确认后恢复 '+esc(t.from_warehouse_name)+' 可用量。</p><label>退回数量<input type="number" name="qty" min="1" max="'+t.returning_qty+'" value="'+t.returning_qty+'" required></label><button class="primary" '+(manage()?'':'disabled')+'>确认退回入库</button></form>');
 const opBlock=ops.length?'<div class="op-grid">'+ops.join('')+'</div>':'<p class="hint">该调拨单已'+(t.status==='closed'?'结清':'无当前可办理动作')+'。</p>';
 const snap=(s,k)=>s&&s[k]!=null?esc(s[k]):'—';
 const rows=t.events.map(e=>'<tr><td>'+date(e.at)+'</td><td>'+esc(TransferKind[e.kind]||e.kind)+'</td><td>'+e.qty+'</td><td>'+esc(e.actor)+'</td><td>'+snap(e.snapshot,'from_on_hand')+'</td><td>'+snap(e.snapshot,'to_on_hand')+'</td><td>'+snap(e.snapshot,'in_transit')+'</td><td>'+snap(e.snapshot,'returning')+'</td></tr>').join('');
 return heading('05 / TRANSFERS','调拨单 #'+t.id+' · '+esc(t.part),esc(t.from_warehouse_name)+' → '+esc(t.to_warehouse_name)+' · 依据预测「'+esc(t.job_name)+'」'+(t.note?' · '+esc(t.note):''),'<a class="button" href="#/transfers">← 返回列表</a>')
 +'<div class="result-selector">'+chip(t.status)+'<span>建单 '+date(t.created_at)+'</span><span>更新 '+date(t.updated_at)+'</span><a class="text-button" href="#/results/'+t.job_id+'">查看关联预测 ↗</a></div>'
 +'<section class="panel"><div class="metrics">'+numbers.map(n=>'<div><span>'+n[0]+'</span><strong>'+n[1]+'<small>件</small></strong></div>').join('')+'</div>'+flow
 +'<p class="conserve '+(con.ok?'ok':'bad')+'">'+(con.ok?'✓ 台账守恒：逐笔去向、计数与各库可用量一致':'✗ 台账存在不一致，请核查')+'</p><ul class="conserve-checks">'+con.checks.map(ck=>'<li class="'+(ck.ok?'ok':'bad')+'">'+(ck.ok?'✓':'✗')+' '+esc(ck.label)+'</li>').join('')+'</ul></section>'
 +'<section class="panel"><div class="section-title"><h2>办理</h2><span>'+(manage()?'负责人可操作；重试不会重复增减':'分析员与观察员只读')+'</span></div>'+opBlock+'</section>'
 +'<section class="panel"><div class="section-title"><h2>逐笔去向台账</h2><span>'+t.events.length+' 笔</span></div><div class="table-wrap"><table><thead><tr><th>时间</th><th>操作</th><th>数量</th><th>经办</th><th>出库库可用</th><th>收库库可用</th><th>在途</th><th>退运在途</th></tr></thead><tbody>'+rows+'</tbody></table></div></section>';
}
export function bindTransfers(refresh){
 document.querySelector('#refresh-transfers')?.addEventListener('click',refresh);
 document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{workspace.transferFilter=b.dataset.filter||'';refresh();});
 document.querySelectorAll('[data-open]').forEach(r=>r.onclick=()=>{location.hash='#/transfers/'+r.dataset.open;});
 const createForm=document.querySelector('#transfer-form');
 if(createForm)submit(createForm,async f=>{
  const stocksLine=[];
  if(f.get('from_on_hand')!=='')stocksLine.push({warehouse_id:Number(f.get('from_warehouse_id')),on_hand:Number(f.get('from_on_hand'))});
  if(f.get('to_on_hand')!=='')stocksLine.push({warehouse_id:Number(f.get('to_warehouse_id')),on_hand:Number(f.get('to_on_hand'))});
  const t=await transfers.create({job_id:Number(f.get('job_id')),from_warehouse_id:Number(f.get('from_warehouse_id')),to_warehouse_id:Number(f.get('to_warehouse_id')),quantity:Number(f.get('quantity')),note:f.get('note')||'',request_id:f.get('request_id'),stocks:stocksLine});
  notify(t.replayed?'该表单已提交过，已为你打开原调拨单':'调拨单已建立');location.hash='#/transfers/'+t.id;});
 const stockForm=document.querySelector('#stock-form');
 if(stockForm)submit(stockForm,async f=>{await stocks.register({warehouse_id:Number(f.get('warehouse_id')),part:f.get('part'),on_hand:Number(f.get('on_hand'))});notify('现存量已登记');await refresh();});
 const act=(id,fn,msg)=>{const form=document.querySelector(id);if(form)submit(form,async f=>{const r=await fn(f);notify(r.replayed?'该操作已落账过，未重复增减':msg);await refresh();});};
 const tid=location.hash.split('/')[2];
 act('#ship-form',f=>transfers.ship(tid,f.get('request_id')),'已发运：出库量转在途');
 act('#receive-form',f=>transfers.receive(tid,Number(f.get('qty')),f.get('request_id')),'收货已登记');
 act('#recall-form',f=>transfers.recall(tid,Number(f.get('qty')),f.get('request_id')),'未收部分已转退运');
 act('#return-form',f=>transfers.confirmReturn(tid,Number(f.get('qty')),f.get('request_id')),'退回已确认，原库可用量已恢复');
}
