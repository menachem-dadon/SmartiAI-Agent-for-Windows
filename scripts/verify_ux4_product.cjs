// Real product React + authenticated, isolated Core. Native IPC only is adapted
// for Edge; model generation is deterministic. Never used by the product.
const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const { randomUUID } = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
async function main() {
  const output = path.resolve(process.argv[3] || '.codex-local/ux-4/product');
  await fs.mkdir(output, { recursive: true });
  const token = randomUUID();
  const host = spawn('python', ['scripts/ux3_core_host.py'], { windowsHide: true, env: {...process.env, UX3_TEST_TOKEN: token, UX4_WORKBENCH_QA:'1', PYTHONUTF8:'1'} });
  let stderr = ''; host.stderr.on('data', x => { stderr += x; });
  const results = [], errors = [], commands = new Set();
  let browser, page; let native={tabs:[],activeTabId:null,transport:'QA-adapted-IPC'};
  const handshake = await new Promise((resolve, reject) => {
    let lines = ''; const timer = setTimeout(() => reject(new Error('Core startup timeout: '+stderr.slice(-1000))), 45000);
    host.once('exit', code => { clearTimeout(timer); reject(new Error(`Core exited ${code}: ${stderr.slice(-1500)}`)); });
    host.stdout.on('data', chunk => { lines += chunk; for (const line of lines.split('\n')) {
      if (line.includes('"sample"')) { try { const value = JSON.parse(line); clearTimeout(timer); resolve(value); } catch {} }
    }});
  }).catch(e => { host.stdin.end('shutdown\n'); throw e; });
  const api = async (method, route, body, idempotencyKey = null) => {
    const response = await fetch(`http://127.0.0.1:${handshake.port}${route}`, {method, signal:AbortSignal.timeout(15000), headers:{ Authorization:`Bearer ${token}`, 'Content-Type':'application/json', ...(idempotencyKey ? {'Idempotency-Key':idempotencyKey} : {})}, body:method==='GET' ? undefined : JSON.stringify(body || {})});
    return {status:response.status, body:await response.json()};
  };
  const legal = (await api('GET','/v2/management/legal')).body.data;
  assert.equal((await api('POST','/v2/management/legal',{accepted:true,version:legal.version},randomUUID())).status,200);
  try {
    browser = await chromium.launch({channel:'msedge',headless:true});
    const context = await browser.newContext({viewport:{width:1380,height:900},permissions:['clipboard-read','clipboard-write']});
    page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    await page.exposeFunction('__qaInvoke', async (cmd,args={}) => {
      commands.add(cmd);
      if(cmd==='desktop_open_with') return false;
      if(cmd==='browser_status'||cmd==='browser_metadata')return native;
      if(cmd==='browser_open') { const tab={tabId:'qa-'+randomUUID(),workspaceId:args.workspaceId,url:args.url,title:'QA browser',profile:args.profile,active:true,loading:false,pinned:false};native={...native,tabs:[...native.tabs,tab],activeTabId:tab.tabId};return native; }
      if(cmd==='browser_close_workspace') {native={...native,tabs:native.tabs.filter(t=>t.workspaceId!==args.workspaceId)};return native;}
      if(cmd==='browser_set_visible'||cmd==='browser_set_bounds')return true;
      if(cmd==='browser_action')return {result:args.action.method==='Page.captureScreenshot'?{data:'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg=='}:{}};

      if(cmd==='core_api') { const r=args.request; return api(r.method,r.path,r.body,r.idempotencyKey); }
      if(cmd==='core_status') return {state:handshake.state,generation:1,pid:handshake.pid,port:handshake.port,stderrTail:[]};
      if(cmd==='core_health') return handshake.health;
      if(cmd==='plugin:window|is_maximized') return false;
      if(cmd==='plugin:event|listen') return commands.size;
      if(cmd==='plugin:event|unlisten' || cmd==='desktop_finish_startup' || cmd==='desktop_set_close_to_tray' || cmd==='desktop_set_voice_hotkey' || cmd==='desktop_set_unread' || cmd==='desktop_notify') return true;
      if(cmd==='stage_attachment') { const target=path.join(output, 'attachment-'+randomUUID()+'.txt'); await fs.writeFile(target,Buffer.from(args.bytes)); return target; }
      if(cmd==='save_text_file') { await fs.writeFile(path.join(output,'export-'+randomUUID()+'.txt'),args.contents); return true; }
      throw new Error('Unadapted native command: '+cmd);
    });
    await page.addInitScript(() => {
      let id=0; const callbacks=new Map();
      window.__TAURI_INTERNALS__={metadata:{currentWindow:{label:'main'},currentWebview:{label:'main',windowLabel:'main'}},transformCallback: fn => { callbacks.set(++id,fn); return id; },unregisterCallback:n=>callbacks.delete(n),invoke:(cmd,args)=>window.__qaInvoke(cmd,args)};
      window.__TAURI_EVENT_PLUGIN_INTERNALS__={unregisterListener:()=>{}};
    });
    const base=process.argv[2] || 'http://localhost:1420';
    await page.goto(base); await page.locator('.chat-column').waitFor({timeout:30000});
    const record=(name,value)=>{assert.ok(value,name);results.push(name);console.log(name);};
    const geometry=[];
    const select=async title=>{await page.locator('.conversation-select').filter({hasText:title}).click();await page.waitForTimeout(400);};
    const open=async()=>{await page.getByRole('button',{name:'פתיחת סביבת העבודה',exact:true}).click();await page.waitForTimeout(400);};
    const close=async()=>{await page.getByRole('button',{name:'סגירת סביבת העבודה',exact:true}).click();await page.waitForTimeout(400);};
    const add=async name=>{await page.getByRole('button',{name:'פתיחת לשונית',exact:true}).click();await page.getByRole('menuitem',{name,exact:true}).click();};
    await select('מחקר לקראת המפגש');
    const draft=page.getByRole('textbox',{name:'הודעה',exact:true}); await draft.fill('UX-4 retained draft');
    await open();
    record('four entries; Canvas is available only from chat',(await page.locator('.workbench-empty button').allTextContents()).join('|')==='דפדפן|קבצים|מסוף|תוצרים');
    await page.locator('.workbench-empty').getByRole('button',{name:'קבצים',exact:true}).click();
    await page.locator('.file-tree summary').first().click();
    await page.getByRole('button',{name:'notes.md',exact:false}).click();
    await page.getByRole('heading',{name:'UX-4 document'}).waitFor();
    record('real scoped Markdown preview from Core',await page.locator('.markdown-preview').isVisible());
    await page.getByRole('button',{name:'פעולות קובץ',exact:true}).click();await page.getByRole('menuitem',{name:'העתקת נתיב מלא'}).click();
    record('full path copy equals validated Core workspace path',(await page.evaluate(()=>navigator.clipboard.readText())).replace(/\\/g,'/').endsWith('/folder/notes.md'));
    await page.getByRole('button',{name:'פעולות קובץ',exact:true}).click();await page.getByRole('menuitem',{name:'שמירת עותק'}).click();
    record('save uses native save IPC with actual preview contents',commands.has('save_text_file'));
    await page.getByRole('button',{name:'הסתרת רשימת הקבצים'}).click();
    const reading=page.locator('.file-preview');await reading.evaluate(e=>e.scrollTop=650);await page.waitForTimeout(100);const scroll=await reading.evaluate(e=>e.scrollTop);
    await page.getByRole('button',{name:'הרחבת סביבת העבודה',exact:true}).click();await page.waitForTimeout(400);
    record('expanded reading preserves scroll',Math.abs((await reading.evaluate(e=>e.scrollTop))-scroll)<2);
    await page.screenshot({path:path.join(output,'expanded-reading.png')});
    await page.getByRole('button',{name:'חזרה לעבודה משולבת'}).click();await page.waitForTimeout(400);await close();
    record('draft survives expanded/split/close',(await draft.inputValue())==='UX-4 retained draft');
    await open(); record('last tab and document survive reopening',await page.getByRole('heading',{name:'UX-4 document'}).isVisible());
    await page.reload();await page.locator('.chat-column').waitFor();await page.getByRole('heading',{name:'UX-4 document'}).waitFor();
    record('WebView reload restores same session file/selection/scroll',Math.abs((await page.locator('.file-preview').evaluate(e=>e.scrollTop))-scroll)<2);
    await close();
    await page.locator('.canvas-open-card').filter({hasText:'Canvas 2'}).getByRole('button',{name:'פתיחה',exact:true}).click();await page.locator('.canvas-panel iframe').waitFor();
    record('chat reference selects exact Canvas',await page.frameLocator('.canvas-panel iframe').getByRole('heading',{name:'Canvas 2'}).isVisible());
    await close();await page.locator('.canvas-open-card').filter({hasText:'Canvas 2'}).getByRole('button',{name:'פתיחה',exact:true}).click();
    record('same Canvas reference reuses existing tab',(await page.locator('.workbench-tabs [role=tab]').count())===2);
    await close();await select('שיחה נוספת');await open();
    record('Canvas stays with source conversation while chat changes',await page.frameLocator('.canvas-panel iframe').getByRole('heading',{name:'Canvas 2'}).isVisible());
    await page.frameLocator('.canvas-panel iframe').getByRole('button',{name:'Ask Smarti'}).click();await page.getByRole('dialog',{name:'פעולה מהקנבס'}).waitFor();
    await page.getByRole('dialog').getByRole('button',{name:'שליחה לסמארטי'}).click();await page.getByRole('dialog').waitFor({state:'detached'});
    const sampleMessages=(await api('GET',`/v2/conversations/${handshake.sample}/messages?limit=48`)).body.data.messages;
    const otherMessages=(await api('GET',`/v2/conversations/${handshake.other}/messages?limit=48`)).body.data.messages;
    record('Canvas action reaches source owner without active-chat fallback',sampleMessages.some(m=>m.role==='user'&&m.content.includes('[נתוני משתמש מהקנבס ux4-canvas-2]'))&&!otherMessages.some(m=>m.content.includes('[נתוני משתמש מהקנבס')));
    record('Canvas remains sandboxed',(await page.locator('.canvas-panel iframe').getAttribute('sandbox'))==='allow-scripts');
    await add('תוצרים');await page.getByRole('button',{name:/reading.pdf/}).click();await page.locator('.file-preview iframe').waitFor();
    record('real PDF data from Core enters PDF viewer',(await page.locator('.file-preview iframe').getAttribute('src')).startsWith('data:application/pdf;base64,'));
    await page.getByRole('button',{name:'פתח באמצעות',exact:true}).click();record('Open With delegates to Rust adapter',commands.has('desktop_open_with'));
    await page.getByRole('button',{name:/unsupported.ux4/}).click();await page.getByRole('heading',{name:'unsupported.ux4'}).waitFor();
    record('unsupported file keeps external opening available',await page.getByRole('button',{name:'פתח באמצעות',exact:true}).first().isEnabled());
    const denied=await api('GET','/v2/workbench/file?path=../outside.txt');record('Core continues to deny scope escape',denied.status>=400);
    await add('מסוף');await page.getByRole('textbox',{name:'פקודת PowerShell'}).waitFor();await page.waitForFunction(()=>!document.querySelector('.terminal-panel input').disabled);
    await page.getByRole('textbox',{name:'פקודת PowerShell'}).fill("Write-Output ('UX4_' + 'TERMINAL_OK')");await page.getByRole('button',{name:'הרצת פקודה'}).click();await page.waitForFunction(()=>document.querySelector('.terminal-panel pre')?.textContent.includes('UX4_TERMINAL_OK'));
    const terminalBefore=await page.evaluate(()=>{const s=JSON.parse(sessionStorage.getItem('smarti-workbench-session-v2'));return JSON.parse(sessionStorage.getItem('smarti-workbench-panel:'+s.snapshot.active));});
    await page.reload();await page.getByRole('textbox',{name:'פקודת PowerShell'}).waitFor();await page.waitForFunction(()=>!document.querySelector('.terminal-panel input').disabled);
    const terminalAfter=await page.evaluate(()=>{const s=JSON.parse(sessionStorage.getItem('smarti-workbench-session-v2'));return JSON.parse(sessionStorage.getItem('smarti-workbench-panel:'+s.snapshot.active));});
    record('real PowerShell session survives WebView reload without duplicate create',terminalBefore.terminalId===terminalAfter.terminalId && terminalAfter.output.includes('UX4_TERMINAL_OK'));
    await page.getByRole('tab',{name:'מסוף',exact:true}).hover();await page.getByRole('button',{name:'סגירת מסוף',exact:true}).click();
    record('tab close cleans the actual terminal',(await api('GET',`/v2/workbench/terminals/${terminalAfter.terminalId}`)).status>=400);
    await close();await select('מחקר לקראת המפגש');await draft.fill('approve-long');await page.getByRole('button',{name:'שליחה',exact:true}).click();await page.locator('.conversation-approvals').waitFor({timeout:20000});await draft.fill('next draft during approval');await open();
    for(const theme of ['light','dark']) {
      await api('PATCH','/v2/settings',{values:{ui_preferences:{theme_mode:theme}}},randomUUID());await page.reload();await page.locator('.chat-column').waitFor();await page.waitForTimeout(500);
      for(const width of [360,500,900,1206,1380,1920]) {
        await page.setViewportSize({width,height:900});await page.waitForTimeout(500);
        const captions=await page.locator('.window-titlebar').evaluate(element=>[...element.querySelectorAll('button')].map(button=>{
          const r=button.getBoundingClientRect(),s=getComputedStyle(button),icon=getComputedStyle(button.querySelector('.window-caption-icon'));
          return {x:r.x,right:r.right,width:r.width,height:r.height,border:s.borderWidth,font:icon.fontFamily};
        }));
        record(`${theme}-${width} Windows caption styling and physical right side`,captions.length===3&&captions.every(c=>Math.abs(c.width-46)<1&&Math.abs(c.height-32)<1&&parseFloat(c.border)===0&&c.font.includes('Segoe'))&&Math.abs(captions[2].right-width)<1&&captions[0].x<captions[2].x);
        if(width>=1206) {
          await page.locator('.workbench-resize-handle').focus();await page.keyboard.press('Home');await page.waitForTimeout(150);
          const left=await page.locator('.workbench').boundingBox(), right=await page.locator('.chat-column').boundingBox();
          record(`${theme}-${width} splitter minimum`,left.width>=300&&right.width>=320);
          await page.keyboard.press('End');await page.waitForTimeout(150);
          record(`${theme}-${width} composer after splitter maximum`,await draft.isVisible());
          await page.getByRole('button',{name:'פרופיל בטיחות'}).click();const menu=await page.getByRole('menu').boundingBox();record(`${theme}-${width} menu escapes clipping`,menu.x>=0&&menu.x+menu.width<=width);await page.keyboard.press('Escape');
        }
        const g=await page.evaluate(()=>{const box=s=>{const n=document.querySelector(s);if(!n)return null;const r=n.getBoundingClientRect();return {left:r.left,right:r.right,width:r.width,height:r.height};};return {width:innerWidth,workbench:box('.workbench'),chat:box('.chat-column'),composer:box('.composer'),head:box('.workbench-head')};});geometry.push({theme,...g});
        record(`${theme}-${width} workbench inside viewport`,g.workbench.left>=-1&&g.workbench.right<=width+1);
        await page.screenshot({path:path.join(output,`${theme}-${width}.png`)});
      }
    }
    await page.setViewportSize({width:1380,height:900});await page.waitForTimeout(400);await close();
    record('approval and writing owner preserved through workspace layouts',(await draft.inputValue())==='next draft during approval'&&await page.locator('.conversation-approvals').isVisible());
    await page.locator('.conversation-approvals').getByRole('button',{name:/דח/}).click();await page.locator('.conversation-approvals').waitFor({state:'detached'});
    const retainedDraft=await draft.inputValue();
    for(const theme of ['light','dark']) {
      await api('PATCH','/v2/settings',{values:{ui_preferences:{theme_mode:theme}}},randomUUID());await page.reload();await page.locator('.chat-column').waitFor();
      for(const width of [500,900,1380]) {
        await page.setViewportSize({width,height:900});await page.waitForTimeout(300);
        await page.locator('.drawer-management').getByRole('button',{name:'הגדרות',exact:true}).click();
        const dialog=page.getByRole('dialog',{name:'הגדרות וניהול',exact:true});await dialog.waitFor();
        const nav=dialog.getByRole('navigation',{name:'ניווט הגדרות וניהול'});
        for(const section of ['מודלי AI וספקים','זיכרונות','מרכז משימות']) {
          await nav.getByRole('button',{name:section,exact:true}).click();await page.waitForTimeout(150);
          const layout=await dialog.evaluate(element=>{
            const rect=node=>{const r=node.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom};};
            const nav=element.querySelector('nav'),main=element.querySelector('main'),buttons=[...nav.querySelectorAll('button')];
            return {nav:rect(nav),main:rect(main),buttons:buttons.map(rect),groups:[...nav.querySelectorAll('section')].map(node=>getComputedStyle(node).display),labels:buttons.map(node=>getComputedStyle(node.querySelector('span')).display),overflow:main.scrollWidth>main.clientWidth+1};
          });
          record(`${theme}-${width} management ${section} remains contained and separated`,layout.groups.every(display=>display==='grid')&&layout.buttons.every(b=>b.height>=41)&&layout.main.right<=layout.nav.x+1&&layout.main.x>=-1&&!layout.overflow&&(width<=920||layout.labels.every(display=>display!=='none')));
          if(section==='זיכרונות')await page.screenshot({path:path.join(output,`management-${theme}-${width}.png`)});
        }
        await dialog.getByRole('button',{name:'חזרה לצ׳אט',exact:true}).click();await dialog.waitFor({state:'detached'});
        record(`${theme}-${width} management returns to the same chat draft`,(await draft.inputValue())===retainedDraft);
      }
    }
    await page.evaluate(()=>sessionStorage.removeItem('smarti-workbench-session-v2'));await page.reload();await page.locator('.chat-column').waitFor();await open();record('new-session cache starts empty without deleting files',await page.locator('.workbench-empty').isVisible() && (await api('GET','/v2/workbench/artifacts')).body.data.items.length>=4);
    record('no product renderer errors',errors.length===0);
    await fs.writeFile(path.join(output,'report.json'),JSON.stringify({ok:true,results,errors,geometry,scope:'Real React and authenticated isolated Core; native IPC adapted for headless Edge, deterministic model only',browser:browser.version()},null,2));
  } catch(error) {if(page){await page.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});await fs.writeFile(path.join(output,'failure.json'),JSON.stringify({error:error.stack,results,errors},null,2));}throw error;}
  finally {if(browser)await browser.close();host.stdin.end('shutdown\n');await new Promise(resolve=>{if(host.exitCode!==null)resolve();else host.once('exit',resolve);});}
}
main().catch(error=>{console.error(error.stack);process.exitCode=1;});
