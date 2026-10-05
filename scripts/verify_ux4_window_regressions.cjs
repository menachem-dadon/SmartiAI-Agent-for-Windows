// Actual QA Tauri window; never point this verifier at the personal app.
const {chromium}=require('playwright');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process'),{randomUUID}=require('node:crypto');
async function main(){
 const root=process.cwd(),output=path.resolve(process.argv[2]||'.codex-local/ux-4/regression-native');
 await fs.mkdir(output,{recursive:true});
 const launch=JSON.parse(await fs.readFile('.codex-local/ux-4/native-launch.json','utf8'));
 assert.equal(launch.identifier,'ai.smarti.ux4native');
 assert.equal(path.resolve(launch.executable),path.join(root,'desktop/src-tauri/target/debug/ux4-native.exe'));
 assert.ok(path.resolve(launch.data).startsWith(path.join(root,'.codex-local/ux-4/native-data-')));
 execFileSync('pwsh',['-NoProfile','-Command',"if(Get-Process -Name ux4-native -ErrorAction SilentlyContinue){throw 'Close the QA app before its placement regression test'}"],{windowsHide:true,stdio:'pipe'});
 const placement=path.join(launch.data,'tauri-desktop/data/window-placement.json');
 await fs.mkdir(path.dirname(placement),{recursive:true});
 await fs.copyFile(placement,path.join(output,'qa-placement-before.json')).catch(error=>{if(error.code!=='ENOENT')throw error;});
 // Reproduce the legacy maximized record from the report using QA data only.
 await fs.writeFile(placement,JSON.stringify({layout_version:1,x:-9,y:-9,width:1938,height:1038,maximized:true}));
 const results=[],geometry=[],errors=[];let browser,page,qaVerified=false;
 const check=(name,condition)=>{assert.ok(condition,name);results.push(name);console.log(name);};
 const restart=()=>execFileSync('pwsh',['-NoProfile','-File','scripts/restart_ux4_native.ps1'],{windowsHide:true,stdio:'ignore'});
 const connect=async()=>{
  for(let attempt=0;attempt<80;attempt++){
   try{
    browser=await chromium.connectOverCDP('http://127.0.0.1:19446');
    page=browser.contexts()[0].pages().find(p=>p.url().includes('localhost:1420'));
    if(!page){await browser.close();browser=null;throw Error('QA renderer has not loaded yet');}
    break;
   }
   catch(error){if(attempt===79)throw error;await new Promise(resolve=>setTimeout(resolve,250));}
  }
  page=browser.contexts()[0].pages().find(p=>p.url().includes('localhost:1420'));assert.ok(page);
  assert.equal(await page.evaluate(()=>window.__TAURI_INTERNALS__.invoke('plugin:app|identifier')),'ai.smarti.ux4native');
  qaVerified=true;
  page.on('pageerror',error=>errors.push(error.message));
  await page.evaluate(()=>window.__TAURI_INTERNALS__.invoke('desktop_focus_main'));
  await page.locator('.chat-column').waitFor({timeout:45000});await page.waitForTimeout(350);
 };
 const invoke=(command,args={})=>page.evaluate(({command,args})=>window.__TAURI_INTERNALS__.invoke(command,args),{command,args});
 const quit=async()=>{if(qaVerified&&page&&!page.isClosed())await invoke('desktop_quit').catch(()=>{});if(browser)await browser.close().catch(()=>{});browser=null;qaVerified=false;};
 const windowState=()=>page.evaluate(async()=>{
  const i=(c)=>window.__TAURI_INTERNALS__.invoke('plugin:window|'+c,{label:'main'});
  return {maximized:await i('is_maximized'),minimized:await i('is_minimized'),size:await i('outer_size'),monitor:await i('current_monitor'),scale:devicePixelRatio};
 });
 try{
  restart();await connect();const initial=await windowState();
  const area=initial.monitor.workArea.size,scale=initial.monitor.scaleFactor;
  const defaultDimension=(available,fraction,min)=>Math.min(Math.max(Math.round(available*fraction),min),Math.max(available-32,1));
  const expected={width:defaultDimension(area.width/scale,.84,720)*scale,height:defaultDimension(area.height/scale,.8,560)*scale};
  check('legacy maximized record starts in the normal default window',!initial.maximized&&Math.abs(initial.size.width-expected.width)<=2&&Math.abs(initial.size.height-expected.height)<=2);
  geometry.push({phase:'startup',...initial,expected});
  const normal=JSON.parse(await fs.readFile(placement,'utf8'));
  check('startup replaces legacy maximized placement with normal bounds',!normal.maximized&&normal.width===initial.size.width&&normal.height===initial.size.height);
  const session=await page.context().newCDPSession(page);await session.send('DOM.enable');await session.send('CSS.enable');
  const {root:document}=await session.send('DOM.getDocument');
  const {nodeIds}=await session.send('DOM.querySelectorAll',{nodeId:document.nodeId,selector:'.window-caption-icon'});
  const fonts=[];for(const nodeId of nodeIds)fonts.push((await session.send('CSS.getPlatformFontsForNode',{nodeId})).fonts);
  check('all caption glyphs render with actual Windows icon fonts',fonts.length===3&&fonts.every(list=>list.some(font=>font.glyphCount>0&&/Segoe (Fluent Icons|MDL2 Assets)/.test(font.familyName))));
  await page.locator('.window-titlebar').screenshot({path:path.join(output,'native-caption.png')});
  await page.getByRole('button',{name:'מזער',exact:true}).click();await page.waitForTimeout(300);
  check('actual caption minimize button minimizes the window',(await windowState()).minimized);
  await invoke('desktop_focus_main');await page.waitForTimeout(300);
  check('focus restores the minimized window',!(await windowState()).minimized);
  await page.getByRole('button',{name:'הגדל',exact:true}).click();await page.getByRole('button',{name:'שחזר',exact:true}).waitFor();await page.waitForTimeout(300);
  check('actual caption maximize button changes the native window',(await windowState()).maximized);
  check('maximizing preserves the saved normal window bounds',JSON.stringify(JSON.parse(await fs.readFile(placement,'utf8')))===JSON.stringify(normal));
  await page.getByRole('button',{name:'שחזר',exact:true}).click();await page.getByRole('button',{name:'הגדל',exact:true}).waitFor();await page.waitForTimeout(300);
  const restored=await windowState();check('actual restore button returns to normal bounds',!restored.maximized&&restored.size.width===initial.size.width&&restored.size.height===initial.size.height);
  await page.getByRole('button',{name:'הגדל',exact:true}).click();await page.getByRole('button',{name:'שחזר',exact:true}).waitFor();await quit();
  restart();await connect();const relaunched=await windowState();
  check('app quit while maximized still relaunches in the normal size',!relaunched.maximized&&relaunched.size.width===initial.size.width&&relaunched.size.height===initial.size.height);
  const draft=page.getByRole('textbox',{name:'הודעה',exact:true});await draft.fill('QA draft preserved through management');
  for(const theme of ['light','dark'])for(const width of [500,1380]){
   const patch=await invoke('core_api',{request:{method:'PATCH',path:'/v2/settings',body:{values:{ui_preferences:{theme_mode:theme}}},idempotencyKey:randomUUID()}});assert.equal(patch.status,200);
   await page.reload();await page.locator('.chat-column').waitFor();
   const latest=JSON.parse(await fs.readFile('.codex-local/ux-4/native-launch.json','utf8'));
   execFileSync('pwsh',['-NoProfile','-File','scripts/resize_ux4_window.ps1','-ProbeProcessId',String(latest.pid),'-Width',String(width),'-Height','720'],{windowsHide:true});await page.waitForTimeout(500);
   await page.locator('.drawer-management').getByRole('button',{name:'הגדרות',exact:true}).click();
   const dialog=page.getByRole('dialog',{name:'הגדרות וניהול',exact:true}),nav=dialog.getByRole('navigation',{name:'ניווט הגדרות וניהול'});
   for(const section of ['מודלי AI וספקים','זיכרונות','מרכז משימות']){
    await nav.getByRole('button',{name:section,exact:true}).click();await page.waitForTimeout(200);
    const g=await dialog.evaluate(e=>{const n=e.querySelector('nav'),m=e.querySelector('main'),a=n.getBoundingClientRect(),b=m.getBoundingClientRect();return {width:innerWidth,nav:{x:a.x,width:a.width},main:{x:b.x,right:b.right},groups:[...n.querySelectorAll('section')].map(v=>getComputedStyle(v).display),overflow:m.scrollWidth>m.clientWidth+1,covered:e.contains(document.elementFromPoint(b.x+b.width/2,b.y+b.height/2))};});geometry.push({theme,width,section,...g});
    check(`native ${theme}-${width} ${section} covers chat and has an orderly right navigation`,g.covered&&g.groups.every(v=>v==='grid')&&g.main.right<=g.nav.x+1&&!g.overflow);
   }
   await page.screenshot({path:path.join(output,`management-${theme}-${width}.png`)});
   await dialog.getByRole('button',{name:'חזרה לצ׳אט',exact:true}).click();await dialog.waitFor({state:'detached'});
   check(`native ${theme}-${width} management returns to the same draft`,await draft.inputValue()==='QA draft preserved through management');
  }
  check('zero native renderer errors',errors.length===0);
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({ok:true,results,geometry,errors,fonts,webview:browser.version(),scope:'QA identifier/data/keyring only; actual native window actions and app relaunch; Windows DPI 125%'},null,2));
 }catch(error){if(page)await page.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});await fs.writeFile(path.join(output,'failure.json'),JSON.stringify({error:error.stack,results,errors},null,2));throw error;}
 finally{if(browser)await quit();}
}
main().catch(error=>{console.error(error.stack);process.exitCode=1;});
