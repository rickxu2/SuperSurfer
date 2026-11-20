'use strict';
// Isolated Electron fixtures: never signs out a real Google account.
const {_electron:electron}=require('playwright'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {install}=require('./fixtures/workspace-demo.cjs');
(async()=>{
 const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'supersurfer-agy-accounts-'));
 const main=path.join(temporary,'main.cjs');
 fs.writeFileSync(main,"const {app,BrowserWindow}=require('electron');app.whenReady().then(()=>{new BrowserWindow({width:1280,height:900,webPreferences:{sandbox:true,contextIsolation:true,nodeIntegration:false}}).loadURL('about:blank');});");
 let application;
 try{
  const delivered=process.env.SUPERSURFER_PACKAGED_EXECUTABLE;
  application=await electron.launch({...(delivered?{executablePath:delivered}:{}),args:[...(delivered?[]:[main]),`--user-data-dir=${path.join(temporary,'profile')}`],chromiumSandbox:true});
  const page=await application.firstWindow(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await install(page,{tab:'overview',...(delivered?{uiRoot:path.resolve(delivered,'../../Resources/app/ui')}:{})});
  let connected=true,reconnect=false,active=0,logouts=0,logins=0;
  const account=id=>({backend:id,installed:true,account:connected?{type:id==='codex'?'chatgpt':id}:null,login_required:!connected,logout_supported:true,reconnect_required:id==='antigravity'&&reconnect,active_turns:id==='antigravity'?active:0,logout_note:'Signs out the native Google account; other Antigravity clients sharing this login may also be signed out.',usage:{quota:{status:connected?'available':'unavailable',windows:connected?[{label:'Gemini Models',remaining_percent:91}]:[],source:'Native ACP /usage',observed_at:Date.now()/1000},consumption:{}}});
  await page.route('http://demo.test/api/account*',route=>route.fulfill({json:account(new URL(route.request().url()).searchParams.get('backend')||'codex')}));
  await page.route('http://demo.test/api/action',async route=>{
   const body=route.request().postDataJSON();
   if(body.op==='account.logout'){assert.equal(body.params.backend,'antigravity');logouts++;connected=false;return route.fulfill({json:account('antigravity')});}
   if(body.op==='account.login'){assert.equal(body.params.backend,'antigravity');logins++;connected=true;reconnect=false;return route.fulfill({json:{type:'provider',backend:'antigravity',note:'Native Google connection completed.'}});}
   return route.fallback();
  });
  await page.goto('http://demo.test/');
  await page.locator('[data-quota-provider=antigravity]').click();
  const row=page.locator('[data-provider-account=antigravity]'),signout=row.getByRole('button',{name:'Sign out',exact:true}),signin=row.getByRole('button',{name:'Sign in',exact:true});
  await signout.waitFor();assert.equal(await signin.isVisible(),false);
  assert.match(await signout.getAttribute('title'),/other Antigravity clients/);
  active=1;await row.locator('[data-account-refresh]').click();await page.waitForFunction(()=>document.querySelector('[data-account-logout=antigravity]').disabled);
  active=0;await row.locator('[data-account-refresh]').click();await page.waitForFunction(()=>!document.querySelector('[data-account-logout=antigravity]').disabled);
  await signout.click();await signin.waitFor();assert.equal(logouts,1);assert.equal(await signout.isVisible(),false);
  await signin.click();await signout.waitFor();await page.locator('#account-gate').waitFor({state:'hidden'});await page.waitForFunction(()=>!document.querySelector('[data-account-refresh=antigravity]').disabled);assert.equal(logins,1);
  reconnect=true;await row.locator('[data-account-refresh]').click();
  const reconnectButton=row.getByRole('button',{name:'Reconnect',exact:true});await reconnectButton.waitFor();assert.equal(await signout.isDisabled(),true);
  await reconnectButton.click();await page.waitForFunction(()=>!document.querySelector('[data-account-logout=antigravity]').disabled);assert.equal(logins,2);assert.equal(logouts,1);await page.locator('#account-gate').waitFor({state:'hidden'});
  await page.screenshot({path:'/tmp/supersurfer-antigravity-account-controls.png'});
  assert.deepEqual(errors,[]);console.log('PASS native sign-out/sign-in, shared-login notice, active-turn guard and explicit reconnect in isolated Electron.');
 }finally{if(application)await application.close();fs.rmSync(temporary,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});
