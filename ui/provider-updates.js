export function createProviderUpdates({api,action,readOnly,onUpdated,onError}){
 let root,timer,previousCheck=null,pending=false;
 const labels={codex:'Codex',claude:'Claude Code',cursor:'Cursor',opencode:'OpenCode',antigravity:'Google Antigravity'};
 function paint(data){
  if(!root?.isConnected)return;
  root.replaceChildren();
  const heading=document.createElement('h3');heading.textContent='Provider runtime updates';
  const label=document.createElement('label'),enabled=document.createElement('input');enabled.type='checkbox';enabled.checked=!!data.enabled;enabled.disabled=readOnly()||pending;enabled.dataset.providerAutoUpdates='';
  label.append(enabled,' Automatically update installed provider runtimes when idle');
  const note=document.createElement('p');note.className='small muted';note.textContent='Checks every six hours while this workspace service is running. Active provider turns defer updates. Missing tools are not installed; pinned paths stay managed by their owner. New models still depend on your account and plan. Google may need Reconnect after an update.';
  const button=document.createElement('button');button.type='button';button.className='button small-button';button.textContent=data.working?'Checking updates…':'Check & update now';button.disabled=readOnly()||pending||data.working;
  const status=document.createElement('div');status.setAttribute('role','status');status.dataset.providerUpdateStatus='';
  for(const [id,row] of Object.entries(data.providers||{})){const line=document.createElement('p');line.className='small';line.textContent=`${labels[id]||id}: ${row.version?row.version+' · ':''}${row.status} · ${row.note||''}`;status.append(line);}
  const next=document.createElement('small');next.textContent=data.enabled&&data.next_check?'Next check: '+new Date(data.next_check*1000).toLocaleString():'Automatic updates are off.';
  enabled.onchange=()=>perform('provider.updates.configure',{enabled:enabled.checked});button.onclick=()=>perform('provider.updates.check',{});
  root.append(heading,label,note,button,status,next);
 }
 async function refresh(){clearTimeout(timer);try{const value=await api('provider-updates');paint(value);if(!value.working&&value.last_check&&previousCheck!==value.last_check){previousCheck=value.last_check;await onUpdated();}if(root?.isConnected)timer=setTimeout(refresh,value.working?2000:60000);}catch(error){if(root?.isConnected){root.textContent='Runtime update status unavailable: '+error.message;timer=setTimeout(refresh,60000);}}}
 async function perform(op,params){if(pending||readOnly())return;pending=true;try{paint(await action(op,params));}catch(error){onError(error.message);}finally{pending=false;void refresh();}}
 return {mount(element){clearTimeout(timer);root=element;if(root)void refresh();},refresh};
}
