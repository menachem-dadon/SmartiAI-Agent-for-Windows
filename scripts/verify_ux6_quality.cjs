const {browserQA}=require('./ux6_browser_support.cjs');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const {performance}=require('node:perf_hooks');
const percentile=(values,p)=>[...values].sort((a,b)=>a-b)[Math.min(values.length-1,Math.floor(values.length*p))];
async function main(){
 const base=process.argv[2]||'http://127.0.0.1:1446',output=path.resolve(process.argv[3]||'.codex-local/ux-6/baseline/browser');await fs.mkdir(output,{recursive:true});
 const layoutOnly=process.argv.includes('--layout-only');
 const qa=await browserQA(),{page,browser,api,handshake}=qa;
 const checks=[],failures=[],errors=[],failedRequests=[],navigations=[],metrics=[],geometry=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('requestfailed',r=>failedRequests.push({url:new URL(r.url()).pathname,error:r.failure()?.errorText}));
 const check=(name,ok)=>{(ok?checks:failures).push(name);};
 const ready=()=>page.locator('.chat-column').waitFor({timeout:30000});
 const select=async title=>{await page.locator('.conversation-select').filter({hasText:title}).click();await page.getByRole('heading',{name:title,exact:true}).waitFor();};
 const frame=()=>page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
 try{
  for(let n=0;n<(layoutOnly?1:10);n++){
   const start=performance.now();if(n===0||n===5)await page.goto(base);else await page.reload();await ready();
   navigations.push({kind:n===0?'fresh':n===5?'navigation':'reload',ms:performance.now()-start,...await page.evaluate(()=>({rootChildren:document.getElementById('root').childElementCount,resources:performance.getEntriesByType('resource').map(r=>({name:new URL(r.name).pathname,duration:r.duration,bytes:r.transferSize})),html:performance.getEntriesByType('navigation')[0]?.responseEnd}))});
  }
  check(layoutOnly?'layout navigation produces a populated root':'ten navigations/reloads produce a populated root',navigations.every(n=>n.rootChildren>0));
  for(const [title,count] of (layoutOnly?[]:[['מחקר לקראת המפגש',202],['UX6 1000 messages',1000]])){
   const start=performance.now();await select(title);await page.waitForFunction(()=>document.querySelectorAll('.chat-message-row').length>0);await frame();
   metrics.push({title,count,kind:'initial paged selection',ms:performance.now()-start,rendered:await page.locator('.chat-message-row').count()});
   const loadStart=performance.now();let pages=0;
   while(await page.getByRole('button',{name:/^טעינת \d+ הודעות קודמות$/}).count()){
    const older=page.getByRole('button',{name:/^טעינת \d+ הודעות קודמות$/});const oldName=await older.textContent();await older.click();
    await page.waitForFunction(old=>{const b=[...document.querySelectorAll('button')].find(e=>/^טעינת \d+ הודעות קודמות$/.test(e.textContent.trim()));return!b||b.textContent!==old;},oldName);if(++pages>25)throw Error('Unexpected paging loop');
   }
   check(`${count} stored messages all loaded`,await page.locator('.chat-message-row').count()>=count);
   const frames=await page.locator('.chat-stage').evaluate(e=>new Promise(resolve=>{const intervals=[],start=performance.now();let previous=start;const tick=now=>{intervals.push(now-previous);previous=now;e.scrollTop=((now-start)/2000)*(e.scrollHeight-e.clientHeight);if(now-start<2000)requestAnimationFrame(tick);else resolve({intervals,elapsed:now-start,scrollTop:e.scrollTop,scrollHeight:e.scrollHeight});};requestAnimationFrame(tick);}));
   metrics.push({title,count,kind:'all loaded',loadAllMs:performance.now()-loadStart-frames.elapsed,pages,rendered:await page.locator('.chat-message-row').count(),rAF:{samples:frames.intervals.length,medianMs:percentile(frames.intervals,.5),p95Ms:percentile(frames.intervals,.95),over33ms:frames.intervals.filter(n=>n>33.34).length},heap:await page.evaluate(()=>performance.memory?{used:performance.memory.usedJSHeapSize,total:performance.memory.totalJSHeapSize}:null)});
  }
  const draft=page.getByRole('textbox',{name:'הודעה',exact:true});await draft.fill('UX6 שלום English retained draft');
  const stage=page.locator('.chat-stage');await stage.evaluate(e=>e.scrollTop=600);const scroll=await stage.evaluate(e=>e.scrollTop);
  await page.getByRole('button',{name:'הגדרות',exact:true}).click();await page.getByRole('button',{name:'חזרה לצ׳אט',exact:true}).waitFor();
  await page.waitForFunction(()=>document.activeElement?.getAttribute('aria-label')==='חזרה לצ׳אט');
  await page.keyboard.press('Escape');await page.locator('.management-overlay').waitFor({state:'hidden'});
  check('management Escape restores triggering focus',await page.getByRole('button',{name:'הגדרות',exact:true}).evaluate(e=>e===document.activeElement));
  check('management retains draft and old reading position',await draft.inputValue()==='UX6 שלום English retained draft'&&Math.abs(await stage.evaluate(e=>e.scrollTop)-scroll)<3);
  await page.getByRole('button',{name:'פעולות שיחה',exact:true}).click();await page.keyboard.press('Escape');
  check('menu Escape restores focus',await page.getByRole('button',{name:'פעולות שיחה',exact:true}).evaluate(e=>e===document.activeElement));
  for(const theme of ['light','dark'])for(const width of [360,500,1380])for(const zoom of [1,1.5,2]){
   await api('PATCH','/v2/settings',{values:{ui_preferences:{theme_mode:theme}}});await page.reload();await ready();await page.setViewportSize({width,height:900});
   await page.evaluate(z=>{document.documentElement.style.zoom=String(z);},zoom);await frame();
   const g=await page.locator('.composer').evaluate(e=>{const r=e.getBoundingClientRect(),buttons=[...e.querySelectorAll('button')].filter(b=>b.getClientRects().length).map(b=>{const q=b.getBoundingClientRect();return{name:b.getAttribute('aria-label')||b.textContent,x:q.x,right:q.right,width:q.width,height:q.height}});return{viewport:innerWidth,scale:devicePixelRatio,x:r.x,right:r.right,width:r.width,buttons,overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth,lang:document.documentElement.lang};});
   geometry.push({theme,width,zoom,...g});check(`${theme}/${width}/zoom${zoom} composer remains inside viewport`,g.x>=-1&&g.right<=width+1&&g.overflow<=1);
   if(zoom===1&&[360,1380].includes(width))await page.screenshot({path:path.join(output,`${theme}-${width}.png`)});
  }
  await page.evaluate(()=>document.documentElement.style.zoom='1');await page.setViewportSize({width:1380,height:900});
  await page.emulateMedia({reducedMotion:'reduce'});await page.getByRole('button',{name:'פתיחת סביבת העבודה',exact:true}).click();await frame();
  check('reduced motion leaves no active chat layer animation',await page.locator('.chat-column').evaluate(e=>e.getAnimations().filter(a=>a.playState==='running').length===0));
  await page.locator('.workbench-empty').getByRole('button',{name:'קבצים',exact:true}).click();
  for(const name of ['מסוף','תוצרים']){await page.getByRole('button',{name:'פתיחת לשונית',exact:true}).click();await page.getByRole('menuitem',{name,exact:true}).click();}
  check('multiple real workbench tabs remain mounted',await page.locator('.workbench-tab').count()===3);
  await page.getByRole('button',{name:'סגירת סביבת העבודה',exact:true}).click();await frame();
  if(!layoutOnly){const cdp=await browser.newBrowserCDPSession(),info=await cdp.send('SystemInfo.getProcessInfo');
  metrics.push({kind:'idle multi-tab process sample',...JSON.parse(String(execFileSync('pwsh',['-NoProfile','-File','scripts/measure_ux6_processes.ps1','-RootIds',String(info.processInfo.find(p=>p.type==='browser').id)+','+handshake.pid],{windowsHide:true,encoding:'utf8'})))});}
  check('no uncaught renderer exceptions',errors.length===0);
  const ax=await page.locator('body').ariaSnapshot();await fs.writeFile(path.join(output,'accessibility-tree.yaml'),ax);
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({checks,failures,errors,failedRequests,navigations,metrics,geometry,version:browser.version(),scope:'Edge / actual isolated Core; adapted IPC; CSS zoom is reflow simulation, not Windows DPI/text scaling; AX tree is not spoken screen reader; rAF intervals are not compositor FPS'},null,2));
  if(failures.length)process.exitCode=1;
 }catch(e){await page.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});await fs.writeFile(path.join(output,'failure.json'),JSON.stringify({error:String(e),checks,errors,failedRequests,navigations,metrics,geometry},null,2));throw e;}
 finally{await qa.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
