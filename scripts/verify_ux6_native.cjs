// Actual built/dev Tauri, guarded by executable, data path and app identifier.
const {chromium}=require('playwright');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process'),{randomUUID}=require('node:crypto');
const {performance}=require('node:perf_hooks');
async function main(){
 const mode=process.argv.includes('--dev')?'dev':'built',output=path.resolve(process.argv[2]||`.codex-local/ux-6/native-${mode}`);await fs.mkdir(output,{recursive:true});
 const launch=JSON.parse(await fs.readFile(`.codex-local/ux-6/native-${mode}-launch.json`,'utf8'));
 assert.notEqual(launch.deterministic,false,'Refusing automation on the live-provider user trial');
 assert.match(String(launch.pid),/^\d+$/);assert.equal(launch.identifier,'ai.smarti.ux6'+mode);
 assert.ok(path.resolve(launch.data).startsWith(path.resolve('.codex-local/ux-6')+path.sep));
 const exe=execFileSync('pwsh',['-NoProfile','-Command',`[Console]::OutputEncoding=[Text.UTF8Encoding]::new();(Get-Process -Id ${launch.pid}).Path`],{windowsHide:true,encoding:'utf8'}).trim();
 assert.equal(path.win32.basename(exe),'ux6-'+mode+'.exe');assert.equal(path.resolve(exe),path.resolve(launch.executable));
 const browser=await chromium.connectOverCDP(launch.cdp);
 const page=browser.contexts()[0].pages().find(p=>mode==='dev'?p.url().includes('127.0.0.1:1446'):p.url().includes('tauri.localhost'));
 assert.ok(page,'owned main renderer');
 const invoke=(cmd,args={})=>page.evaluate(({cmd,args})=>window.__TAURI_INTERNALS__.invoke(cmd,args),{cmd,args});
 assert.equal(await invoke('plugin:app|identifier'),launch.identifier);
 const api=async(method,route,body)=>{const r=await invoke('core_api',{request:{method,path:route,body:body??null,idempotencyKey:method==='GET'?null:randomUUID()}});assert.ok(r.status>=200&&r.status<300,route+': '+r.status);return r.body.data;};
 const checks=[],errors=[],metrics=[],geometry=[];page.on('pageerror',e=>errors.push(e.message));
 const check=(name,ok)=>{assert.ok(ok,name);checks.push(name);};
 const resize=width=>JSON.parse(execFileSync('pwsh',['-NoProfile','-File','scripts/resize_ux6_window.ps1','-Mode',mode,'-ProbeProcessId',String(launch.pid),'-Width',String(width),'-Height','900'],{windowsHide:true,encoding:'utf8'}));
 const ready=()=>page.locator('.chat-column').waitFor({timeout:30000});
 try{
  const status=await invoke('core_status');assert.equal(status.state,'ready');
  resize(1380);const legal=await api('GET','/v2/management/legal');
  if(!legal.accepted){await page.getByRole('checkbox').check();await page.getByRole('button',{name:'אני מסכים',exact:true}).click();}
  await ready();
  for(let n=0;n<10;n++){const start=performance.now();await page.reload();await ready();metrics.push({kind:'native reload',ms:performance.now()-start});}
  check('ten real WebView reloads keep root and Core PID',status.pid===(await invoke('core_status')).pid);
  for(const count of [200,1000]){
   const title=`UX6 ${count} messages`,start=performance.now();await page.locator('.conversation-select').filter({hasText:title}).click();
   await page.getByRole('heading',{name:title,exact:true}).waitFor();await page.waitForFunction(()=>document.querySelectorAll('.chat-message-row').length>0);
   metrics.push({kind:'native paged selection',count,ms:performance.now()-start});const loadStart=performance.now();let pages=0;
   while(await page.getByRole('button',{name:/^טעינת \d+ הודעות קודמות$/}).count()){
    const older=page.getByRole('button',{name:/^טעינת \d+ הודעות קודמות$/});const before=await older.textContent();await older.click();
    await page.waitForFunction(old=>{const b=[...document.querySelectorAll('button')].find(e=>/^טעינת \d+ הודעות קודמות$/.test(e.textContent.trim()));return!b||b.textContent!==old;},before);assert.ok(++pages<=25);
   }
   const frames=await page.locator('.chat-stage').evaluate(e=>new Promise(resolve=>{const start=performance.now(),intervals=[];let prev=start;const tick=now=>{intervals.push(now-prev);prev=now;e.scrollTop=(now-start)/2000*(e.scrollHeight-e.clientHeight);if(now-start<2000)requestAnimationFrame(tick);else resolve(intervals);};requestAnimationFrame(tick);}));
   metrics.push({kind:'native all messages loaded',count,loadAllMs:performance.now()-loadStart-2000,pages,rendered:await page.locator('.chat-message-row').count(),rAF:frames});
   check(`${count} messages loaded in real Windows renderer`,await page.locator('.chat-message-row').count()>=count);
  }
  const draft=page.getByRole('textbox',{name:'הודעה',exact:true});await draft.fill('UX6 native שלום English draft');
  for(const theme of ['light','dark'])for(const width of [360,500,1380]){
   await api('PATCH','/v2/settings',{values:{ui_preferences:{theme_mode:theme}}});await page.reload();await ready();const window=resize(width);await page.waitForFunction(w=>Math.abs(innerWidth-w)<2,width);
   const g=await page.locator('.composer').evaluate(e=>{const r=e.getBoundingClientRect();return{x:r.x,right:r.right,width:r.width,viewport:innerWidth,dpr:devicePixelRatio,lang:document.documentElement.lang,overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth};});
   geometry.push({theme,viewportWidth:width,window,...g});check(`${theme}/${width} physical window and composer bounds`,Math.abs(g.viewport-width)<2&&g.right<=width+1&&g.overflow<=1);
   await page.screenshot({path:path.join(output,`${theme}-${width}.png`)});
  }
  resize(1380);await invoke('desktop_focus_main');
  await page.waitForTimeout(500);
  check('native draft survives six theme/window reloads',await draft.inputValue()==='UX6 native שלום English draft');
  const before=await page.locator('.chat-stage').evaluate(e=>{e.scrollTop=400;return e.scrollTop;});
  await page.waitForTimeout(150);
  await page.getByRole('button',{name:'הגדרות',exact:true}).click();
  await page.waitForFunction(()=>document.activeElement?.getAttribute('aria-label')==='חזרה לצ׳אט');
  await page.keyboard.press('Escape');await page.locator('.management-overlay').waitFor({state:'hidden'});
  await page.waitForFunction(()=>document.activeElement?.getAttribute('aria-label')==='הגדרות'||document.activeElement?.textContent.trim()==='הגדרות');
  check('native management focus returns to trigger',await page.getByRole('button',{name:'הגדרות',exact:true}).evaluate(e=>e===document.activeElement));
  const roundTrip={before,after:await page.locator('.chat-stage').evaluate(e=>e.scrollTop),draftPreserved:await draft.inputValue()==='UX6 native שלום English draft'};
  metrics.push({kind:'native management scroll round trip',...roundTrip});
  check('native draft and scroll survive management',roundTrip.draftPreserved&&Math.abs(roundTrip.after-before)<3);
  // A real PowerShell process continues while its UI is hidden behind management.
  const terminal=await api('POST','/v2/workbench/terminals',{});
  await api('POST',`/v2/workbench/terminals/${terminal.id}`,{action:'write',text:"Start-Sleep -Seconds 3; Write-Output 'UX6_HIDDEN_COMPLETE'\n"});
  await page.getByRole('button',{name:'הגדרות',exact:true}).click();
  await invoke('desktop_set_close_to_tray',{enabled:true});await invoke('plugin:window|close');
  let terminalText='',deadline=Date.now()+15000;
  while(Date.now()<deadline&&!terminalText.includes('UX6_HIDDEN_COMPLETE')){await new Promise(r=>setTimeout(r,150));terminalText+=(await api('GET',`/v2/workbench/terminals/${terminal.id}`)).output;}
  check('actual terminal continues with main Windows window hidden to tray',terminalText.includes('UX6_HIDDEN_COMPLETE'));
  await invoke('desktop_focus_main');await invoke('desktop_set_close_to_tray',{enabled:false});
  await api('DELETE',`/v2/workbench/terminals/${terminal.id}`,{});
  await page.keyboard.press('Escape');
  await page.emulateMedia({reducedMotion:'reduce'});await page.getByRole('button',{name:'פתיחת סביבת העבודה',exact:true}).click();
  check('native reduced motion has no painted chat animation',await page.locator('.chat-column').evaluate(e=>e.getAnimations().every(a=>a.playState!=='running')));
  await page.getByRole('button',{name:'סגירת סביבת העבודה',exact:true}).click();
  await page.getByRole('button',{name:'פתיחת סביבת העבודה',exact:true}).click();
  await page.locator('.workbench-empty').getByRole('button',{name:'קבצים',exact:true}).click();
  for(const name of ['מסוף','תוצרים']){await page.getByRole('button',{name:'פתיחת לשונית',exact:true}).click();await page.getByRole('menuitem',{name,exact:true}).click();}
  check('three actual Windows workbench tabs keep separate owners',await page.locator('.workbench-tab').count()===3);
  await page.getByRole('button',{name:'סגירת סביבת העבודה',exact:true}).click();
  metrics.push({kind:'native idle process tree',...JSON.parse(execFileSync('pwsh',['-NoProfile','-File','scripts/measure_ux6_processes.ps1','-RootIds',String(launch.pid)],{windowsHide:true,encoding:'utf8'}))});
  check('no native JavaScript exceptions',errors.length===0);
  await fs.writeFile(path.join(output,'accessibility-tree.yaml'),await page.locator('body').ariaSnapshot());
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({checks,errors,metrics,geometry,webview:browser.version(),mode,executableHash:launch.sha256,scope:'Actual isolated Tauri/Rust/Core/Windows; measured HWND DPI only; deterministic model; no actual OAuth/audio/pickers/install; rAF is not compositor FPS'},null,2));
 }catch(e){await page.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});await fs.writeFile(path.join(output,'failure.json'),JSON.stringify({error:String(e),checks,errors,metrics,geometry},null,2));throw e;}
 finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
