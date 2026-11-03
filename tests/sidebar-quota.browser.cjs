'use strict';
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {install}=require('./fixtures/workspace-demo.cjs');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||chromium.executablePath(),headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1400,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await install(page,{tab:'results',...(process.env.SUPERSURFER_TEST_UI_ROOT?{uiRoot:process.env.SUPERSURFER_TEST_UI_ROOT}:{})});
  const linked={codex:true,claude:true,cursor:false,opencode:false};let failure=false,expired=false,shortOnly=false;
  const now=Date.now()/1000;
  await page.route('http://demo.test/api/account*',route=>{
   const id=new URL(route.request().url()).searchParams.get('backend')||'codex';
   if(failure&&id==='codex')return route.fulfill({status:503,json:{error:'Temporary quota fixture failure'}});
   const windows=id==='codex'?[{label:'codex · primary',remaining_percent:75,window_minutes:300,resets_at:expired?now-1:now+1000},{label:'codex · secondary',remaining_percent:42,window_minutes:10080,resets_at:now+3000}]:id==='claude'?[{label:'five hour',remaining_percent:0,window_minutes:300,resets_at:now+1000},{label:'seven day',remaining_percent:91,window_minutes:10080,resets_at:now+3000}]:[];
   const selected=shortOnly&&id==='codex'?[windows[0],{label:'another model · primary',remaining_percent:99,window_minutes:300}]:windows;
   return route.fulfill({json:{backend:id,installed:true,account:linked[id]?{type:id==='codex'?'chatgpt':id}:null,login_required:!linked[id],usage:{quota:{windows:selected,observed_at:now,source:'Isolated quota fixture'},consumption:{}}}});
  });
  await page.goto('http://demo.test/');
  const root=page.locator('#sidebar-quota');await root.locator('[data-quota-provider=claude]').waitFor();
  assert.equal(await root.locator('[data-quota-provider]').count(),2);
  assert.equal(await page.locator('#workspace-accounts').count(),0,'Quota is visible without opening Settings');
  const codex=root.locator('[data-quota-provider=codex]'),claude=root.locator('[data-quota-provider=claude]');
  assert.match(await codex.innerText(),/75%.*42%/);assert.match(await claude.innerText(),/0%.*91%/);
  assert.match(await codex.getAttribute('aria-label'),/5h: 75% remaining.*7d: 42% remaining/);
  assert.equal(await codex.locator('.quota-level-0.sidebar-quota-fill').evaluate(el=>el.style.width),'75%');
  assert.equal(await codex.locator('.quota-level-1.sidebar-quota-fill').evaluate(el=>el.style.width),'42%');
  const opacity=await codex.locator('.sidebar-quota-fill').evaluateAll(elements=>elements.map(el=>Number(getComputedStyle(el).opacity)));
  assert.ok(opacity[0]>opacity[1]);
  const geometry=await page.locator('.sidebar-footer>button[data-view=settings],#sidebar-quota').evaluateAll(elements=>elements.map(el=>el.getBoundingClientRect().toJSON()));
  assert.ok(geometry[1].y>=geometry[0].bottom-1,'Quota sits directly below Settings');
  for(const [width,theme] of [[1400,'light'],[850,'dark']]){
   await page.setViewportSize({width,height:1000});await page.evaluate(theme=>window.superSurferTheme?.setPreference(theme),theme);
   assert.equal(await root.evaluate(el=>el.scrollWidth>el.clientWidth+1),false);
   await page.screenshot({path:`/tmp/supersurfer-sidebar-quota-${theme}.png`});
  }
  // Transport errors retain linked identity and clearly mark prior observations stale.
  failure=true;await root.getByRole('button',{name:'Refresh remaining quota'}).click();
  await page.waitForFunction(()=>document.querySelector('[data-quota-provider=codex]')?.dataset.stale==='true');
  assert.match(await codex.getAttribute('title'),/Stale observation/);assert.match(await codex.innerText(),/75%.*42%/);
  failure=false;expired=true;await root.getByRole('button',{name:'Refresh remaining quota'}).click();
  await page.waitForFunction(()=>document.querySelector('[data-quota-provider=codex] .sidebar-quota-value')?.textContent==='—');
  assert.match(await codex.getAttribute('title'),/reset; refresh needed/);
  expired=false;shortOnly=true;await root.getByRole('button',{name:'Refresh remaining quota'}).click();
  await page.waitForFunction(()=>document.querySelector('[data-quota-provider=codex] .sidebar-quota-value.quota-level-1')?.textContent==='—');
  assert.match(await codex.innerText(),/75%.*—/,'Do not substitute another model quota for a missing long window');
  linked.claude=false;linked.cursor=true;await root.getByRole('button',{name:'Refresh remaining quota'}).click();
  await root.locator('[data-quota-provider=claude]').waitFor({state:'detached'});
  await root.locator('[data-quota-provider=cursor]').waitFor();assert.match(await root.locator('[data-quota-provider=cursor]').innerText(),/Unavailable/);
  await codex.click();await page.locator('#workspace-accounts').waitFor();
  Object.keys(linked).forEach(id=>linked[id]=false);
  await root.getByRole('button',{name:'Refresh remaining quota'}).click();await root.waitFor({state:'hidden'});
  assert.deepEqual(errors,[]);
  console.log('PASS linked-only sidebar quotas outside Settings, two independent opacity fills/percentages, accessible periods, zero vs unavailable/expired, stale transport errors, account unlink/link, details navigation and light/dark responsive layout');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
