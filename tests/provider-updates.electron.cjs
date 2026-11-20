'use strict';
// Isolated UI fixture only: no native updater, account login or model inference.
const {_electron:electron}=require('playwright'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {install}=require('./fixtures/workspace-demo.cjs');
(async()=>{
 const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'supersurfer-runtime-ui-')),main=path.join(temporary,'main.cjs');
 fs.writeFileSync(main,"const {app,BrowserWindow}=require('electron');app.whenReady().then(()=>new BrowserWindow({width:1280,height:1000,webPreferences:{sandbox:true,contextIsolation:true,nodeIntegration:false}}).loadURL('about:blank'));");
 let application;
 try{
  const delivered=process.env.SUPERSURFER_PACKAGED_EXECUTABLE;
  application=await electron.launch({...(delivered?{executablePath:delivered}:{}),args:[...(delivered?[]:[main]),`--user-data-dir=${path.join(temporary,'profile')}`],chromiumSandbox:true});
  const page=await application.firstWindow(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await install(page,{tab:'overview',...(delivered?{uiRoot:path.resolve(delivered,'../../Resources/app/ui')}:{})});
  let google=false,checks=0,enabled=false,finished=false,modelReads=0;
  const status=()=>({enabled,working:false,last_check:finished?12345:null,next_check:enabled?Date.now()/1000+21600:null,providers:finished?{codex:{status:'updated',version:'0.170.0',note:'Runtime updated. Refresh models.'}}:{}});
  await page.route('http://demo.test/api/account*',route=>{
   const id=new URL(route.request().url()).searchParams.get('backend')||'codex',linked=id==='codex'||id==='claude'||id==='antigravity'&&google;
   return route.fulfill({json:{backend:id,installed:id!=='cursor',account:linked?{type:id==='codex'?'chatgpt':id}:null,login_required:!linked,usage:{quota:{windows:[]},consumption:{}}}});
  });
  await page.route('http://demo.test/api/chat*',route=>route.fulfill({json:{backend:'codex',busy:false,messages:[],tasks:[],questions:[],approvals:[],preferences:{backend:'codex',editable:true,defaults:{model:'gpt-old',reasoning:'medium'},overrides:{},effective:{model:'gpt-old',reasoning:'medium'},supported_reasoning:['medium']}}}));
  await page.route('http://demo.test/api/provider-updates',route=>route.fulfill({json:status()}));
  await page.route('http://demo.test/api/models*',route=>{modelReads++;return route.fulfill({json:{models:[{id:finished?'gpt-6.2':'gpt-old',displayName:finished?'GPT-6.2':'Old model'}]}});});
  await page.route('http://demo.test/api/action',route=>{
   const body=route.request().postDataJSON();
   if(body.op==='provider.updates.configure'){enabled=body.params.enabled;return route.fulfill({json:status()});}
   if(body.op==='provider.updates.check'){assert.deepEqual(body.params,{});checks++;finished=true;return route.fulfill({json:status()});}
   return route.fallback();
  });
  await page.goto('http://demo.test/');
  await page.waitForFunction(()=>document.querySelector('#chat-backend option[value=claude]'));
  assert.equal(await page.locator('#chat-backend').isEnabled(),true);
  assert.deepEqual(await page.locator('#chat-backend option').evaluateAll(nodes=>nodes.filter(n=>n.value).map(n=>n.value)),['codex','claude']);
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  const checkbox=page.locator('[data-provider-auto-updates]');await checkbox.waitFor();assert.equal(await checkbox.isChecked(),false);
  await checkbox.check();await page.waitForFunction(()=>document.querySelector('[data-provider-auto-updates]').checked);
  const before=modelReads;await page.getByRole('button',{name:'Check & update now',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('[data-provider-update-status]').textContent.includes('0.170.0'));
  await page.waitForFunction(()=>Array.from(document.querySelectorAll('#chat-model option')).some(x=>x.value==='gpt-6.2'));
  assert.equal(checks,1);assert.equal(enabled,true);assert.ok(modelReads>before);
  google=true;await page.locator('[data-account-refresh=antigravity]').click();await page.waitForFunction(()=>document.querySelector('#chat-backend option[value=antigravity]'));
  google=false;await page.locator('[data-account-refresh=antigravity]').click();await page.waitForFunction(()=>!document.querySelector('#chat-backend option[value=antigravity]'));
  await page.locator('#provider-runtime-updates').scrollIntoViewIfNeeded();
  await page.screenshot({path:'/tmp/supersurfer-provider-updates.png'});assert.deepEqual(errors,[]);
  console.log('PASS signed-in-only picker, login-state refresh, auto-update opt-in, fixed update action, status and refreshed model catalog in isolated Electron.');
 }finally{if(application)await application.close();fs.rmSync(temporary,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});
