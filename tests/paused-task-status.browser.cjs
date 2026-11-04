'use strict';
// Isolated official-CLI wire fixture; no real account, inference or running job.
const {chromium,_electron}=require('playwright'),{spawn}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
(async()=>{
 const root=path.resolve(__dirname,'..'),fixture=spawn(process.env.PYTHON||'python3',['tests/backend_runtime_fixture.py','--planning-preparing'],{cwd:root,stdio:['pipe','pipe','pipe']});let browser,profile,stderr='';fixture.stderr.on('data',v=>stderr+=v);
 try{
  const meta=await new Promise((resolve,reject)=>{let out='';fixture.stdout.on('data',v=>{out+=v;if(out.includes('\n'))resolve(JSON.parse(out.split('\n')[0]));});fixture.on('exit',code=>reject(Error(code+' '+stderr)));});
  const token=fs.readFileSync(path.join(meta.directory,'token'),'utf8').trim(),base='http://127.0.0.1:'+meta.port;
  if(process.env.SUPERSURFER_PACKAGED_EXECUTABLE){profile=fs.mkdtempSync(path.join(os.tmpdir(),'supersurfer-paused-task-'));browser=await _electron.launch({executablePath:process.env.SUPERSURFER_PACKAGED_EXECUTABLE,args:['--user-data-dir='+profile],chromiumSandbox:true});}
  else browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/opt/google/chrome/chrome',headless:true,args:['--no-sandbox']});
  const page=profile?await browser.firstWindow():await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(15000);
  await page.addInitScript(({token,id})=>{sessionStorage.setItem('supersurfer-token',token);if(!localStorage.getItem('supersurfer-workspace'))localStorage.setItem('supersurfer-workspace',JSON.stringify({view:'workspace',projectId:'p1',experimentId:id,tab:'overview',chatVisible:true}));},{token,id:meta.experiment});
  await page.goto(base);await page.getByLabel('Conversation backend').selectOption('claude');
  await page.waitForFunction(()=>document.querySelector('#chat-backend')?.value==='claude'&&!document.querySelector('#chat-send').disabled);
  const dot=page.locator('#project-tree [data-experiment="'+meta.experiment+'"] .status-dot');
  const colorMatches=color=>page.waitForFunction(({id,color})=>{const el=document.querySelector('#project-tree [data-experiment="'+id+'"] .status-dot');if(!el)return false;const reference=document.createElement('i');reference.style.background='var(--'+color+')';document.body.append(reference);const expected=getComputedStyle(reference).backgroundColor;reference.remove();return getComputedStyle(el).backgroundColor===expected;},{id:meta.experiment,color});
  const start=async()=>{await page.locator('#chat-input').fill('hold');await page.locator('#chat-send').click();await page.waitForFunction(()=>!document.querySelector('#chat-stop').disabled);await page.locator('[data-action=refresh]').first().click();await dot.locator('xpath=self::*[contains(@class,"working")]').waitFor();};
  const stop=async()=>{await page.locator('#chat-stop').click();await page.waitForFunction(()=>!document.querySelector('#chat-send').disabled);await dot.locator('xpath=self::*[contains(@class,"paused")]').waitFor();};
  await start();await stop();assert.match(await dot.getAttribute('title'),/paused by the user/);
  await page.reload();await dot.locator('xpath=self::*[contains(@class,"paused")]').waitFor();
  for(const theme of ['light','dark']){
   await page.evaluate(theme=>window.superSurferTheme.setPreference(theme),theme);
   await colorMatches('red');
   if(process.env.SUPERSURFER_QA_OUTPUT){fs.mkdirSync(process.env.SUPERSURFER_QA_OUTPUT,{recursive:true});await page.locator('.sidebar').screenshot({path:path.join(process.env.SUPERSURFER_QA_OUTPUT,'paused-task-'+theme+'.png')});}
  }
  await start();await colorMatches('green');await stop();
  assert.deepEqual(errors,[]);console.log('PASS preparing → working → paused/red; reload persistence; light/dark; resume → working/green → paused/red through real Stop action and offline CLI wire');
 }finally{await browser?.close();fixture.stdin.end();if(profile)fs.rmSync(profile,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});
