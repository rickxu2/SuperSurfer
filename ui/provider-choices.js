// Only positively verified connected accounts are offered for new selections.
export function connectedProviders(accounts={}){
 return Object.entries(accounts).filter(([id,a])=>a?.installed!==false&&a.account&&!a.error&&!a.transport_error&&!a.reconnect_required&&a.login_required!==true&&a.account.type===(id==='codex'?'chatgpt':id)).map(([id])=>id);
}
export function providerChoices(labels,accounts,current,pinned=false){
 const connected=new Set(connectedProviders(accounts));
 return Object.entries(labels).filter(([id])=>connected.has(id)||pinned&&id===current).map(([id,label])=>({id,label:label+(pinned&&id===current&&!connected.has(id)?' · unavailable; check Settings':''),disabled:!connected.has(id)}));
}
