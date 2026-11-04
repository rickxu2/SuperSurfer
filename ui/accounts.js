import {linkedAccount,paintSidebarQuota} from './sidebar-quota.js';
const providers={codex:'ChatGPT / Codex',cursor:'Cursor',claude:'Claude Code',opencode:'OpenCode',antigravity:'Google Antigravity'};
const installUrls={codex:'https://developers.openai.com/codex/cli/',cursor:'https://cursor.com/docs/cli/installation',claude:'https://code.claude.com/docs/en/setup',opencode:'https://opencode.ai/docs',antigravity:'https://antigravity.google/docs/ide/extensions'};
const usageUrls={codex:'https://chatgpt.com/codex/settings/usage',cursor:'https://cursor.com/dashboard',claude:'https://claude.ai/settings/usage',opencode:'https://opencode.ai/docs/providers/',antigravity:'https://antigravity.google/docs/plans'};
const observed=at=>at?new Date(at*1000).toLocaleString():'No observation yet';
function paintUsage(element,value){
 element.replaceChildren();
 const line=(label,text,detail)=>{const row=document.createElement('div'),title=document.createElement('strong'),body=document.createElement('span'),note=document.createElement('small');title.textContent=label;body.textContent=text;note.textContent=detail;row.append(title,body,note);element.append(row);};
 const usage=value?.usage,quota=usage?.quota,consumption=usage?.consumption;
 if(!value){line('Account quota','Checking…','');return;}
 if(quota?.windows?.length){for(const window of quota.windows){const stale=quota.stale||Date.now()/1000-quota.observed_at>120||(window.resets_at&&window.resets_at<Date.now()/1000);line('Account quota',`${window.unlimited?'Unlimited credits':window.remaining_credits!=null?window.remaining_credits.toLocaleString()+' credits remaining':window.remaining_units!=null?window.remaining_units.toLocaleString()+' units remaining':window.remaining_percent+'% remaining'} · ${window.label}${window.window_minutes?` · ${window.window_minutes} min window`:''}${stale?' · stale':''}`,`${quota.source} · ${observed(quota.observed_at)}${window.resets_at?' · Resets '+observed(window.resets_at):''}`);}}
 else line('Account quota','Unavailable',quota?.note||'This provider did not expose remaining account quota.');
 if(quota?.windows?.length&&quota.note)line('Quota details',quota.note,'');
 const accountTokens=usage?.account_tokens;
 if(accountTokens)line('Account tokens (lifetime)',accountTokens.value.toLocaleString(),`${accountTokens.source} · ${observed(accountTokens.observed_at)} · ${accountTokens.scope}`);
 for(const [key,label] of [['tokens','Tokens consumed'],['cost_usd','Cost consumed']]){const metric=consumption?.[key];line(label,metric?key==='tokens'?metric.value.toLocaleString():`$${metric.value.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:6})} USD · estimate`:'Unavailable',metric?`${metric.source} · ${observed(metric.observed_at)}`:'No supported usage observation has been received.');}
 const note=document.createElement('small');note.textContent=consumption?.scope||'Consumption covers observed SuperSurfer sessions on this host, across accounts. Native-owner agents and unreported activity are excluded.';element.append(note);
 if(value.usage_stale){const warning=document.createElement('small');warning.textContent='Refresh failed. Showing previous consumption observations; refresh to retry.';element.append(warning);}
}
export function createWorkspaceAccounts({api,action,gate,readOnly,onError}){
 const records=new Map(),busy=new Set(),inflight=new Map(),revisions=new Map();let root=null,sidebar=null;
 const markup=()=>`<div class="workspace-accounts">${Object.entries(providers).map(([id,label])=>`<div class="workspace-account-row" data-provider-account="${id}"><div><strong>${label}</strong><small class="provider-account-status" role="status">Checking…</small><details class="provider-usage"><summary>Usage &amp; remaining quota</summary><div class="provider-usage-values"></div><a href="${usageUrls[id]}" target="_blank" rel="noopener noreferrer">Provider usage dashboard / configuration ↗</a><small>Refresh to update. Provider cost estimates are not invoices.</small></details></div><a class="provider-install" href="${installUrls[id]}" target="_blank" rel="noopener noreferrer" hidden>Install CLI</a><button type="button" class="button small-button" data-account-login="${id}">Sign in</button><button type="button" class="button small-button" data-account-logout="${id}" hidden>Sign out</button><button type="button" class="icon-button" data-account-refresh="${id}" title="Refresh ${label} status and usage" aria-label="Refresh ${label} status">↻</button></div>`).join('')}</div>`;
 function paint(){paintSidebarQuota(sidebar,records,{refresh:()=>refreshAll(true),openSettings:()=>sidebar?.dispatchEvent(new CustomEvent('quota-details',{bubbles:true})),loading:inflight.size>0});if(!root?.isConnected)return;for(const [id,label] of Object.entries(providers)){
  const row=root.querySelector(`[data-provider-account="${id}"]`),record=records.get(id),value=record?.value,connected=linkedAccount(value);
  if(!row)continue;const working=busy.has(id),loading=inflight.has(id),active=value?.active_turns>0;
  row.querySelector('.provider-account-status').textContent=working?'Signing out…':!value?'Checking…':value.error||value.note||(connected?['Signed in',value.account.email||value.account.authMethod,active?value.active_turns+' active turn'+(value.active_turns===1?'':'s'):''].filter(Boolean).join(' · '):'Signed out');
  row.querySelector('.provider-install').hidden=value?.installed!==false;
  paintUsage(row.querySelector('.provider-usage-values'),value);
  const login=row.querySelector('[data-account-login]'),logout=row.querySelector('[data-account-logout]');login.hidden=connected;logout.hidden=!connected||value?.logout_supported===false;
  login.disabled=readOnly()||working||loading;login.textContent=value?.installed===false?'Set up':'Sign in';logout.disabled=readOnly()||working||active;logout.title=active?'Finish or stop this provider’s active turns before signing out.':'Sign out on this machine';row.querySelector('[data-account-refresh]').disabled=working||loading;
 }}
 function observe(value){const id=value.backend||'codex',previous=records.get(id)?.value;value=value.transport_error&&previous?.account?{...previous,error:value.error,usage_stale:true}:{...value,backend:id};records.set(id,{value,at:Date.now()});paint();}
 async function refresh(id,force=false){
  if(inflight.has(id))return inflight.get(id);if(!force&&records.has(id)&&Date.now()-records.get(id).at<30000)return;
  const revision=revisions.get(id)||0;const task=(async()=>{try{let value=await api('account?'+new URLSearchParams({backend:id,...(force?{refresh:'1'}:{})}));if(revision!==(revisions.get(id)||0))return;if(value.backend&&value.backend!==id)throw new Error('This machine returned a different provider account. Refresh the workspace.');value={...value,backend:id};observe(value);gate.observe(value);}catch(error){if(revision===(revisions.get(id)||0)){const previous=records.get(id)?.value;observe({...previous,backend:id,login_required:previous?.login_required??true,error:error.message,usage_stale:true});}}finally{inflight.delete(id);paint();}})();inflight.set(id,task);paint();return task;
 }
 async function logout(id){
  if(readOnly()||busy.has(id))return;revisions.set(id,(revisions.get(id)||0)+1);busy.add(id);paint();
  try{const value=await action('account.logout',{backend:id});observe(value);gate.signedOut(value);}
  catch(error){onError(error.message);}
  finally{busy.delete(id);paint();}
 }
 function mount(element){root=element;if(!root)return;if(!root.querySelector('[data-provider-account]'))root.innerHTML=markup();root.onclick=event=>{const button=event.target.closest('button');if(!button||button.disabled)return;const id=button.dataset.accountLogin||button.dataset.accountLogout||button.dataset.accountRefresh;if(!id)return;event.preventDefault();if(button.dataset.accountLogin)void gate.open(id);else if(button.dataset.accountLogout)void logout(id);else void refresh(id,true);};paint();void Promise.allSettled(Object.keys(providers).map(id=>refresh(id)));}
 function refreshAll(force=false){return Promise.allSettled(Object.keys(providers).map(id=>refresh(id,force)));}
 function mountSidebar(element){sidebar=element;paint();void refreshAll();}
 return {mount,mountSidebar,observe,repaint:paint,refresh:refreshAll};
}
