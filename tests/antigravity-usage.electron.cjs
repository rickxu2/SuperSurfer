'use strict';
// One isolated Electron window; no Chrome, live service or provider requests.
const {_electron:electron}=require('playwright'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {install}=require('./fixtures/workspace-demo.cjs');
(async()=>{
 const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'supersurfer-agy-usage-'));
 const main=path.join(temporary,'main.cjs');
 fs.writeFileSync(main,"const {app,BrowserWindow}=require('electron');app.whenReady().then(()=>{const window=new BrowserWindow({width:1280,height:900,webPreferences:{sandbox:true,contextIsolation:true,nodeIntegration:false}});window.loadURL('about:blank');});");
 let application;
 try{
  application=await electron.launch({args:[main,`--user-data-dir=${path.join(temporary,'profile')}`],chromiumSandbox:true});
  const page=await application.firstWindow(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await install(page,{tab:'overview'});
  let unavailable=false,units=false;
  const now=Date.now()/1000;
  await page.route('http://demo.test/api/account*',route=>{
   const id=new URL(route.request().url()).searchParams.get('backend')||'codex',linked=id==='antigravity';
   const windows=unavailable?[]:[{label:'Gemini Models · Weekly Limit Remaining',remaining_percent:91,resets_at:now+600},{label:'Claude and GPT models · Weekly Limit Remaining',remaining_percent:0,resets_at:now+1200},...(units?[{label:'Requests · Daily',remaining_units:1234}]:[])];
   return route.fulfill({json:{backend:id,installed:true,account:linked?{type:id}:null,login_required:!linked,logout_supported:false,usage:{quota:{status:unavailable?'unavailable':'available',windows:linked?windows:[],source:'Antigravity ACP 1.4.5 built-in /usage',observed_at:unavailable?null:now,note:unavailable?'Native quota is unavailable; context is not account quota.':'Native report rounds percentages to integers and reset times to minutes.'},consumption:{}}}});
  });
  await page.goto('http://demo.test/');
  const root=page.locator('#sidebar-quota'),row=root.locator('[data-quota-provider=antigravity]');await row.waitFor();
  assert.match(await row.innerText(),/91%.*0%/);
  assert.match(await row.getAttribute('title'),/Gemini Models.*91% remaining[\s\S]*Claude and GPT models.*0% remaining[\s\S]*built-in \/usage/);
  assert.equal(await row.locator('.quota-level-1.sidebar-quota-fill').evaluate(el=>el.style.width),'0%');
  await row.click();await page.locator('#workspace-accounts').waitFor();
  const details=page.locator('[data-provider-account=antigravity] details');await details.locator('summary').click();
  assert.match(await details.innerText(),/91% remaining.*Gemini Models[\s\S]*0% remaining.*Claude and GPT models/);
  assert.match(await details.innerText(),/Resets/);
  assert.match(await details.innerText(),/rounds percentages to integers/);
  assert.match(await details.innerText(),/Tokens consumed[\s\S]*Unavailable/);
  await page.screenshot({path:'/tmp/supersurfer-antigravity-usage.png'});
  units=true;await root.getByRole('button',{name:'Refresh remaining quota'}).click();
  await page.waitForFunction(()=>document.querySelector('[data-provider-account=antigravity] .provider-usage-values').textContent.includes('1,234 units remaining'));
  unavailable=true;await root.getByRole('button',{name:'Refresh remaining quota'}).click();
  await page.waitForFunction(()=>document.querySelector('[data-quota-provider=antigravity]').textContent.includes('Unavailable'));
  assert.doesNotMatch(await details.innerText(),/91% remaining/);
  assert.match(await details.innerText(),/context is not account quota/);
  assert.deepEqual(errors,[]);
  console.log('PASS Antigravity sidebar groups, zero, source/reset details, units, unavailable replacement and separate token consumption in isolated Electron. Screenshot: /tmp/supersurfer-antigravity-usage.png');
 }finally{if(application)await application.close();fs.rmSync(temporary,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});
