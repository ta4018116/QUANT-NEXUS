(() => {
 const $ = id => document.getElementById(id);
 const home = $('dashboardHome');
 if (!home || $('monitoringRoomPanel')) return;
 const card=document.createElement('button');
 card.className='home-card monitoring-home-card';card.dataset.openPage='monitoring';
 card.innerHTML='<span class="card-icon">◉</span><b>غرفة المراقبة المركزية</b><small>تأكيد الدخول · حركة الفرص · متابعة حية</small><strong>دخول غرفة المراقبة ←</strong>';
 home.appendChild(card);
 const col=document.querySelector('.layout>.col');
 const panel=document.createElement('div');panel.className='panel';panel.id='monitoringRoomPanel';
 panel.innerHTML='<div class="head">◉ غرفة المراقبة المركزية <span class="badge">LIVE · PAPER</span></div><div class="body"><div class="monitor-status-grid"><div><small>العملة</small><b id="roomSymbol">—</b></div><div><small>تأكيد الدخول</small><b id="roomState" class="tier-silver">قيد المراقبة</b></div><div><small>قوة الإشارة</small><b id="roomScore">—</b></div><div><small>السعر</small><b id="roomPrice">—</b></div></div><div class="room-marquee"><div id="roomMarqueeTrack">QUANT NEXUS · بانتظار بيانات المراقبة · التداول التجريبي فقط</div></div><div id="roomEntryTicker" class="entry-ticker"><b>شريط تأكيد الدخول</b><div class="muted">اختر عملة من الفرص أو شغّل الماسح</div></div><section class="liquidation-panel"><h3>محرك المشتقات البنفسجي · تصفيات Bybit المباشرة</h3><div class="liquidation-status"><span id="liqConnection" class="liq-off">غير متصل</span><span id="liqSymbol">BTCUSDT</span><span id="liqCount">0 حدث</span></div><div class="liquidation-totals"><div><small>تصفية مراكز LONG</small><b id="liqLong">0 USDT</b></div><div><small>تصفية مراكز SHORT</small><b id="liqShort">0 USDT</b></div><div><small>الإجمالي</small><b id="liqTotal">0 USDT</b></div></div><div id="liqEvents" class="liquidation-events">بانتظار أحداث التصفية من Bybit</div><small class="muted">بث عام لأحداث التصفية المنفذة على عقد USDT الخطي. لا يمثل جميع المراكز المعرضة للتصفية ولا يرسل أوامر تداول.</small></section><h3>حالة المحركات التحليلية</h3><div id="roomEngineReadouts" class="room-engine-readouts">اختر عملة لعرض حالة السوق وبنية السعر وتقييم الفرصة</div><h3>الفرص تحت المراقبة</h3><div id="roomWatchList" class="room-watch-list">لا توجد فرص بعد</div><h3>تصنيف الفرص</h3><div class="room-tier-legend"><span class="tier-gold">ذهبي · تأكيد مكتمل</span><span class="tier-green">أخضر · توافق جيد</span><span class="tier-silver">فضي · قيد المراقبة</span></div><small class="muted">التصنيف توافق فني وليس احتمال ربح مضموناً. الغرفة لا ترسل أوامر حقيقية.</small></div>';
 col.prepend(panel);
 const cfg=window.PAGE_CONFIG;
 if(cfg)cfg.monitoring={title:'غرفة المراقبة المركزية',panels:['monitoringRoomPanel']};
 const oldOpen=window.openPage;
 if(oldOpen){window.openPage=function(key){oldOpen(key);if(key==='monitoring'){window.refreshEntryTicker?.();window.renderMonitoringRoom?.(window.lastItems||[]);const symbol=$('selectedName')?.textContent?.trim();window.refreshEngineReadouts?.(symbol);connectLiquidationStream(symbol)}else if(liquidationSocket){try{liquidationSocket.close(1000,'monitoring room closed')}catch(_){}}}}
 const oldTicker=window.refreshEntryTicker;
 if(oldTicker){window.refreshEntryTicker=async function(){await oldTicker();const state=$('entryTicker')?.innerText||'قيد المراقبة';$('roomEntryTicker').innerHTML=$('entryTicker')?.innerHTML||state;$('roomSymbol').textContent=$('selectedName')?.textContent||'—';$('roomPrice').textContent=$('price')?.textContent||'—';$('roomState').textContent=state.split('\n')[0].slice(0,60)}}
 window.refreshEngineReadouts=async function(symbol){
  const box=$('roomEngineReadouts');if(!box||!symbol)return;
  box.textContent='جارٍ تحديث المحركات…';
  try{
   const results=await Promise.all(['regime','structure','opportunity'].map(async key=>{
    const response=await fetch('/api/'+key+'/'+encodeURIComponent(symbol)+'?category=spot&interval=15m');
    if(!response.ok)throw new Error(key+' unavailable');return [key,await response.json()];
   }));
   const data=Object.fromEntries(results);
   const regime=data.regime,structure=data.structure,op=data.opportunity;
   box.innerHTML='<div><b>حالة السوق:</b> '+(regime.regime||regime.status)+'</div><div><b>بنية السوق:</b> '+(structure.trend||'—')+' · BOS '+(structure.break_of_structure||'—')+' · CHoCH '+(structure.change_of_character||'—')+'</div><div><b>تقييم الفرصة:</b> '+(op.tier||'—')+' · '+(op.score??'—')+'/100 · '+(op.action||'—')+'</div><small>نتائج فنية وصفية وليست احتمالات ربح. PAPER ONLY.</small>';
  }catch(error){box.textContent='تعذر تحميل بيانات المحركات: '+error.message}
 };
 let latestItems=[],lastWatchRender='';const WATCH_KEY='quantNexusManualWatchlist';let watchSymbols=[];try{const saved=JSON.parse(localStorage.getItem(WATCH_KEY)||'[]');if(Array.isArray(saved))watchSymbols=[...new Set(saved.map(x=>String(x).toUpperCase()).filter(x=>/^[A-Z0-9]{2,30}USDT$/.test(x)))];}catch(_){watchSymbols=[]}
 function persistWatchlist(){try{localStorage.setItem(WATCH_KEY,JSON.stringify(watchSymbols))}catch(_){ }}
 function syncOpportunityButtons(){document.querySelectorAll('[data-add-monitor]').forEach(btn=>{const added=watchSymbols.includes(btn.dataset.addMonitor);btn.textContent=added?'✓ مضاف للمراقبة':'＋ إضافة للمراقبة';btn.classList.toggle('is-added',added);btn.setAttribute('aria-pressed',added?'true':'false')})}
 window.isMonitoringSymbol=symbol=>watchSymbols.includes(String(symbol||'').toUpperCase());
 window.addMonitoringSymbol=function(symbol){symbol=String(symbol||'').toUpperCase();if(!/^[A-Z0-9]{2,30}USDT$/.test(symbol))return false;if(!watchSymbols.includes(symbol)){watchSymbols.push(symbol);persistWatchlist();lastWatchRender=''}window.renderMonitoringRoom(latestItems);syncOpportunityButtons();return true};
 window.renderMonitoringRoom=function(items){if(Array.isArray(items)&&(items.length||!latestItems.length))latestItems=items;const bySymbol=new Map(latestItems.map(x=>[String(x.symbol||'').toUpperCase(),x]));const list=watchSymbols.map(symbol=>bySymbol.get(symbol)||{symbol,score:null,direction:'—',manualOnly:true});const signature=JSON.stringify(list.map(x=>[x.symbol,x.score??null,x.direction||'—',!!x.manualOnly]));if(signature!==lastWatchRender){$('roomWatchList').innerHTML=list.map(x=>{const score=Number(x.score||0),tier=score>=85?'gold':score>=70?'green':'silver',label=x.manualOnly?'مضاف يدوياً':tier==='gold'?'ذهبي':tier==='green'?'أخضر':'فضي';return '<div class="room-watch-row"><b>'+x.symbol+'</b><span class="tier-'+tier+'">'+label+'</span><b>'+(x.score==null?'—':score+'/100')+'</b><div class="room-watch-actions"><button class="btn" data-room-symbol="'+x.symbol+'">فتح</button><button class="btn room-remove-btn" data-remove-room-symbol="'+x.symbol+'">إزالة</button></div></div>'}).join('')||'لم تضف فرصاً بعد. استخدم زر «إضافة للمراقبة» في بطاقة الفرصة.';lastWatchRender=signature;}const marquee=list.map(x=>x.symbol+' · '+(x.direction||'—')+' · '+(x.score??'—')+'/100').join(' ◆ ')||'أضف الفرص يدوياً لبدء المراقبة';const track=$('roomMarqueeTrack');if(track.textContent!==marquee)track.textContent=marquee;syncOpportunityButtons()};
 $('roomWatchList').addEventListener('click',e=>{const remove=e.target.closest('[data-remove-room-symbol]');if(remove){watchSymbols=watchSymbols.filter(x=>x!==remove.dataset.removeRoomSymbol);persistWatchlist();lastWatchRender='';window.renderMonitoringRoom(latestItems);return}const b=e.target.closest('[data-room-symbol]');if(b){window.selectCoin?.(b.dataset.roomSymbol);window.refreshEntryTicker?.();window.refreshEngineReadouts?.(b.dataset.roomSymbol);connectLiquidationStream(b.dataset.roomSymbol)}});
 const original=window.render;
 if(original)window.render=function(items){original(items);window.renderMonitoringRoom(items)};
 syncOpportunityButtons();

 let liquidationSocket=null,liquidationSymbol='';let liquidationTotals={long:0,short:0,count:0};
 const fmt=n=>Number(n||0).toLocaleString('en-US',{maximumFractionDigits:2});
 function setLiqStatus(label,online){const el=$('liqConnection');if(el){el.textContent=label;el.className=online?'liq-on':'liq-off'}}
 function connectLiquidationStream(symbol){
  symbol=String(symbol||'BTCUSDT').toUpperCase();if(!/^[A-Z0-9]+USDT$/.test(symbol))symbol='BTCUSDT';
  if(liquidationSocket&&liquidationSymbol===symbol&&[WebSocket.CONNECTING,WebSocket.OPEN].includes(liquidationSocket.readyState))return;
  if(liquidationSocket){try{liquidationSocket.close()}catch(_){}}
  liquidationSymbol=symbol;liquidationTotals={long:0,short:0,count:0};
  $('liqSymbol').textContent=symbol;$('liqCount').textContent='0 حدث';$('liqLong').textContent='0 USDT';$('liqShort').textContent='0 USDT';$('liqTotal').textContent='0 USDT';$('liqEvents').textContent='جارٍ الاتصال ببث Bybit…';setLiqStatus('جارٍ الاتصال',false);
  const protocol=location.protocol==='https:'?'wss:':'ws:';
  const ws=new WebSocket(protocol+'//'+location.host+'/ws/derivatives/'+encodeURIComponent(symbol)+'/liquidations');liquidationSocket=ws;
  ws.onopen=()=>setLiqStatus('متصل · Bybit',true);
  ws.onmessage=event=>{let payload;try{payload=JSON.parse(event.data)}catch(_){return}
   if(payload.type==='status'){setLiqStatus(payload.status==='connected'?'متصل · Bybit':'انقطع الاتصال',payload.status==='connected');return}
   if(payload.type!=='liquidations'||!Array.isArray(payload.events))return;
   const list=$('liqEvents');if(list.textContent.includes('جارٍ الاتصال')||list.textContent.includes('بانتظار أحداث'))list.textContent='';
   payload.events.forEach(item=>{const value=Number(item.notional_usdt)||0;const isLong=item.liquidated_position==='LONG';if(isLong)liquidationTotals.long+=value;else liquidationTotals.short+=value;liquidationTotals.count++;
    const row=document.createElement('div');row.className='liq-event '+(isLong?'liq-long':'liq-short');
    const side=document.createElement('b');side.textContent=isLong?'تصفية LONG':'تصفية SHORT';
    const details=document.createElement('span');details.textContent=fmt(value)+' USDT · '+fmt(item.size)+' '+symbol.replace(/USDT$/,'')+' @ '+fmt(item.bankruptcy_price);
    const time=document.createElement('small');time.textContent=new Date(Number(item.timestamp_ms)||Date.now()).toLocaleTimeString();row.append(side,details,time);list.prepend(row);
   });
   while(list.children.length>30)list.lastElementChild.remove();
   $('liqCount').textContent=liquidationTotals.count+' حدث';$('liqLong').textContent=fmt(liquidationTotals.long)+' USDT';$('liqShort').textContent=fmt(liquidationTotals.short)+' USDT';$('liqTotal').textContent=fmt(liquidationTotals.long+liquidationTotals.short)+' USDT';
  };
  ws.onerror=()=>setLiqStatus('تعذر الاتصال',false);
  ws.onclose=()=>{if(liquidationSocket===ws){setLiqStatus('انقطع الاتصال · إعادة المحاولة',false);setTimeout(()=>{if($('monitoringRoomPanel')?.classList.contains('page-visible')&&liquidationSymbol===symbol)connectLiquidationStream(symbol)},5000)}};
 }

 window.removeMonitoringSymbol = function(symbol) {
  symbol=String(symbol||'').toUpperCase();
  if(!watchSymbols.includes(symbol)) return false;
  watchSymbols=watchSymbols.filter(x=>x!==symbol);
  persistWatchlist();lastWatchRender='';
  window.renderMonitoringRoom(latestItems);
  window.renderOpportunityCards?.(latestItems);
  return true;
 };
})();

