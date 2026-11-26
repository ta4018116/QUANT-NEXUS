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
 panel.innerHTML='<div class="head">◉ غرفة المراقبة المركزية <span class="badge">LIVE · PAPER</span></div><div class="body"><div class="monitor-status-grid"><div><small>العملة</small><b id="roomSymbol">—</b></div><div><small>تأكيد الدخول</small><b id="roomState" class="tier-silver">قيد المراقبة</b></div><div><small>قوة الإشارة</small><b id="roomScore">—</b></div><div><small>السعر</small><b id="roomPrice">—</b></div></div><div class="room-marquee"><div id="roomMarqueeTrack">QUANT NEXUS · بانتظار بيانات المراقبة · التداول التجريبي فقط</div></div><div id="roomEntryTicker" class="entry-ticker"><b>شريط تأكيد الدخول</b><div class="muted">اختر عملة من الفرص أو شغّل الماسح</div></div><h3>الفرص تحت المراقبة</h3><div id="roomWatchList" class="room-watch-list">لا توجد فرص بعد</div><h3>تصنيف الفرص</h3><div class="room-tier-legend"><span class="tier-gold">ذهبي · تأكيد مكتمل</span><span class="tier-green">أخضر · توافق جيد</span><span class="tier-silver">فضي · قيد المراقبة</span></div><small class="muted">التصنيف توافق فني وليس احتمال ربح مضموناً. الغرفة لا ترسل أوامر حقيقية.</small></div>';
 col.prepend(panel);
 const cfg=window.PAGE_CONFIG;
 if(cfg)cfg.monitoring={title:'غرفة المراقبة المركزية',panels:['monitoringRoomPanel']};
 const oldOpen=window.openPage;
 if(oldOpen){window.openPage=function(key){oldOpen(key);if(key==='monitoring'){window.refreshEntryTicker?.();window.renderMonitoringRoom?.(window.lastItems||[])}}}
 const oldTicker=window.refreshEntryTicker;
 if(oldTicker){window.refreshEntryTicker=async function(){await oldTicker();const state=$('entryTicker')?.innerText||'قيد المراقبة';$('roomEntryTicker').innerHTML=$('entryTicker')?.innerHTML||state;$('roomSymbol').textContent=$('selectedName')?.textContent||'—';$('roomPrice').textContent=$('price')?.textContent||'—';$('roomState').textContent=state.split('\n')[0].slice(0,60)}}
 window.renderMonitoringRoom=function(items){const list=(items||[]).slice(0,15);$('roomWatchList').innerHTML=list.map(x=>{const score=Number(x.score||0),tier=score>=85?'gold':score>=70?'green':'silver',label=tier==='gold'?'ذهبي':tier==='green'?'أخضر':'فضي';return '<div class="room-watch-row"><b>'+x.symbol+'</b><span class="tier-'+tier+'">'+label+'</span><b>'+score+'/100</b><button class="btn" data-room-symbol="'+x.symbol+'">مراقبة</button></div>'}).join('')||'لا توجد فرص مطابقة';$('roomMarqueeTrack').textContent=list.map(x=>x.symbol+' · '+(x.direction||'—')+' · '+(x.score||0)+'/100').join(' ◆ ')||'بانتظار فرص مطابقة'};
 $('roomWatchList').addEventListener('click',e=>{const b=e.target.closest('[data-room-symbol]');if(b){window.selectCoin?.(b.dataset.roomSymbol);window.refreshEntryTicker?.()}});
 const original=window.render;
 if(original)window.render=function(items){original(items);window.renderMonitoringRoom(items)};
 const signals=$('signals');
 if(signals){const observer=new MutationObserver(()=>{signals.querySelectorAll('.opportunity-card').forEach(card=>{if(card.querySelector('.tier-gold,.tier-green,.tier-silver'))return;const score=Number(card.querySelector('.opp-score')?.textContent)||0;const tier=score>=85?'gold':score>=70?'green':'silver';const badge=document.createElement('span');badge.className='tier-'+tier;badge.textContent=tier==='gold'?'ذهبي':tier==='green'?'أخضر':'فضي';card.querySelector('.opp-top')?.appendChild(badge)})});observer.observe(signals,{childList:true,subtree:true})}
})();