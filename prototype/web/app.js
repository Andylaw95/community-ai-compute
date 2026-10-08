"use strict";
const $ = id => document.getElementById(id);
const fmt = new Intl.NumberFormat("zh-HK");
const esc = value => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const names = {queued:"等待分配",running:"進行中",completed:"已完成",failed:"失敗",working:"計算中",ready:"就緒",paused:"已暫停",stopped:"已停止"};
let state, first = true, toastTimer;
async function api(path, data, extra={}) {
  const response = await fetch(path, data===undefined ? {cache:"no-store"} : {method:"POST",headers:{"Content-Type":"application/json",...extra},body:JSON.stringify(data)});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || `HTTP ${response.status}`);
  return value;
}
function notice(message, error=false) {
  $("notice").textContent=message; $("notice").classList.toggle("error",error); $("notice").hidden=false;
  clearTimeout(toastTimer); toastTimer=setTimeout(()=>$("notice").hidden=true,5000);
}
function put(id, html) { if ($(id).innerHTML!==html) $(id).innerHTML=html; }
function badge(s) {return `<span class="state ${esc(s)}">${esc(names[s]||s)}</span>`;}
function render(s) {
  state=s;
  $("metric-chunks").textContent=fmt.format(s.totals.accepted);
  $("metric-nodes").textContent=s.nodes.filter(n=>n.alive).length;
  $("metric-credits").textContent=fmt.format(s.totals.credits);
  $("metric-verify").textContent=(s.totals.verify_ms/1000).toFixed(2);
  $("job-counter").textContent=`${s.jobs.length} 份工作`;
  $("effective").textContent=`${s.policy.effective_budget}%`;
  $("policy-status").textContent=!s.policy.consent?"等待同意，尚未貢獻":s.policy.paused?"已暫停，不接新工作":s.policy.effective_budget===0?"前景忙碌或負載限制，已退避":"目前每程序排程預算";
  $("pause").textContent=s.policy.paused?"恢復貢獻":"暫停貢獻";
  $("hardware").textContent=`${s.hardware.system} ${s.hardware.machine} · ${s.hardware.logical_cpus} 邏輯 CPU · 1 分鐘平均負載 ${s.policy.load_1m?.toFixed(2)??"不可讀取"}`;
  if(first){$("consent").checked=s.policy.consent;$("budget").value=s.policy.budget;$("budget-output").value=`${s.policy.budget}%`;$("usage").value=s.policy.usage;$("foreground").checked=s.policy.foreground_busy;document.querySelector(`[name=mode][value=${s.policy.mode}]`).checked=true;first=false;}
  const j=s.jobs[0];
  const stages=j?[["等待分配",j.phases.queued],["分配進行中",j.phases.leased],["驗證並接受",`${j.phases.accepted} / ${j.chunks.length}`],["交付成果",j.status==="completed"?"可下載":j.status==="failed"?"需處理":"等待驗證"]]:[["等待分配",0],["分配進行中",0],["驗證並接受",0],["交付成果","—"]];
  put("phases",stages.map(([name,value],i)=>`<div class="${j&&(i<3||j.status==="completed")?"active":""}"><span>${i+1}</span>${name}<strong>${esc(value)}</strong></div>`).join(""));
  put("jobs",s.jobs.length?s.jobs.map(j=>`<tr><td>${esc(j.title)}<small>${esc(j.id)}</small></td><td>${j.phases.accepted} / ${j.chunks.length}</td><td>${badge(j.status)}</td><td>${j.status==="completed"?`<a href="/api/jobs/${encodeURIComponent(j.id)}/results" target="_blank" rel="noopener">取回 JSON</a>`:"—"}</td></tr>`).join(""):'<tr><td colspan="4" class="empty">提交第一個批次，觀察分片如何完成。</td></tr>');
  put("nodes",s.nodes.map(n=>`<tr><td>${esc(n.id)}<small>PID ${n.pid??"—"}${n.fault?` · 下次：${esc(n.fault)}`:""}</small></td><td>${badge(n.status)}</td><td>${n.accepted}</td><td><button data-node="${esc(n.id)}" data-action="${n.alive?"stop":"start"}">${n.alive?"停止程序":"啟動程序"}</button></td></tr>`).join(""));
  put("ledger",s.ledger.length?s.ledger.map(l=>`<tr><td>#${l.id}<small>${esc(l.chunk_id)}</small></td><td>${esc(l.node)}</td><td>+${l.credits}</td></tr>`).join(""):'<tr><td colspan="3" class="empty">尚未有驗證完成的工作。</td></tr>');
  $("events").textContent=s.events.map(e=>`${new Date(e.created*1000).toLocaleTimeString("zh-HK",{hour12:false})}  ${e.kind.padEnd(10)}  ${e.detail}`).join("\n")||"尚未有事件。";
  $("connection").textContent="已連接本機協調器 · 每秒更新";
}
async function refresh(){try{render(await api("/api/state"));}catch(e){$("connection").textContent="協調器未連接；請檢查終端機。";}}
$("budget").addEventListener("input",()=>$("budget-output").value=`${$("budget").value}%`);
$("job-form").addEventListener("submit",async event=>{event.preventDefault();$("submit").disabled=true;try{const result=await api("/api/jobs",{count:Number($("count").value),batch:Number($("batch").value),seed:7,title:"合成影像亮度統計"},{"Idempotency-Key":crypto.randomUUID()});notice(`工作已提交：${result.job_id}`);await refresh();}catch(e){notice(e.message,true);}finally{$("submit").disabled=false;}});
$("policy-form").addEventListener("submit",async event=>{event.preventDefault();try{await api("/api/policy",{consent:$("consent").checked,budget:Number($("budget").value),mode:document.querySelector("[name=mode]:checked").value,usage:$("usage").value,foreground_busy:$("foreground").checked});notice("設定已套用；新設定會在短工作段之間生效。");await refresh();}catch(e){notice(e.message,true);}});
$("pause").addEventListener("click",async()=>{if(!state)return;try{await api("/api/policy",{paused:!state.policy.paused});await refresh();notice(state.policy.paused?"已暫停貢獻":"已恢復貢獻");}catch(e){notice(e.message,true);}});
$("nodes").addEventListener("click",async event=>{const b=event.target.closest("[data-node]");if(!b)return;b.disabled=true;try{await api(`/api/nodes/${b.dataset.node}/${b.dataset.action}`,{});await refresh();notice(b.dataset.action==="stop"?"程序已停止；未完成的租約會逾期重派。":"本機程序已啟動。");}catch(e){notice(e.message,true);}});
document.querySelectorAll("[data-fault]").forEach(b=>b.addEventListener("click",async()=>{try{await api("/api/demo/fault",{node:$("fault-node").value,mode:b.dataset.fault});notice("已設定下一個租約的一次故障試驗。");await refresh();}catch(e){notice(e.message,true);}}));
document.querySelectorAll("[data-tab]").forEach(b=>b.addEventListener("click",()=>{document.querySelectorAll(".page").forEach(p=>p.hidden=p.id!==b.dataset.tab);document.querySelectorAll("[data-tab]").forEach(t=>{t.classList.toggle("selected",t===b);if(t===b)t.setAttribute("aria-current","page");else t.removeAttribute("aria-current");});}));
$("api-example").textContent=`curl ${location.origin}/api/jobs \\\n+  -H 'Content-Type: application/json' \\\n+  -H 'Idempotency-Key: first-batch-001' \\\n+  -d '{"count":96,"batch":32,"seed":7}'\n\n# 用回傳的 job_id 查詢\ncurl ${location.origin}/api/jobs/{job_id}\ncurl ${location.origin}/api/jobs/{job_id}/results`;
refresh();setInterval(refresh,1000);
