'use strict';
// Isolated UI fixtures: no provider requests, inference or shared workspace writes.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {install}=require('./fixtures/workspace-demo.cjs');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||chromium.executablePath(),headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1350,height:1000}}),errors=[],creates=[],calls=[];
  page.on('pageerror',error=>errors.push(error.message));
  const {data,exp}=await install(page,{tab:'overview',...(process.env.SUPERSURFER_TEST_UI_ROOT?{uiRoot:process.env.SUPERSURFER_TEST_UI_ROOT}:{})}),now=Date.now()/1000;
  data.settings.backends={manager:'codex',lead:'codex',worker:'claude'};
  const agents=[{scope:'experiment:'+exp.id,name:'Task worker',owner:'supersurfer',status:'idle',busy:false}];
  let failed=false,refreshFail=false,selected=agents[0].scope;
  await page.route('http://demo.test/api/experiment-agents*',route=>route.fulfill({json:{experiment_id:exp.id,selected_scope:selected,agents}}));
  await page.route('http://demo.test/api/account*',route=>{
   const id=new URL(route.request().url()).searchParams.get('backend')||'codex';
   if(refreshFail&&id==='claude')return route.fulfill({status:503,json:{error:'Temporary fixture failure'}});
   const metric=(value,source)=>({value,source,observed_at:now,samples:1});
   return route.fulfill({json:{backend:id,installed:true,account:{type:id==='codex'?'chatgpt':id},login_required:false,usage:{account_tokens:id==='codex'?{...metric(98765,'Codex account/usage/read'),scope:'Account lifetime tokens across clients'}:null,quota:id==='codex'?{status:'available',windows:[{label:'codex · primary',remaining_percent:0,window_minutes:300,resets_at:now+1000}],source:'Codex account/rateLimits/read',observed_at:now}:{status:'unavailable',windows:[],note:'The supported CLI does not expose account quota.'},consumption:{tokens:id==='claude'?metric(12345,'Claude result.usage'):null,cost_usd:id==='claude'?metric(0,'Claude result.total_cost_usd'):null,scope:'Observed SuperSurfer sessions on this host, across accounts; excludes native-owner agents.'}}}});
  });
  await page.route('http://demo.test/api/action',route=>{
   const call=route.request().postDataJSON();calls.push(call);
   if(call.op==='experiment.agent.create'){
    creates.push(call.params);
    if(!failed){failed=true;return route.fulfill({status:503,json:{error:'Temporary creation failure'}});}
    const agent={scope:'conversation:manual-created',name:call.params.name,backend:call.params.backend,owner:'supersurfer',status:'idle',busy:false};
    if(!agents.some(x=>x.scope===agent.scope))agents.push(agent);selected=agent.scope;
    return route.fulfill({json:{scope:agent.scope,selected_scope:agent.scope,agents}});
   }
   return route.fulfill({json:{accepted:true}});
  });
  await page.goto('http://demo.test/');
  await page.locator('#chat-new-agent').click();
  const form=page.locator('#create-agent-form');await form.locator('[name=name]').fill('UI developer');
  assert.equal(await form.locator('[name=backend]').inputValue(),'claude');
  await form.getByRole('button',{name:'Create agent',exact:true}).click();
  await form.locator('[role=alert]').waitFor();assert.match(await form.locator('[role=alert]').innerText(),/Retry/);
  await form.getByRole('button',{name:'Create agent',exact:true}).click();await page.locator('#modal').waitFor({state:'hidden'});
  assert.equal(creates.length,2);assert.equal(creates[0].request_id,creates[1].request_id);
  assert.equal(creates[1].backend,'claude');assert.equal(creates[1].project_id,'demo-vla');assert.equal(creates[1].experiment_id,exp.id);
  assert.equal(calls.filter(x=>/chat.send|resume|run.queue/.test(x.op)).length,0);
  await page.reload();await page.locator('[data-action=toggle-agent-list]').click();
  await page.locator('[data-conversation="conversation:manual-created"]').waitFor();
  await page.locator('#chat-new-agent').click();await page.screenshot({path:'/tmp/supersurfer-new-agent.png'});await page.locator('[data-action=close-modal]').first().click();
  await page.locator('.project-row[data-project=demo-vla]').click();await page.locator('#chat-new-agent').click();
  assert.equal(await page.locator('#create-agent-form [name=experiment_id] option').count(),3);
  await page.locator('#create-agent-form [name=name]').fill('Project worker');
  await page.locator('#create-agent-form [name=experiment_id]').selectOption(exp.id);
  await page.locator('#create-agent-form [type=submit]').click();await page.locator('#modal').waitFor({state:'hidden'});
  assert.equal(creates.length,3);assert.equal(creates[2].experiment_id,exp.id);
  await page.locator('[data-view=settings]').click();
  const codex=page.locator('[data-provider-account=codex]'),claude=page.locator('[data-provider-account=claude]');
  await codex.locator('summary').click();await claude.locator('summary').click();
  await page.waitForFunction(()=>document.querySelector('[data-provider-account=codex] .provider-usage-values').textContent.includes('0% remaining'));
  assert.match(await codex.innerText(),/Account tokens \(lifetime\)\s*98,765/);assert.match(await claude.innerText(),/12,345/);assert.match(await claude.innerText(),/\$0\.00 USD · estimate/);
  assert.match(await claude.innerText(),/Account quota\s*Unavailable/);assert.match(await codex.innerText(),/Tokens consumed\s*Unavailable/);
  refreshFail=true;await claude.locator('[data-account-refresh]').click();
  await page.waitForFunction(()=>document.querySelector('[data-provider-account=claude]').textContent.includes('Refresh failed'));
  assert.match(await claude.innerText(),/12,345/);
  for(const width of [1350,850]){await page.setViewportSize({width,height:1000});const overflow=await page.locator('.provider-usage').evaluateAll(elements=>elements.some(el=>el.scrollWidth>el.clientWidth+2));assert.equal(overflow,false);}
  await page.setViewportSize({width:1350,height:1000});await page.screenshot({path:'/tmp/supersurfer-provider-usage.png',fullPage:true});
  data.read_only=true;await page.reload();await page.locator('.project-row[data-project=demo-vla]').click();
  assert.equal(await page.locator('#chat-new-agent').isDisabled(),true);
  assert.deepEqual(errors,[]);
  console.log('PASS manual idle creation, stable retry, provider/scope selection, reload, quota zero vs unknown, token/cost provenance, refresh failure and responsive layout');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
