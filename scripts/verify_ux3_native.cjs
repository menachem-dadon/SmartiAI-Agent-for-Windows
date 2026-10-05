// Run only against the separately launched, hidden UX-3 QA application with an
// isolated SMARTI_DATA_DIR and WebView2 CDP port. No IPC mocks or bearer access.
const { chromium } = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const {execFileSync}=require('node:child_process');
async function main() {
  const output=path.resolve(process.argv[3] || '.codex-local/ux-3/native-ui');await fs.mkdir(output,{recursive:true});
  const probe=String(await fs.readFile('.codex-local/ux-3/native-ui.pid','utf8')).trim();
  assert.match(probe,/^\d+$/,'isolated QA process ID');
  const probePath=String(execFileSync('pwsh',['-NoProfile','-Command',`(Get-Process -Id ${probe} -ErrorAction Stop).Path`],{windowsHide:true})).trim();
  assert.equal(path.win32.basename(probePath).toLowerCase(),'ux3-native.exe','isolated QA executable');
  const browser=await chromium.connectOverCDP(process.argv[2] || 'http://127.0.0.1:19445');
  const page=browser.contexts()[0].pages().find(p=>p.url().includes('localhost:1420'));
  assert.ok(page,'actual product WebView target');const errors=[],results=[];
  page.on('pageerror',e=>errors.push(e.message));
  const invoke=(cmd,args={})=>page.evaluate(({cmd,args})=>window.__TAURI_INTERNALS__.invoke(cmd,args),{cmd,args});
  const identifier=await invoke('plugin:app|identifier');
  if(identifier!=='ai.smarti.ux3native') {
    await browser.close();
    throw new Error('Refusing to change data or quit an application outside the isolated UX-3 QA identifier.');
  }
  const api=async(method,route,body)=>{const value=await invoke('core_api',{request:{method,path:route,body:body??null,idempotencyKey:method==='GET'?null:crypto.randomUUID()}});assert.ok(value.status>=200 && value.status<300,route+':'+value.status+':'+value.body.detail);return value.body.data;};
  const check=(name,value)=>{assert.ok(value,name);results.push(name);};
  try {
    await page.reload();
    let status; for(let attempt=0;attempt<100;attempt++){ status=await invoke('core_status'); if(status.state==='ready')break; await page.waitForTimeout(300); } assert.equal(status.state,'ready',JSON.stringify(status));
    const legal=await api('GET','/v2/management/legal');
    if(!legal.accepted){await page.getByRole('checkbox').check();await page.getByRole('button',{name:'אני מסכים',exact:true}).click();}
    await page.locator('.chat-column').waitFor({timeout:30000});
    await api('PATCH','/v2/settings',{values:{updates_auto_check:false}});
    const suffix=crypto.randomUUID().slice(0,6); const titleA='Native UX-3 A '+suffix, titleB='Native UX-3 B '+suffix, renamed='Native UX-3 renamed '+suffix;
    const first=(await api('POST','/v2/conversations',{title:titleA})).conversation;
    const second=(await api('POST','/v2/conversations',{title:titleB})).conversation;
    await api('POST',`/v2/conversations/${first.id}/runs`,{text:'native-first'});
    await api('POST',`/v2/conversations/${second.id}/runs`,{text:'native-second'});
    await page.reload();await page.locator('.chat-column').waitFor();
    const select=async title=>{if(!await page.locator('.conversation-list').isVisible())await page.getByRole('button',{name:'פתיחת תפריט הצד'}).click();await page.locator('.conversation-select').filter({hasText:title}).click();await page.waitForTimeout(400);};
    await select(titleA);
    const area=page.getByRole('textbox',{name:'הודעה',exact:true});await area.fill('native UI submission');await page.getByRole('button',{name:'שליחה',exact:true}).click();
    await page.getByText('deterministic:native UI submission',{exact:true}).waitFor({timeout:20000});
    check('real renderer to Rust to authenticated Core to stored response',(await api('GET',`/v2/conversations/${first.id}/messages?limit=48`)).messages.some(m=>m.content==='deterministic:native UI submission'));
    await area.fill('טיוטה בחלון הילידי');await page.locator('input[type=file]').setInputFiles({name:'native.txt',mimeType:'text/plain',buffer:Buffer.from('native attachment')});
    await page.getByRole('button',{name:'הסרת native.txt'}).waitFor();
    await select(titleB);await area.fill('טיוטה אחרת');await select(titleA);
    check('native draft and staged file owners',(await area.inputValue())==='טיוטה בחלון הילידי' && await page.getByRole('button',{name:'הסרת native.txt'}).isVisible());
    await page.reload();await page.locator('.chat-column').waitFor();await select(titleA);
    check('native WebView reload retains staged draft',(await area.inputValue())==='טיוטה בחלון הילידי' && await page.getByRole('button',{name:'הסרת native.txt'}).isVisible());
    const after=await invoke('core_status');check('reload preserves actual Core process',status.pid===after.pid && status.generation===after.generation);
    await page.getByRole('button',{name:'פרופיל בטיחות'}).click();await page.getByRole('menuitem',{name:'בטוח',exact:true}).click();
    await area.fill('native attachment submission'); await page.getByRole('button',{name:'שליחה',exact:true}).click();
    await page.getByText('deterministic:native attachment submission',{exact:true}).waitFor({timeout:20000});
    check('attachment registered and stored by actual Core',(await api('GET',`/v2/conversations/${first.id}/messages?limit=48`)).messages.some(m=>m.role==='user' && m.attachments?.some(a=>a.name?.endsWith('native.txt'))));
    check('native safety persists',(await api('GET','/v2/settings')).values.autonomy_mode==='locked_down');
    if(!await page.locator('.conversation-list').isVisible())await page.getByRole('button',{name:'פתיחת תפריט הצד'}).click();
    await page.locator('.conversation-row').filter({hasText:titleA}).hover();await page.getByRole('button',{name:'פעולות עבור '+titleA}).click();await page.getByRole('menuitem',{name:'שנה שם'}).click();
    const dialog=page.getByRole('dialog',{name:'שינוי שם שיחה'});await dialog.getByRole('textbox',{name:'שם חדש'}).fill(renamed);await dialog.getByRole('button',{name:'אישור'}).click();
    await dialog.waitFor({state:'detached'});check('native rename persists',(await api('GET','/v2/conversations?q=Native&limit=100')).items.some(c=>c.id===first.id && c.title===renamed));
    await invoke('desktop_focus_main');
    const devtools=await browser.contexts()[0].newCDPSession(page);
    await devtools.send('Emulation.clearDeviceMetricsOverride');
    await devtools.send('Network.setCacheDisabled',{cacheDisabled:true});
    const geometry=[];let probeWindowHandle;
    let currentTheme;
    for(const theme of ['light','dark'])for(const width of [360,500,1290,1380]){
      if(currentTheme!==theme){await api('PATCH','/v2/settings',{values:{ui_preferences:{theme_mode:theme}}});await page.reload({waitUntil:'networkidle'});await page.locator('.chat-column').waitFor();currentTheme=theme;}
      const windowArgs=probeWindowHandle?['-ProbeWindowHandle',String(probeWindowHandle)]:[];
      const resized=JSON.parse(String(execFileSync('pwsh',['-NoProfile','-File','scripts/resize_ux3_window.ps1','-ProbeProcessId',probe,'-Width',String(width),'-Height','900',...windowArgs],{windowsHide:true})));
      probeWindowHandle=resized.window;await page.waitForTimeout(600);
      await area.focus();
      const g=await page.evaluate(()=>{const box=node=>{const r=node.getBoundingClientRect();return {left:r.left,right:r.right,width:r.width,height:r.height,top:r.top,bottom:r.bottom};};const rect=s=>box(document.querySelector(s));const user=Array.from(document.querySelectorAll('.chat-message-row--user')).at(-1);return {viewport:innerWidth,scale:devicePixelRatio,composer:rect('.composer'),reading:rect('.message-list'),chat:rect('.chat-column'),primary:rect('.composer-primary'),attachment:rect('.composer-tool'),model:rect('.model-quick-pill summary'),policy:rect('.autonomy-quick-pill .sds-button'),toolbar:rect('.chat-toolbar-controls'),title:rect('.chat-toolbar h1'),bubble:box(user.querySelector('.sds-user-bubble')),footer:box(user.querySelector('.sds-message-actions')),textareaOutline:getComputedStyle(document.querySelector('.composer textarea')).outlineStyle,theme:document.querySelector('.chat-design').dataset.theme};});
      g.scrollbarGutter=await page.locator('.chat-stage').evaluate(node=>node.offsetWidth-node.clientWidth);
      check(`native ${theme}-${width} bounds: ${JSON.stringify(g)}`,Math.abs(g.viewport-width)<2 && g.composer.left>=g.chat.left-.5 && g.composer.right<=g.chat.right+.5 && g.primary.width>=40 && g.attachment.width>=40 && g.model.left<g.policy.left && g.model.left-g.primary.right<18 && g.attachment.left-g.policy.right<18 && g.toolbar.right<=g.title.left+.5 && Math.abs(g.footer.right-g.bubble.right)<.5 && g.footer.top>=g.bubble.bottom && g.textareaOutline==='none' && g.reading.left>=g.composer.left-.5 && g.reading.right<=g.composer.right+.5 && Math.abs(g.reading.width-g.composer.width)<=g.scrollbarGutter+1 && (width<1206 || (Math.abs(g.composer.width-697)<.5 && Math.abs(g.reading.width-697)<.5 && Math.abs(g.composer.left-g.reading.left)<.5)));geometry.push(g);
      await page.screenshot({path:path.join(output,`${theme}-${width}.png`)});
    }
    check('no native renderer runtime errors',errors.length===0);
    await fs.writeFile(path.join(output,'report.json'),JSON.stringify({ok:true,results,geometry,errors,webview:browser.version(),coreProcessPreserved:true,scope:'separate app identifier and isolated profile; initial hidden window shown without activation for native resize; actual Rust IPC; deterministic generation'},null,2));
    console.log(JSON.stringify({ok:true,checks:results.length,webview:browser.version()}));
  }catch(error){await page.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});const document=await page.evaluate(()=>({url:location.href,html:document.documentElement.outerHTML.slice(0,2500)})).catch(()=>null);await fs.writeFile(path.join(output,'failure.json'),JSON.stringify({results,errors,document,error:error.stack},null,2));throw error;}
  finally{await invoke('desktop_quit').catch(()=>{});await browser.close();}
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