/* Rich opportunity cards for the opportunities room. */
(() => {
 const host = document.getElementById('signals');
 const originalCards = window.renderOpportunityCards;
 if (!host || typeof originalCards !== 'function' || window.__qnRichOpportunityCards) return;
 window.__qnRichOpportunityCards = true;
 const esc = value => String(value ?? '—').replace(/[&<>"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));
 const number = value => value == null || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString('en-US',{maximumFractionDigits:6});
 const stateLabel = state => ({CONFIRMED:'تأكيد مكتمل',APPROACH:'اقتراب من الدخول',WAITING:'قيد المراقبة'})[state] || 'قيد المراقبة';
 window.renderOpportunityCards = function(items) {
  originalCards(items);
  const rows = new Map((Array.isArray(items)?items:[]).map(x=>[String(x.symbol||'').toUpperCase(),x]));
  host.querySelectorAll('.opportunity-card[data-opp-symbol]').forEach(card=>{
   const symbol=card.dataset.oppSymbol, x=rows.get(symbol);
   if(!x || card.dataset.richCard==='1') return;
   card.dataset.richCard='1';
   const confirmation=x.entryConfirmation||{};
   const state=confirmation.state||'WAITING';
   const score=Number(x.score)||0;
   const tier=score>=85&&confirmation.confirmed?'gold':score>=70?'green':'silver';
   const tierText=tier==='gold'?'ذهبي · تأكيد مكتمل':tier==='green'?'أخضر · توافق جيد':'فضي · قيد المراقبة';
   const detail=document.createElement('div');
   detail.className='qn-opp-details';
   detail.innerHTML='<div><small>السعر الحالي</small><b>'+number(x.price)+'</b></div>'+
    '<div><small>التغير اليومي</small><b class="'+(Number(x.change24h)>=0?'positive':'negative')+'">'+number(x.change24h)+'%</b></div>'+
    '<div><small>قيمة التداول 24h</small><b>'+number(x.turnover24h)+' USDT</b></div>'+
    '<div><small>نسبة الحجم</small><b>'+(x.volumeRatio==null?'—':number(x.volumeRatio)+'x')+'</b></div>'+
    '<div><small>قوة الإشارة</small><b>'+number(x.score)+'/100</b></div>'+
    '<div><small>التصنيف</small><b class="tier-'+tier+'">'+tierText+'</b></div>'+
    '<div class="qn-opp-confirm"><small>تأكيد الدخول · '+stateLabel(state)+'</small><b>'+esc(confirmation.reason||'بانتظار تأكيد الشمعة المكتملة')+'</b></div>';
   const grid=card.querySelector('.opp-grid');
   if(grid) grid.insertAdjacentElement('afterend',detail); else card.append(detail);
   const actions=card.querySelector('.opp-card-actions');
   if(actions){
    const analyze=document.createElement('button');analyze.type='button';analyze.className='btn qn-opp-analyze';analyze.dataset.oppAction='analyze';analyze.dataset.symbol=symbol;analyze.textContent='تحليل مفصل';
    actions.append(analyze);
    if(window.isMonitoringSymbol?.(symbol)){
     const remove=document.createElement('button');remove.type='button';remove.className='btn qn-opp-remove';remove.dataset.oppAction='remove';remove.dataset.symbol=symbol;remove.textContent='إزالة من المراقبة';actions.append(remove);
    }
   }
  });
 };
 host.addEventListener('click',e=>{
  const button=e.target.closest('[data-opp-action]');
  if(!button)return;
  e.preventDefault();e.stopPropagation();
  const symbol=button.dataset.symbol;
  if(button.dataset.oppAction==='remove'){window.removeMonitoringSymbol?.(symbol);return}
  if(button.dataset.oppAction==='analyze'){window.selectCoin?.(symbol);window.openPage?.('analysis')}
 },true);
 const style=document.createElement('style');
 style.textContent='.qn-opp-details{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin-top:9px}.qn-opp-details>div{min-width:0;padding:8px;background:#061522;border:1px solid #12384a;border-radius:8px;overflow-wrap:anywhere}.qn-opp-details small{display:block;color:var(--muted);font-size:10px;margin-bottom:4px}.qn-opp-details b{font-size:11px}.qn-opp-details .qn-opp-confirm{grid-column:1/-1}.qn-opp-analyze{border-color:#16d9ff;color:#8cecff;padding:8px 12px;font-size:12px}.qn-opp-remove{border-color:#a94c63;color:#ff9aaa;padding:8px 12px;font-size:12px}@media(max-width:600px){.qn-opp-details{grid-template-columns:repeat(2,minmax(0,1fr))}.qn-opp-details .qn-opp-confirm{grid-column:1/-1}}';
 document.head.append(style);
})();
