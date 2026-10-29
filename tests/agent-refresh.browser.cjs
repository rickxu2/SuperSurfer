'use strict';
const {chromium}=require('playwright'),{spawn}=require('node:child_process'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const child=spawn('python3',['-u','-c',`
import sys, tempfile, threading, json
from pathlib import Path
sys.path.insert(0, 'tests')
from server.app import Service, create_server
from server.aml import AMLClient
from test_backend import FakeCodex, FakeTracking, FakeManager
with tempfile.TemporaryDirectory() as directory:
 service=Service(Path(directory)/'state',Path(directory)/'aml',aml=AMLClient(Path(directory)/'aml',rpc=FakeManager(Path(directory)/'repo')),codex=FakeCodex(),start_monitor=False,tracking=FakeTracking())
 service.codex.account=lambda:{'account':{'type':'chatgpt'},'login_required':False}
 project=service.action('project.add',{'name':'Refresh fixture','repo':str(Path(directory)/'repo'),'surfboard_template':'software'})
 item=service.action('experiment.create',{'project_id':project['id'],'name':'Refresh fixture','summary':'Keep typing'})
 server=create_server(service,port=0)
 print(json.dumps({'port':server.server_port,'directory':str(service.directory),'projects':{'software':project['id']},'items':{'software':item['id']}}),flush=True)
 threading.Thread(target=server.serve_forever,daemon=True).start()
 try: sys.stdin.read()
 finally: server.shutdown();server.server_close();service.close()
`],{stdio:['pipe','pipe','inherit']});let browser;
 try{
  const fixture=await new Promise((resolve,reject)=>{let out='';child.stdout.on('data',chunk=>{out+=chunk;if(out.includes('\n'))resolve(JSON.parse(out.split('\n')[0]));});child.on('exit',code=>reject(Error('fixture '+code)));});
  const token=fs.readFileSync(fixture.directory+'/token','utf8').trim(),origin='http://127.0.0.1:'+fixture.port,pid=fixture.projects.software,eid=fixture.items.software;
  const api=async(route,body)=>{const response=await fetch(origin+'/api/'+route,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});const result=await response.json();assert.ok(response.ok,JSON.stringify(result));return result;};
  const layout=await api('view-layout?project_id='+pid+'&experiment_id='+eid);
  await api('action',{op:'view-layout.save',params:{project_id:pid,experiment_id:eid,version:layout.version,board_version:layout.board_version,pages:[...layout.pages,{id:'conversation',title:'Agent',tiles:[{id:'agent',kind:'chat',span:12,height:750}]}]}});
  const snapshot=await api('state');
  browser=await chromium.launch({executablePath:process.env.CHROME_PATH||chromium.executablePath(),headless:true});
  for(const mode of (process.env.AGENT_REFRESH_MODES||'overview,workflow,surfboard,conversation,detached').split(',')){
   const page=await browser.newPage({viewport:{width:1400,height:950}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(({token,pid,eid,mode})=>{sessionStorage.setItem('supersurfer-token',token);localStorage.setItem('supersurfer-workspace',JSON.stringify({view:'workspace',projectId:pid,experimentId:eid,tab:mode==='detached'?'conversation':mode,chatVisible:true}));},{token,pid,eid,mode});
   let reads=0,stateReads=0;
   await page.route('**/api/state',route=>route.fulfill({json:{...snapshot,settings:{...snapshot.settings,fixture_refresh:++stateReads}}}));
   await page.route('**/api/chat?*',route=>route.fulfill({json:{busy:false,agent:{name:'Test worker'},messages:Array.from({length:60},(_,i)=>({id:'m'+i,role:i%2?'assistant':'user',created:1700000000+i,text:'History '+i+'\n\n'+'Preserve the reading position. '.repeat(15)})),questions:[],approvals:[],refresh:++reads}}));
   await page.goto(origin+(mode==='detached'?`/?panel_project=${pid}&panel_item=${eid}&panel_page=conversation&panel_tile=agent`:''));
   if(mode==='detached'){await page.locator('#main-chat-host #chat-panel').waitFor({state:'attached'});await page.keyboard.press('Control+Shift+B');await page.keyboard.press('Control+Shift+B');}
   await page.locator('#chat-messages .message').last().waitFor();
   await page.waitForTimeout(500);
   const input=page.locator('#chat-input');await input.fill('Draft survives background refresh');await input.focus();
   await input.evaluate(el=>el.setSelectionRange(6,14,'backward'));
   const top=await page.locator('#chat-messages').evaluate(el=>{el.scrollTop=Math.round((el.scrollHeight-el.clientHeight)*.45);return el.scrollTop;});
   const initialReads=reads;
   // Cross two ordinary five-second state polls and several chat updates.
   await page.waitForTimeout(11200);
   assert.ok(reads>initialReads,mode+' must actually refresh chat');
   assert.equal(await input.evaluate(el=>document.activeElement===el),true,mode+' composer lost focus');
   assert.deepEqual(await input.evaluate(el=>[el.selectionStart,el.selectionEnd,el.selectionDirection]),[6,14,'backward'],mode+' selection changed');
   assert.ok(Math.abs(await page.locator('#chat-messages').evaluate(el=>el.scrollTop)-top)<2,mode+' history moved from '+top+' to '+await page.locator('#chat-messages').evaluate(el=>el.scrollTop));
   await page.keyboard.type(' replacement ');assert.equal(await input.inputValue(),'Draft  replacement  background refresh');
   assert.deepEqual(errors,[]);console.log('PASS '+mode+' keeps focus, selection, draft and reading position across polling');await page.close();
  }
 }finally{await browser?.close();child.stdin.end();child.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
