// Account quota only: never substitute host token totals or context occupancy.
const labels={codex:'Codex',claude:'Claude Code',cursor:'Cursor',opencode:'OpenCode',antigravity:'Google Antigravity'};
export function linkedAccount(value){
 return !!value?.account&&value.installed!==false&&!value.login_required&&(!value.error||value.usage_stale)&&value.account.type===(value.backend==='codex'?'chatgpt':value.backend);
}
function windowsFor(quota){
 const windows=(quota?.windows||[]).filter(w=>Number.isFinite(w.remaining_percent)&&w.remaining_percent>=0&&w.remaining_percent<=100);
 const first=windows.find(w=>w.label==='codex · primary')||windows.find(w=>w.label==='five hour')||windows[0];
 if(quota?.grouped)return [first,windows.find(w=>w.group!==first?.group)];
 const group=first?.label?.split(' · ')[0];
 const second=windows.find(w=>w!==first&&(w.label===`${group} · secondary`||w.label==='seven day'))||windows.find(w=>w!==first&&w.label?.split(' · ')[0]===group&&w.window_minutes!==first?.window_minutes);
 return [first,second];
}
function duration(window){
 const mins=window?.window_minutes;
 const period=mins?mins%1440===0?`${mins/1440}d`:mins%60===0?`${mins/60}h`:`${mins}m`:window?.label||'Quota window';
 return window?.group?`${window.group} · ${period}`:period;
}
export function paintSidebarQuota(root,records,{refresh,openSettings,loading=false}={}){
 if(!root)return;
 const accounts=Object.keys(labels).map(id=>[id,records.get(id)?.value]).filter(([,value])=>linkedAccount(value));
 root.hidden=!accounts.length;if(!accounts.length){root.replaceChildren();return;}
 const focused=document.activeElement?.dataset.quotaProvider,refreshFocused=document.activeElement?.dataset.quotaRefresh!==undefined;
 root.replaceChildren();
 const heading=document.createElement('div');heading.className='sidebar-quota-heading';
 const title=document.createElement('span');title.textContent='Remaining quota';
 const reload=document.createElement('button');reload.type='button';reload.className='sidebar-quota-refresh';reload.dataset.quotaRefresh='';reload.textContent='↻';reload.ariaLabel='Refresh remaining quota';reload.title=reload.ariaLabel;reload.disabled=loading;reload.onclick=()=>refresh?.();heading.append(title,reload);root.append(heading);
 for(const [id,value] of accounts){
  const quota=value.usage?.quota,windows=windowsFor(quota),now=Date.now()/1000;
  const stale=!!value.usage_stale||!!quota?.stale||(quota?.observed_at&&now-quota.observed_at>120);
  const row=document.createElement('button');row.type='button';row.className='sidebar-quota-row';row.dataset.quotaProvider=id;row.dataset.stale=String(!!stale);row.onclick=()=>openSettings?.();
  const name=document.createElement('span');name.className='sidebar-quota-name';name.textContent=labels[id];
  const values=document.createElement('span');values.className='sidebar-quota-percentages';
  const track=document.createElement('span');track.className='sidebar-quota-track';track.ariaHidden='true';
  const details=[];let available=false;
  windows.forEach((window,index)=>{
   const expired=!!window?.resets_at&&window.resets_at<=now,known=!!window&&!expired;
   available||=known;
   const percentage=document.createElement('span');percentage.className=`sidebar-quota-value quota-level-${index}`;percentage.textContent=known?`${Math.round(window.remaining_percent)}%`:'—';
   if(index){const divider=document.createElement('span');divider.className='sidebar-quota-divider';divider.textContent=' / ';values.append(divider);}values.append(percentage);
   const fill=document.createElement('span');fill.className=`sidebar-quota-fill quota-level-${index}`;fill.style.width=(known?window.remaining_percent:0)+'%';track.append(fill);
   if(window)details.push(`${duration(window)}: ${known?Math.round(window.remaining_percent)+'% remaining':expired?'reset; refresh needed':'unavailable'}${window.resets_at?' · resets '+new Date(window.resets_at*1000).toLocaleString():''}`);
  });
  if(!available){values.textContent='Unavailable';row.dataset.unavailable='true';}
  const note=stale?'Stale observation. ':'';
  row.title=`${labels[id]} · ${note}${details.join('\n')||quota?.note||'Quota unavailable'}${quota?.source?'\n'+quota.source:''}${quota?.observed_at?' · '+new Date(quota.observed_at*1000).toLocaleString():''}\nOpen usage details in Settings`;
  if(quota?.grouped&&quota.note)row.title+='\n'+quota.note;
  row.ariaLabel=`${labels[id]} remaining quota. ${note}${details.join('. ')||'Unavailable'}. Open usage details.`;
  row.append(name,values,track);root.append(row);
 }
 if(focused)root.querySelector(`[data-quota-provider="${focused}"]`)?.focus({preventScroll:true});
 else if(refreshFocused)reload.focus({preventScroll:true});
}
