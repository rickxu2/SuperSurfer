'use strict';
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process');
(async()=>{
 const root=path.resolve(__dirname,'..'),fixture=spawn(process.env.PYTHON||'python3',['tests/backend_runtime_fixture.py'],{cwd:root,stdio:['pipe','pipe','pipe']});let browser,stderr='';fixture.stderr.on('data',v=>stderr+=v);
 try{
  const meta=await new Promise((resolve,reject)=>{let text='';fixture.stdout.on('data',v=>{text+=v;if(text.includes('\n'))resolve(JSON.parse(text.split('\n')[0]));});fixture.on('exit',code=>reject(new Error(code+' '+stderr)));}),base='http://127.0.0.1:'+meta.port,token=fs.readFileSync(path.join(meta.directory,'token'),'utf8').trim();
  browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/opt/google/chrome/chrome',headless:true,args:['--no-sandbox']});const page=await browser.newPage({viewport:{width:1440,height:900}});page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(({token,id})=>{sessionStorage.setItem('supersurfer-token',token);localStorage.setItem('supersurfer-workspace',JSON.stringify({view:'workspace',projectId:'p1',experimentId:id,tab:'overview',chatVisible:true}));},{token,id:meta.experiment});
  await page.goto(base);await page.locator('#chat-form').waitFor();
  // Composer insets are equal on all three sides and line up with the message column.
  const insets=()=>page.evaluate(()=>{const f=document.querySelector('#chat-form').getBoundingClientRect(),p=document.querySelector('.chat-panel'),b=p.getBoundingClientRect(),m=document.querySelector('.chat-messages'),s=getComputedStyle(m),r=m.getBoundingClientRect(),border=parseFloat(getComputedStyle(p).borderRightWidth)||0;
    return {left:f.left-r.left,right:r.right-f.right,bottom:b.bottom-border-f.bottom,textLeft:parseFloat(s.paddingLeft),textRight:parseFloat(s.paddingRight)};});
  for(const width of [1440,1100]){await page.setViewportSize({width,height:900});await page.waitForTimeout(150);const v=await insets();
   for(const key of ['left','right','bottom'])assert.ok(Math.abs(v[key]-v.textLeft)<=1.5,`${width}px ${key} inset ${JSON.stringify(v)}`);}
  await page.setViewportSize({width:1440,height:900});await page.locator('[data-action="toggle-chat-maximized"],[aria-label="Maximize chat"],[title*="Maximize"]').first().click().catch(()=>{});
  if(await page.evaluate(()=>document.querySelector('.app-shell')?.classList.contains('chat-maximized'))){const v=await page.evaluate(()=>{const f=document.querySelector('#chat-form').getBoundingClientRect(),m=document.querySelector('.chat-messages'),r=m.getBoundingClientRect(),s=getComputedStyle(m),p=document.querySelector('.chat-panel').getBoundingClientRect();return {left:f.left-r.left-parseFloat(s.paddingLeft),right:r.right-parseFloat(s.paddingRight)-f.right,bottom:p.bottom-f.bottom,gutter:parseFloat(s.paddingLeft)};});
   assert.ok(Math.abs(v.left)<=1.5&&Math.abs(v.right)<=1.5&&Math.abs(v.bottom-v.gutter)<=2,'maximized composer '+JSON.stringify(v));await page.keyboard.press('Escape');await page.locator('[data-action="toggle-chat-maximized"],[aria-label="Restore chat"],[title*="Restore"]').first().click().catch(()=>{});}
  // The panel actions menu opens inside its tile and page panel instead of off the right edge.
  for(const width of [1440,1100]){await page.setViewportSize({width,height:900});await page.locator('.tile-space-menu>summary').first().click();const menu=page.locator('.tile-space-menu[open]>div').first();await menu.waitFor();
   const box=await menu.evaluate(n=>{const m=n.getBoundingClientRect(),t=n.closest('.page-tile,.tile,[data-tile]')||n.closest('main');const c=t.getBoundingClientRect();let clip=n.parentElement;while(clip&&getComputedStyle(clip).overflowX==='visible')clip=clip.parentElement;const k=(clip||document.body).getBoundingClientRect();return {m:[m.left,m.right,m.top,m.bottom],tile:[c.left,c.right],clip:[k.left,k.right,k.top,k.bottom]};});
   assert.ok(box.m[0]>=box.tile[0]&&box.m[1]<=box.tile[1]+0.5,`${width}px menu outside tile ${JSON.stringify(box)}`);assert.ok(box.m[1]<=box.clip[1]+0.5&&box.m[3]<=box.clip[3]+0.5,`${width}px menu clipped ${JSON.stringify(box)}`);
   for(const label of ['Space on left','Space on right','Space above','Space below','Remove block']){const item=page.getByRole('button',{name:label});if(await item.count())await item.first().hover({trial:true});}
   if(width===1440)await page.screenshot({path:process.env.SHOT_DIR?path.join(process.env.SHOT_DIR,'tile-menu.png'):'/dev/null'}).catch(()=>{});
   await page.locator('.tile-space-menu>summary').first().click();}
  assert.deepEqual(errors,[]);console.log('PASS equal composer insets aligned with messages and in-panel tile actions menu');
 }finally{if(browser)await browser.close();fixture.stdin.end();await new Promise(resolve=>fixture.once('exit',resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
