// Real product React + authenticated, isolated Core. Native IPC only is adapted
// for Edge; model generation is deterministic. Never used by the product.
const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const { randomUUID } = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
async function main() {
  const output = path.resolve(process.argv[3] || '.codex-local/ux-3/product');
  await fs.mkdir(output, { recursive: true });
  const token = randomUUID();
  const host = spawn('python', ['scripts/ux3_core_host.py'], { windowsHide: true, env: {...process.env, UX3_TEST_TOKEN: token, PYTHONUTF8:'1'} });
  let stderr = ''; host.stderr.on('data', x => { stderr += x; });
  const results = [], errors = [], commands = new Set();
  let browser, page;
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
    const references={};
    if(process.argv[4] && !/^https?:\/\//.test(process.argv[4])) {
      const saved=JSON.parse(await fs.readFile(process.argv[4],'utf8'));
      Object.assign(references,saved.references || saved);
      assert.ok(references.light && references.dark,'saved frozen v7 theme references');
    } else if(process.argv[4]) {
      const reference=await context.newPage();
      for(const theme of ['light','dark']) {
        await reference.goto(`${process.argv[4]}/ux-1.html?v=7&theme=${theme}`,{waitUntil:'networkidle'});
        await reference.locator('.ux-prototype').waitFor();
        references[theme]=await reference.evaluate(()=>{const style=s=>{const c=getComputedStyle(document.querySelector(s));return {background:c.backgroundColor,border:c.borderTop,padding:c.padding,borderRadius:c.borderRadius};};return {chat:style('.ux-chat'),bubble:style('.ux-user .chat-message--user'),process:style('.agent-process>summary'),tool:style('.agent-tool-row')};});
        await reference.screenshot({path:path.join(output,`reference-${theme}.png`)});
      }
      await reference.close();
    }
    const select=async title=>{await page.locator('.conversation-select').filter({hasText:title}).click(); await page.waitForTimeout(400);};
    const historyMenu=async title=>{const row=page.locator('.conversation-row').filter({hasText:title});await row.hover();await row.getByRole('button',{name:'פעולות עבור '+title,exact:true}).click();};
    const text=page.getByRole('textbox',{name:'הודעה',exact:true});
    await select('מחקר לקראת המפגש');
    record('latest messages from real Core',await page.getByText('תוכנית העבודה',{exact:true}).isVisible());
    await text.fill('טיוטה A Mixed Hebrew / English');
    await page.locator('input[type=file]').setInputFiles({name:'qa.txt',mimeType:'text/plain',buffer:Buffer.from('isolated attachment')});
    await page.getByRole('button',{name:'הסרת qa.txt'}).waitFor();
    await select('שיחה נוספת'); await text.fill('טיוטה B');
    await select('מחקר לקראת המפגש');
    record('draft and attachment per conversation',(await text.inputValue()).startsWith('טיוטה A') && await page.getByRole('button',{name:'הסרת qa.txt'}).isVisible());
    // Paging and persisted old reading position, without following new content.
    await page.locator('.chat-stage').evaluate(node=>{node.scrollTop=0;node.dispatchEvent(new Event('scroll'));});
    for(let paging=0;paging<8 && await page.getByRole('button',{name:/טעינת.*הודעות קודמות/}).count();paging++) { await page.getByRole('button',{name:/טעינת.*הודעות קודמות/}).evaluate(node=>node.click()).catch(()=>{}); await page.waitForTimeout(250); }
    await page.locator('.chat-stage').evaluate(node=>{node.scrollTop=0;node.dispatchEvent(new Event('scroll'));});
    await page.getByText('הודעה 0 — Hebrew and English, שיחה ארוכה.',{exact:true}).waitFor({timeout:20000});
    await select('שיחה נוספת'); await select('מחקר לקראת המפגש');
    record('old reading position survives navigation',await page.locator('.chat-stage').evaluate(node=>node.scrollTop<20));
    await page.reload(); await page.locator('.chat-column').waitFor();
    await select('מחקר לקראת המפגש');
    await page.getByText('הודעה 0 — Hebrew and English, שיחה ארוכה.',{exact:true}).waitFor({timeout:20000});
    record('reload restores draft attachment and old messages',(await text.inputValue()).startsWith('טיוטה A') && await page.getByRole('button',{name:'הסרת qa.txt'}).isVisible());
    await page.getByRole('button',{name:'הסרת qa.txt'}).click();
    await text.fill('approve בדיקת אישור'); await page.getByRole('button',{name:'שליחה',exact:true}).click();
    await page.locator('.conversation-approvals').waitFor({timeout:20000});
    record('approval card has no nested outer scroll and normal prompt needs none',await page.locator('.conversation-approvals').evaluate(card=>{const p=card.querySelector('pre'),s=getComputedStyle(card);return s.overflowY==='visible' && p.scrollHeight<=p.clientHeight+1 && getComputedStyle(p).textAlign==='right' && !p.textContent.includes('\n\n');}));
    record('approval actions physically left',await page.locator('.conversation-approval footer').evaluate(f=>{const a=f.querySelector('button').getBoundingClientRect(),r=f.getBoundingClientRect();return a.right<r.left+r.width/2;}));
    await page.screenshot({path:path.join(output,'approval-normal.png')});
    await page.locator('.agent-process').last().evaluate(node=>{node.dataset.qaIdentity='retained';node.open=true;});
    await text.fill('טיוטה בזמן ריצה'); record('writing during approval',!await text.isDisabled());
    await page.getByRole('button',{name:'אשר',exact:true}).click();
    await page.getByText('הפעולה אושרה',{exact:true}).waitFor({timeout:20000});
    record('approval continues same process',await page.locator('[data-qa-identity=retained]').count()===1);
    record('run does not consume next draft',(await text.inputValue())==='טיוטה בזמן ריצה');
    await text.fill('wait ביטול'); await page.getByRole('button',{name:'שליחה',exact:true}).click();
    await page.getByRole('button',{name:'עצירה',exact:true}).waitFor();
    record('stop glyph filled',await page.locator('.composer-primary [data-icon=stop]').getAttribute('fill')==='currentColor');
    await select('שיחה נוספת'); record('other conversation keeps draft',(await text.inputValue())==='טיוטה B');
    await select('מחקר לקראת המפגש'); await page.getByRole('button',{name:'עצירה',exact:true}).click();
    await page.getByRole('button',{name:'הכתבה קולית',exact:true}).waitFor({timeout:20000});results.push('actual run cancellation');
    await text.fill('fail ספק'); await page.getByRole('button',{name:'שליחה',exact:true}).click();
    await page.getByText(/הספק אינו זמין בבדיקת הכשל/).first().waitFor({timeout:20000});results.push('durable provider error');
    await text.fill('key בדיקת הפסקה'); await page.getByRole('button',{name:'שליחה',exact:true}).click();
    await page.locator('.chat-api-key').waitFor({timeout:20000});
    record('secret interruption outside storage',!(await page.evaluate(()=>JSON.stringify({...sessionStorage,...localStorage}))).includes('api_key'));
    await page.getByRole('button',{name:'ביטול',exact:true}).click();
    await page.locator('.chat-api-key').waitFor({state:'detached'});results.push('cancel missing key through actual run route');
    await page.getByRole('button',{name:'פרופיל בטיחות'}).click();await page.getByRole('menuitem',{name:'בטוח',exact:true}).click();
    record('global safety saved in Core',(await api('GET','/v2/settings')).body.data.values.autonomy_mode==='locked_down');
    const modelTrigger=page.getByLabel('בחירת מודל',{exact:true});await modelTrigger.click();await page.getByRole('dialog',{name:'מודלים מועדפים'}).waitFor();
    record('model selector without sparkles and icon-only settings',await modelTrigger.locator('[data-icon=spark]').count()===0 && await page.locator('.model-menu-settings').innerText()==='' && await page.locator('.model-menu-settings [data-icon=settings]').count()===1);
    record('all provider names physically right including English',await page.locator('.model-menu-providers .sds-hover-label').evaluateAll(nodes=>nodes.length>=2 && nodes.every(n=>getComputedStyle(n).textAlign==='right' && Math.abs(n.getBoundingClientRect().right-n.firstElementChild.getBoundingClientRect().right)<1)));
    await page.screenshot({path:path.join(output,'model-refinements.png')});
    record('provider physical right',await page.evaluate(()=>document.querySelector('.model-menu-providers').getBoundingClientRect().left>document.querySelector('.model-menu-models').getBoundingClientRect().left));
    await page.keyboard.press('Escape');record('model Escape restores focus',await modelTrigger.evaluate(node=>node===document.activeElement));
    if(await page.getByRole('switch',{name:'FastMode',exact:true}).count()) {
      await page.getByRole('switch',{name:'FastMode',exact:true}).check();
      await page.waitForTimeout(250);
      record('RTL FastMode and real persistence',(await api('GET','/v2/settings')).body.data.values.local_fast_mode_enabled===true && await page.evaluate(()=>{const thumb=document.querySelector('.sds-switch-thumb').getBoundingClientRect(),track=document.querySelector('.sds-switch-track').getBoundingClientRect();return thumb.left+thumb.width/2<track.left+track.width/2;}));
    }
    await historyMenu('מחקר לקראת המפגש'); await page.getByRole('menuitem',{name:'הצמד שיחה',exact:true}).click();
    await page.waitForTimeout(300);
    record('pin stored by Core',(await api('GET','/v2/conversations?q=&limit=100')).body.data.items.find(c=>c.id===handshake.sample).pinned===true);
    await historyMenu('מחקר לקראת המפגש'); await page.getByRole('menuitem',{name:'יצוא JSON',exact:true}).click();
    const exportDeadline=Date.now()+10000;
    while(!commands.has('save_text_file') && Date.now()<exportDeadline)await page.waitForTimeout(100);
    record('export uses save command',commands.has('save_text_file'));
    await historyMenu('שיחה נוספת');await page.getByRole('menuitem',{name:'מחק שיחה',exact:true}).click();
    const deletion=page.getByRole('dialog',{name:'מחיקת שיחה'});await deletion.waitFor();
    record('delete footer spaced and physically left',await deletion.evaluate(d=>{const f=d.querySelector('footer'),b=f.querySelector('button').getBoundingClientRect(),r=f.getBoundingClientRect();return parseFloat(getComputedStyle(f).marginTop)>=24 && b.right<r.left+r.width/2;}));
    record('delete focuses cancel',await deletion.getByRole('button',{name:'ביטול',exact:true}).evaluate(node=>node===document.activeElement));
    await deletion.getByRole('button',{name:'אישור',exact:true}).click();await deletion.waitFor({state:'detached'});
    record('delete removes only selected conversation',!(await api('GET','/v2/conversations?q=&limit=100')).body.data.items.some(c=>c.id===handshake.other));
    await page.getByRole('button',{name:'גלישת שורות קוד'}).click();record('code wrap available',await page.locator('.code-frame.is-wrapped').count()===1);
    const stored=page.locator('.chat-message-row').filter({hasText:'פעילות כלים שמורה'});
    await stored.locator('.agent-process,.agent-tool-group,.agent-tool-row').evaluateAll(nodes=>nodes.forEach(n=>n.open=true));
    record('16000-character input and output stay within tool and chat',await stored.evaluate(row=>{const chat=document.querySelector('.chat-stage');return chat.scrollWidth<=chat.clientWidth+1 && Array.from(row.querySelectorAll('.agent-tool-row pre')).every(p=>p.scrollWidth<=p.clientWidth+1 && p.textContent.length>16000 && getComputedStyle(p).whiteSpace==='pre-wrap');}));
    const longInput=stored.locator('.agent-tool-row pre').first();await longInput.hover();await page.mouse.wheel(0,180);await page.waitForTimeout(150);
    record('tool text actually scrolls internally',await longInput.evaluate(p=>p.scrollTop>0));
    await stored.scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,'long-tool.png')});
    const row=page.locator('.conversation-row').filter({hasText:'מחקר לקראת המפגש'});
    await text.focus();await page.mouse.move(10,10);
    const idleTitle=await row.locator('.conversation-select').boundingBox();
    record('history ellipsis hidden at rest',await row.locator('.history-actions').evaluate(n=>getComputedStyle(n).opacity==='0'));
    await row.hover();const hoverTitle=await row.locator('.conversation-select').boundingBox();
    record('history hover reveals ellipsis and frees title space at rest',idleTitle.width-hoverTitle.width>=35 && await row.locator('.history-actions').evaluate(n=>getComputedStyle(n).opacity==='1'));
    record('history row matches navigation height with a small gap',await row.evaluate(r=>{const nav=document.querySelector('.drawer-management button');const next=r.nextElementSibling;return r.getBoundingClientRect().height===40 && nav.getBoundingClientRect().height===40 && (!next || next.getBoundingClientRect().top-r.getBoundingClientRect().bottom>=2);}));
    await row.getByRole('button',{name:'פעולות עבור מחקר לקראת המפגש'}).click();
    record('history menu painted above sidebar',await page.getByRole('menu').evaluate(menu=>{const r=menu.getBoundingClientRect();return document.elementFromPoint(r.right-12,r.top+12)?.closest('[role=menu]')===menu && menu.closest('.sds-floating-layer')?.parentElement===document.body;}));
    await page.getByRole('menuitem',{name:'שנה שם'}).click();
    const rename=page.getByRole('dialog',{name:'שינוי שם שיחה'});await rename.waitFor();
    record('rename footer separated from field and physically left',await rename.evaluate(d=>{const i=d.querySelector('input').getBoundingClientRect(),f=d.querySelector('footer'),b=f.querySelector('button').getBoundingClientRect(),r=f.getBoundingClientRect();return r.top-i.bottom>=24 && b.right<r.left+r.width/2;}));
    await page.screenshot({path:path.join(output,'rename-spaced.png')});await rename.getByRole('button',{name:'ביטול'}).click();
    const brand=await page.locator('.drawer-brand').boundingBox();
    await page.getByRole('button',{name:'כיווץ תפריט הצד'}).click();
    const railBrand=await page.locator('.drawer-brand').boundingBox();
    record('same brand hit target in both sidebar modes',brand.x===railBrand.x && brand.y===railBrand.y && brand.width===40 && railBrand.width===40);
    const tasks=page.getByRole('button',{name:'משימות',exact:true});await tasks.hover();
    const tip=page.getByRole('tooltip');await tip.waitFor();
    record('rail tooltip compact and above sidebar',await tip.evaluate(t=>{const r=t.getBoundingClientRect();const original=t.style.pointerEvents;t.style.pointerEvents='auto';const painted=document.elementFromPoint(r.left+12,r.top+12)?.closest('[role=tooltip]')===t;t.style.pointerEvents=original;return r.width<100 && painted;}));
    await page.mouse.move(10,10);record('tooltip disappears immediately on leave',await tip.count()===0);
    const copyButton=page.locator('.message-actions button[aria-label="העתק"]').last();await copyButton.hover();record('message copy has no tooltip',await tip.count()===0 && await copyButton.getAttribute('aria-label')==='העתק');
    const speak=page.locator('.message-actions button[aria-label="הקרא בקול"]').last();await speak.hover();record('read aloud has no tooltip',await tip.count()===0);await page.mouse.move(10,10);
    await page.getByRole('button',{name:'פתיחת תפריט הצד'}).click();
    await text.fill('approve-long בדיקת טקסט ארוך');await page.getByRole('button',{name:'שליחה',exact:true}).click();await page.locator('.conversation-approvals').waitFor();
    record('very long approval scrolls only its text',await page.locator('.conversation-approvals').evaluate(card=>{const p=card.querySelector('pre');return getComputedStyle(card).overflowY==='visible' && p.scrollHeight>p.clientHeight && getComputedStyle(p).overflowY==='auto';}));
    await page.screenshot({path:path.join(output,'approval-long.png')});
    await page.setViewportSize({width:500,height:420});await page.waitForTimeout(300);
    record('short window keeps long approval in main scroll and composer visible',await page.evaluate(()=>{const f=document.querySelector('.chat-input-panel'),s=document.querySelector('.chat-stage').getBoundingClientRect(),c=document.querySelector('.composer').getBoundingClientRect(),a=document.querySelector('.conversation-approvals');return f.classList.contains('is-flowing') && getComputedStyle(a).overflowY==='visible' && c.top>=s.top && c.bottom<=s.bottom+1 && getComputedStyle(document.querySelector('.chat-composer-panel')).position==='sticky';}));
    await page.locator('.chat-stage').evaluate(s=>{s.scrollTop=s.scrollHeight;});await page.getByRole('button',{name:'דחה',exact:true}).click();await page.getByText('הפעולה נדחתה',{exact:true}).waitFor();
    record('approval can be read and resolved in short window',await page.locator('.conversation-approvals').count()===0);
    await page.setViewportSize({width:1380,height:900});await page.waitForTimeout(300);
    await text.fill('visual בדיקת תהליך');await page.getByRole('button',{name:'שליחה',exact:true}).click();
    const thinking=page.locator('.agent-initial-thinking .is-shimmering');await thinking.waitFor();
    record('thinking has moving shimmer',await thinking.evaluate(node=>{const s=getComputedStyle(node);return s.animationName==='chat-text-shimmer' && s.backgroundImage!=='none';}));
    await page.screenshot({path:path.join(output,'thinking-shimmer.png')});
    const visualProcess=page.locator('.agent-process').last();await visualProcess.waitFor();await visualProcess.evaluate(node=>node.open=true);
    const group=visualProcess.locator('.agent-tool-group');await group.waitFor();await group.evaluate(node=>node.open=true);
    const tool=group.locator('.agent-tool-row');await tool.evaluate(node=>node.open=true);
    const runningLabel=tool.locator('.is-shimmering');
    record('running tool label has shimmer',await runningLabel.evaluate(node=>getComputedStyle(node).animationName==='chat-text-shimmer'));
    const before=await runningLabel.evaluate(node=>getComputedStyle(node).backgroundPosition);
    await page.waitForTimeout(120);
    record('shimmer actually advances',before!==await runningLabel.evaluate(node=>getComputedStyle(node).backgroundPosition));
    await page.screenshot({path:path.join(output,'process-running.png')});
    await page.emulateMedia({reducedMotion:'reduce'});
    record('reduced motion keeps readable plain status',await runningLabel.evaluate(node=>{const s=getComputedStyle(node);return s.animationName==='none' && s.backgroundImage==='none' && s.webkitTextFillColor!=='rgba(0, 0, 0, 0)';}));
    await page.emulateMedia({reducedMotion:'no-preference',forcedColors:'active'});
    record('high contrast keeps readable status',await runningLabel.evaluate(node=>getComputedStyle(node).backgroundImage==='none'));
    await page.emulateMedia({reducedMotion:'no-preference',forcedColors:'none'});
    await page.getByText('בדיקת תצוגה הסתיימה',{exact:true}).waitFor({timeout:20000});
    record('completed process stops shimmer',await visualProcess.locator('.is-shimmering').count()===0);
    await page.emulateMedia({reducedMotion:'reduce'});
    await text.fill('טיוטת תצוגה');
    const geometries=[];
    for(const theme of ['light','dark']) for(const width of [320,360,500,900,1206,1380,1920]) {
      await page.setViewportSize({width,height:900});await api('PATCH','/v2/settings',{values:{ui_preferences:{theme_mode:theme}}},randomUUID());await page.reload();await page.locator('.composer').waitFor();await page.waitForTimeout(200);
      await text.focus();
      await page.locator('.chat-message-row--user').first().waitFor();
      await page.locator('.agent-tool-row').last().waitFor({state:'attached'});
      const g=await page.evaluate(()=>{const rect=node=>{const r=node.getBoundingClientRect();return {left:r.left,right:r.right,width:r.width,height:r.height,top:r.top,bottom:r.bottom};};const box=s=>rect(document.querySelector(s));const style=node=>{const c=getComputedStyle(node);return {background:c.backgroundColor,border:c.borderTop,padding:c.padding,borderRadius:c.borderRadius};};const c=box('.composer'),chat=box('.chat-column'),p=box('.composer-primary'),a=box('.composer-tool'),m=box('.model-quick-pill summary'),q=box('.autonomy-quick-pill .sds-button');const user=Array.from(document.querySelectorAll('.chat-message-row--user')).at(-1),bubble=user.querySelector('.sds-user-bubble'),footer=user.querySelector('.sds-message-actions');const process=Array.from(document.querySelectorAll('.agent-process')).at(-1);return {c,chat,p,a,m,q,reading:box('.message-list'),toolbar:box('.chat-toolbar-controls'),title:box('.chat-toolbar h1'),bubble:rect(bubble),footer:rect(footer),styles:{chat:style(document.querySelector('.chat-column')),bubble:style(bubble),process:style(process.querySelector('summary')),tool:style(process.querySelector('.agent-tool-row'))},textareaOutline:getComputedStyle(document.querySelector('.composer textarea')).outlineStyle,bodyWidth:document.documentElement.scrollWidth,width:innerWidth,theme:document.querySelector('.chat-design').dataset.theme};});
      record(`${theme}-${width} contained composer`,g.c.left>=g.chat.left-.5 && g.c.right<=g.chat.right+.5 && g.bodyWidth<=width && g.p.width>=40 && g.p.height>=40 && g.a.width>=40 && g.a.left>g.p.left && [g.m,g.q].every(r=>r.left>=g.c.left-.5 && r.right<=g.c.right+.5 && r.width>=40 && r.height>=40));
      record(`${theme}-${width} physical sides and user footer`,g.m.left<g.q.left && g.m.left-g.p.right<18 && g.a.left-g.q.right<18 && g.toolbar.right<=g.title.left+.5 && Math.abs(g.footer.right-g.bubble.right)<.5 && g.footer.top>=g.bubble.bottom && g.textareaOutline==='none');
      g.scrollbarGutter=await page.locator('.chat-stage').evaluate(node=>node.offsetWidth-node.clientWidth);
      record(`${theme}-${width} common reading cap and measured scrollbar gutters`,g.reading.left>=g.c.left-.5 && g.reading.right<=g.c.right+.5 && Math.abs(g.c.width-g.reading.width)<=g.scrollbarGutter+1 && (width<1206 || (Math.abs(g.c.width-697)<.5 && Math.abs(g.reading.width-697)<.5 && Math.abs(g.c.left-g.reading.left)<.5)));
      record(`${theme}-${width} full-height scroll with fixed composer and fade`,await page.evaluate(()=>{const s=document.querySelector('.chat-stage'),c=document.querySelector('.composer').getBoundingClientRect(),r=s.getBoundingClientRect(),f=getComputedStyle(document.querySelector('.chat-input-panel'),'::before'),track=getComputedStyle(s,'::-webkit-scrollbar-track');return c.bottom<=r.bottom+1 && c.bottom>r.bottom-3 && getComputedStyle(s).scrollbarGutter==='stable both-edges' && track.backgroundColor==='rgba(0, 0, 0, 0)' && f.backgroundImage.includes('linear-gradient') && f.backdropFilter!=='none';}));
      await fs.writeFile(path.join(output,'style-comparison.json'),JSON.stringify({theme,width,actual:g.styles,reference:references[theme]},null,2));
      if(references[theme])record(`${theme}-${width} frozen v7 surface and process styles`,g.theme===theme && ['chat','bubble','process','tool'].every(role=>g.styles[role].background===references[theme][role].background) && g.styles.bubble.padding===references[theme].bubble.padding && ['process','tool'].every(role=>g.styles[role].border===references[theme][role].border && g.styles[role].borderRadius===references[theme][role].borderRadius));
      geometries.push({theme,width,...g}); if([360,1380].includes(width))await page.screenshot({path:path.join(output,`${theme}-${width}.png`)});
    }
    record('no product runtime errors',errors.length===0);
    await page.setViewportSize({width:1380,height:900});await page.getByRole('button',{name:'כיווץ תפריט הצד'}).click();await page.getByRole('button',{name:'שיחה חדשה',exact:true}).click();await page.waitForTimeout(400);
    record('empty chat reserves the same scrollbar space before overflow',await page.locator('.chat-stage').evaluate(s=>s.scrollHeight<=s.clientHeight+1 && s.offsetWidth-s.clientWidth>=16 && document.querySelector('.composer').getBoundingClientRect().width===697));
    const report={ok:true,results,geometries,references,errors,commands:[...commands],edge:browser.version(),core:'real authenticated isolated profile; deterministic generation only',native:'IPC adapter; separate native smoke required'};
    await fs.writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({ok:true,checks:results.length,edge:report.edge}));
  } catch(error) {
    const renderer = page ? await page.evaluate(() => ({
      title: document.querySelector('.chat-toolbar h1')?.textContent,
      draft: document.querySelector('.composer textarea')?.value,
      primary: document.querySelector('.composer-primary')?.getAttribute('aria-label'),
      alerts: Array.from(document.querySelectorAll('[role=alert]')).map(node => node.textContent),
    })).catch(() => null) : null;
    const runs = await api('GET','/v2/runs?limit=100').catch(() => null);
    if (page) await page.screenshot({path:path.join(output,'failure.png')}).catch(() => {});
    await fs.writeFile(path.join(output,'failure.json'),JSON.stringify({results,errors,renderer,runs,error:error.stack,stderr:stderr.slice(-2000),commands:[...commands]},null,2));throw error;
  }
  finally { if(browser)await browser.close();host.stdin.end('shutdown\n');await new Promise(resolve=>{if(host.exitCode!==null)resolve();else host.once('exit',resolve);}); }
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
