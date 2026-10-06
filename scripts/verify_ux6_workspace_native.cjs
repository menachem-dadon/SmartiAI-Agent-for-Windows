// Actual product WebView2, Rust IPC and isolated Core. Guard identity before writes.
const {chromium}=require('playwright');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process'),{randomUUID}=require('node:crypto'),http=require('node:http');
async function main(){
 const output=path.resolve(process.argv[3]||'.codex-local/ux-6/final/native-workspace');await fs.mkdir(output,{recursive:true});
 const launch=JSON.parse(await fs.readFile('.codex-local/ux-6/native-built-launch.json','utf8'));
 assert.notEqual(launch.deterministic,false,'Refusing automation on the live-provider user trial');
 const probe=String(launch.pid);assert.match(probe,/^\d+$/);
 const executable=String(execFileSync('pwsh',['-NoProfile','-Command',`(Get-Process -Id ${probe}).Path`],{windowsHide:true})).trim();
 assert.equal(path.win32.basename(executable).toLowerCase(),'ux6-built.exe');
 const browser=await chromium.connectOverCDP(process.argv[2]||'http://127.0.0.1:19467');
 const page=browser.contexts()[0].pages().find(p=>p.url().includes('tauri.localhost'));assert.ok(page);
 const invoke=(cmd,args={})=>page.evaluate(({cmd,args})=>window.__TAURI_INTERNALS__.invoke(cmd,args),{cmd,args});
 assert.equal(await invoke('plugin:app|identifier'),'ai.smarti.ux6built');
 const api=async(method,route,body)=>{const r=await invoke('core_api',{request:{method,path:route,body:body??null,idempotencyKey:method==='GET'?null:randomUUID()}});assert.ok(r.status>=200&&r.status<300,route+': '+r.status+' '+r.body.detail);return r.body.data;};
 const results=[],errors=[],geometry=[],nativeCalls=[];page.on('pageerror',e=>errors.push(e.message));
 const check=(name,condition)=>{assert.ok(condition,name);results.push(name);console.log(name);};
 const server=http.createServer((req,res)=>{res.setHeader('Content-Type','text/html; charset=utf-8');res.end('<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1"><title>UX-6 native fixture</title><h1>Native target</h1><p>Local scoped QA</p>');});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const url=`http://127.0.0.1:${server.address().port}/`;
 try{
  await page.evaluate(()=>sessionStorage.removeItem('smarti-workbench-session-v2'));await page.reload();let status;for(let n=0;n<100;n++){status=await invoke('core_status');if(status.state==='ready')break;await page.waitForTimeout(250);}assert.equal(status.state,'ready');
  const legal=await api('GET','/v2/management/legal');if(!legal.accepted){await page.getByRole('checkbox').check();await page.getByRole('button',{name:'אני מסכים',exact:true}).click();}
  await page.locator('.chat-column').waitFor();await api('PATCH','/v2/settings',{values:{updates_auto_check:false}});
  await invoke('desktop_focus_main');
  execFileSync('pwsh',['-NoProfile','-File','scripts/resize_ux6_window.ps1','-Mode','built','-ProbeProcessId',probe,'-Width','1380','-Height','900'],{windowsHide:true});await page.waitForTimeout(600);
  const root=path.join(launch.data,'workbench');assert.ok(root.startsWith(launch.data+path.sep));await fs.mkdir(root,{recursive:true});
  await fs.writeFile(path.join(root,'native.md'),'# Native UX-6\n\n'+Array.from({length:180},(_,n)=>'Line '+n).join('\n\n'));
  await fs.writeFile(path.join(root,'native.ux4'),'Isolated Windows Open With fixture');
  await api('PATCH','/v2/workbench/root',{path:root});
  const title='UX-6 native '+randomUUID().slice(0,6), first=(await api('POST','/v2/conversations',{title})).conversation;
  await api('POST',`/v2/conversations/${first.id}/runs`,{text:'native-workspace'});await page.reload();await page.locator('.chat-column').waitFor();
  await page.locator('.conversation-select').filter({hasText:title}).click();await page.waitForTimeout(300);
  const draft=page.getByRole('textbox',{name:'הודעה',exact:true});await draft.fill('Native retained draft');
  await page.getByRole('button',{name:'פתיחת סביבת העבודה',exact:true}).click();await page.locator('.workbench-empty').getByRole('button',{name:'קבצים',exact:true}).click();
  await page.getByRole('button',{name:'native.md',exact:false}).click();await page.getByRole('heading',{name:'Native UX-6'}).waitFor();
  check('native scoped file preview uses actual Rust/Core',await page.locator('.markdown-preview').isVisible());
  await page.locator('.file-preview').evaluate(e=>e.scrollTop=500);await page.getByRole('button',{name:'הרחבת סביבת העבודה',exact:true}).click();await page.waitForTimeout(500);
  check('native expanded reading retains scroll',(await page.locator('.file-preview').evaluate(e=>e.scrollTop))===500);
  await page.screenshot({path:path.join(output,'expanded.png')});await page.getByRole('button',{name:'חזרה לעבודה משולבת'}).click();await page.waitForTimeout(500);
  await page.getByRole('button',{name:'native.ux4',exact:false}).click();
  if(!process.argv.includes('--skip-open-with')) {
  // Legacy HWND probe only. Modern composited pickers can be visible without a
  // discoverable dialog window; in that case collect separate human acceptance.
  await page.evaluate(()=>{window.__ux4OpenWith={pending:true};});
  await page.evaluate(()=>{void window.__TAURI_INTERNALS__.invoke('desktop_open_with',{path:'native.ux4'}).then(value=>window.__ux4OpenWith={value},error=>window.__ux4OpenWith={error:String(error)});});
  let dialogs=[];for(let n=0;n<30;n++){dialogs=JSON.parse(String(execFileSync('pwsh',['-NoProfile','-File','scripts/ux4_dialog_probe.ps1','-ProbeProcessId',probe],{windowsHide:true})));if(dialogs.some(d=>d.title!=='SmartiAI'&&d.className==='#32770'))break;await page.waitForTimeout(250);}
  const popup=dialogs.find(d=>d.title!=='SmartiAI'&&d.className==='#32770');
  await fs.writeFile(path.join(output,'open-with-dialog.json'),JSON.stringify({dialogs,pending:await page.evaluate(()=>window.__ux4OpenWith)},null,2));
  assert.ok(popup,'No discoverable legacy Open With dialog; modern overlay display/cancel needs separate human evidence');
  check('actual SHOpenWithDialog appears with verified QA window owner',popup.owner!==0);
  execFileSync('pwsh',['-NoProfile','-File','scripts/ux4_dialog_probe.ps1','-ProbeProcessId',probe,'-CancelHandle',String(popup.handle)],{windowsHide:true});
  await page.waitForFunction(()=>!window.__ux4OpenWith.pending);check('native cancel returns false without restarting Core',await page.evaluate(()=>window.__ux4OpenWith.value===false));
  const after=await invoke('core_status');check('Open With preserves Core process',status.pid===after.pid&&status.generation===after.generation);
  }
  const add=async name=>{await page.getByRole('button',{name:'פתיחת לשונית',exact:true}).click();await page.getByRole('menuitem',{name,exact:true}).click();};
  await add('מסוף');await page.waitForFunction(()=>!document.querySelector('.terminal-panel input')?.disabled);
  await page.getByRole('textbox',{name:'פקודת PowerShell'}).fill("Write-Output ('NATIVE_UX6_' + 'OK')");await page.getByRole('button',{name:'הרצת פקודה'}).click();await page.waitForFunction(()=>document.querySelector('.terminal-panel pre')?.textContent.includes('NATIVE_UX6_OK'));
  const terminal=await page.evaluate(()=>{const s=JSON.parse(sessionStorage.getItem('smarti-workbench-session-v2'));return JSON.parse(sessionStorage.getItem('smarti-workbench-panel:'+s.snapshot.active)).terminalId;});
  await page.reload();await page.getByRole('textbox',{name:'פקודת PowerShell'}).waitFor();check('native reload retains terminal output',await page.locator('.terminal-panel pre').evaluate(e=>e.textContent.includes('NATIVE_UX6_OK')));
  await page.getByRole('tab',{name:'מסוף',exact:true}).hover();await page.getByRole('button',{name:'סגירת מסוף',exact:true}).click();await page.getByRole('tab',{name:'מסוף',exact:true}).waitFor({state:'detached'});
  const gone=await invoke('core_api',{request:{method:'GET',path:`/v2/workbench/terminals/${terminal}`,body:null,idempotencyKey:null}});check('native tab close actually deletes PowerShell session',gone.status>=400&&gone.body.detail==='terminal_session_not_found');
  await add('דפדפן');await page.waitForTimeout(1200);
  let snap=await invoke('browser_status');const owner=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('smarti-workbench-session-v2')).snapshot.active);const tab=snap.tabs.find(t=>t.workspaceId===owner);assert.ok(tab,'visible browser owner');
  await invoke('browser_navigate',{tabId:tab.tabId,url});await page.waitForTimeout(900);
  const cdp=async(tabId,method,params={})=>invoke('browser_action',{action:{requestId:randomUUID(),tabId,method,params}});
  const target=await cdp(tab.tabId,'Runtime.evaluate',{expression:'document.title',returnByValue:true});check('same native visible browser target answers CDP',target.result.result.value==='UX-6 native fixture');
  await invoke('desktop_focus_main');check('native main window remains addressable with browser children',true);
  const image=await cdp(tab.tabId,'Page.captureScreenshot',{format:'png'});await fs.writeFile(path.join(output,'native-page.png'),Buffer.from(image.result.data,'base64'));check('real native screenshot contains page pixels',image.result.data.length>1000);
  const background=await invoke('browser_open',{workspaceId:'ux4-background',profile:'guest',url});const backgroundTab=background.tabs.find(t=>t.workspaceId==='ux4-background');
  await page.waitForTimeout(500);
  await cdp(tab.tabId,'Runtime.evaluate',{expression:"localStorage.setItem('ux4-owner','persistent')",returnByValue:true});
  const guest=await cdp(backgroundTab.tabId,'Runtime.evaluate',{expression:"localStorage.getItem('ux4-owner')",returnByValue:true});check('native Guest storage is isolated from persistent profile',guest.result.result.value===null);
  await invoke('browser_activate',{tabId:tab.tabId});await page.waitForTimeout(500);
  let handle;for(const theme of ['light','dark'])for(const width of [360,500,1380]){
   await api('PATCH','/v2/settings',{values:{ui_preferences:{theme_mode:theme}}});await page.reload();await page.locator('.embedded-browser').waitFor();
   const args=handle?['-ProbeWindowHandle',String(handle)]:[];
   const resized=JSON.parse(String(execFileSync('pwsh',['-NoProfile','-File','scripts/resize_ux6_window.ps1','-Mode','built','-ProbeProcessId',probe,'-Width',String(width),'-Height','900',...args],{windowsHide:true})));handle=resized.window;await page.waitForTimeout(1000);
   const g=await page.evaluate(()=>{const box=s=>{const r=document.querySelector(s).getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right};};return {viewport:innerWidth,scale:devicePixelRatio,workbench:box('.workbench'),native:box('.browser-viewport'),composer:box('.composer')};});
   check(`native ${theme}-${width} viewport and workbench bounds`,Math.abs(g.viewport-width)<2&&g.workbench.x>=0&&g.workbench.right<=width+1);
   const metrics=await cdp(tab.tabId,'Runtime.evaluate',{expression:'({width:innerWidth,height:innerHeight})',returnByValue:true});
   check(`native ${theme}-${width} child WebView agrees with final DOM bounds`,Math.abs(metrics.result.result.value.width-Math.round(g.native.width))<=2&&Math.abs(metrics.result.result.value.height-Math.round(g.native.height))<=2);
   geometry.push({theme,width,...g,resized,child:metrics.result.result.value});await page.screenshot({path:path.join(output,`${theme}-${width}.png`)});
  }
  await page.getByRole('button',{name:'הרחבת סביבת העבודה',exact:true}).click();await page.waitForTimeout(900);
  const expanded=await page.locator('.browser-viewport').boundingBox(),nativeExpanded=await cdp(tab.tabId,'Runtime.evaluate',{expression:'({width:innerWidth,height:innerHeight})',returnByValue:true});
  check('native expanded child agrees with actual expanded bounds',Math.abs(nativeExpanded.result.result.value.width-Math.round(expanded.width))<=2&&Math.abs(nativeExpanded.result.result.value.height-Math.round(expanded.height))<=2);nativeCalls.push({phase:'expansion',dom:expanded,child:nativeExpanded.result.result.value});
  await page.getByRole('button',{name:'חזרה לעבודה משולבת'}).click();await page.waitForTimeout(900);
  await page.evaluate(async()=>{for(let n=0;n<12;n++){const label=n%2?'פתיחת סביבת העבודה':'סגירת סביבת העבודה';const button=[...document.querySelectorAll('button')].find(e=>e.getAttribute('aria-label')===label);if(!button)throw Error('Missing motion control');button.click();await new Promise(r=>setTimeout(r,40));}});
  await page.emulateMedia({reducedMotion:'reduce'});await page.waitForTimeout(200);
  const final=await page.locator('.browser-viewport').boundingBox(),reducedChild=await cdp(tab.tabId,'Runtime.evaluate',{expression:'({width:innerWidth,height:innerHeight})',returnByValue:true});
  check('native mid-transition reversal and live reduce retain exact browser owner/bounds',Math.abs(reducedChild.result.result.value.width-Math.round(final.width))<=2&&Math.abs(reducedChild.result.result.value.height-Math.round(final.height))<=2&&(await invoke('browser_status')).tabs.some(t=>t.tabId===tab.tabId&&t.workspaceId===owner));
  check('live reduce cancels chat painted animation in actual WebView',await page.locator('.chat-column').evaluate(e=>e.getAnimations().every(a=>a.playState!=='running')));
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.getByRole('tab',{name:'דפדפן',exact:true}).hover();await page.getByRole('button',{name:'סגירת דפדפן',exact:true}).click();await page.getByRole('tab',{name:'דפדפן',exact:true}).waitFor({state:'detached'});
  snap=await invoke('browser_status');check('closing UI owner preserves unrelated background target',!snap.tabs.some(t=>t.workspaceId===owner)&&snap.tabs.some(t=>t.tabId===backgroundTab.tabId));
  await invoke('browser_close_workspace',{workspaceId:'ux4-background'});
  await page.getByRole('button',{name:'סגירת סביבת העבודה',exact:true}).click();await page.waitForTimeout(500);check('native conversation draft survives all workspace operations',(await draft.inputValue())==='Native retained draft');
  check('zero native renderer errors',errors.length===0);
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({ok:true,results,errors,geometry,nativeCalls,webview:browser.version(),openWith:process.argv.includes('--skip-open-with')?'UNVERIFIED by this automation; modern-overlay human acceptance is recorded separately in ledger §34':'legacy HWND dialog verified',scope:'isolated identifier/data/keyring; actual Rust IPC, Core, PowerShell and WebView2; Windows DPI measured by HWND; no package or human chooser evidence'},null,2));
 }catch(error){await page.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});await fs.writeFile(path.join(output,'failure.json'),JSON.stringify({error:error.stack,results,errors},null,2));throw error;}
 finally{await new Promise(resolve=>{server.close(resolve);server.closeAllConnections();});await browser.close();}
}
main().catch(error=>{console.error(error.stack);process.exitCode=1;});
