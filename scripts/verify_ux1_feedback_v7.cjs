// UX-1 v7: the 16 latest requests. Source actions terminate in the isolated bridge.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const base=process.argv[2]||'http://127.0.0.1:1432';
const output=path.resolve(process.argv[3]||'.codex-local/ux-1/qa/feedback-next16/focused');
async function run(){
 await fs.mkdir(output,{recursive:true});
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const ctx=await browser.newContext({viewport:{width:1380,height:900},acceptDownloads:true});
 const page=await ctx.newPage();const checks=[],errors=[],remote=[],measurements=[];
 page.on('pageerror',e=>errors.push(e.message));
 ctx.on('request',r=>{if(!r.url().startsWith(base)&&!r.url().startsWith('data:')&&!r.url().startsWith('blob:'))remote.push(r.url());});
 await ctx.route('**/*',r=>r.request().url().startsWith(base)||r.request().url().startsWith('data:')?r.continue():r.abort());
 const check=(name,ok)=>{assert.ok(ok,name);checks.push(name);};
 const b=(name,root=page)=>root.getByRole('button',{name,exact:true});
 const fresh=async()=>{await page.goto(`${base}/ux-1.html?v=7`,{waitUntil:'networkidle'});await page.locator('.ux-prototype').waitFor({state:'visible'});await page.waitForTimeout(250);};
 const shot=async name=>page.screenshot({path:path.join(output,`${name}.png`)});
 const nav=async id=>{await page.locator(`nav button[data-section="${id}"]`).click();await page.waitForTimeout(180);};
 const draft=()=>page.getByRole('textbox',{name:'כתיבת הודעה',exact:true});
 const noAnnotations=async name=>check(`05 no review annotations ${name}`,!/(הדגמ|מדומ|סינתט|דוגמ|UX-1|simulat)/i.test(await page.locator('.ux-prototype').innerText()));
 const report=async(failure=null)=>fs.writeFile(path.join(output,'report.json'),JSON.stringify({checks,measurements,errors,remote,trace:await page.evaluate(()=>window.__UX1_DEMO__?.trace??[]),...(failure?{failure:String(failure)}:{})},null,2));
 try{
 await fresh();await noAnnotations('chat');
 // Sidebar uses one anchored brand control in both modes; rail retains its actions.
 const geometry=()=>page.locator('.ux-brand-reopen,.ux-sidebar .ux-new-chat').evaluateAll(xs=>xs.map(x=>{const r=x.getBoundingClientRect();return{x:r.x,y:r.y,w:r.width,h:r.height};}));
 const full=await geometry();await b('כיווץ סרגל השיחות').hover();await page.waitForTimeout(180);
 check('06 expanded brand replaces logo on hover',await page.locator('.ux-brand-reopen>.ux-icon').evaluate(x=>getComputedStyle(x).opacity==='1'));
 await b('כיווץ סרגל השיחות').click();const rail=await geometry();
 check('06 exact anchored brand position',full[0].x===rail[0].x&&full[0].y===rail[0].y);
 check('07 exact new chat vertical position',full[1].y===rail[1].y);
 check('07 collapsed new chat remains accessible',await b('שיחה חדשה').isVisible()&&await b('שיחה חדשה').evaluate(x=>getComputedStyle(x).fontSize==='0px'));
 const stack=await page.locator('.ux-sidebar-bottom>button').evaluateAll(xs=>xs.map(x=>{const r=x.getBoundingClientRect();return{x:r.x,y:r.y,w:r.width,h:r.height,label:x.ariaLabel};}));
 check('07 bottom rail column',stack.length===5&&stack.every(x=>x.x===stack[0].x)&&stack.every((x,i)=>i===0||x.y>stack[i-1].y+stack[i-1].h));
 check('07 settings bottom and separated from new chat',stack.at(-1).label==='הגדרות וספקים'&&stack[0].y>rail[1].y+rail[1].h+160);
 await shot('collapsed-rail');await b('הרחבת סרגל השיחות').click();
 check('06 same brand toggles both directions',await page.locator('.ux-brand button').count()===1&&await b('כיווץ סרגל השיחות').isVisible());
 check('03 history vertical ellipsis',await page.locator('.ux-conversation-menu-trigger>img').first().evaluate(x=>getComputedStyle(x).transform==='none'));
 check('03 current conversation horizontal ellipsis',await page.locator('.ux-topbar [data-icon="more"]').evaluate(x=>getComputedStyle(x).transform!=='none'));
 // Model/policy/attachment/current/history popovers: no X, toggle/outside/Escape.
 const triggers=['.ux-model-trigger','.ux-policy-trigger','button[aria-label="צירוף קובץ"]','.ux-topbar button:has([data-icon="more"])','.ux-conversation-menu-trigger'];
 for(const [i,selector] of triggers.entries()){
  const trigger=page.locator(selector).first();await trigger.click();await page.locator('.ux-popup').waitFor();
  check(`02 no X in popover ${i}`,await page.locator('.ux-popup-title [data-icon="close"]').count()===0);
  await noAnnotations(`popover ${i}`);
  check(`02 popover keeps trigger enabled ${i}`,await trigger.evaluate(x=>!x.closest('[inert]')));
  await trigger.click();check(`02 repeated trigger closes ${i}`,await page.locator('.ux-popup').count()===0);
  await trigger.click();await page.locator('.ux-topbar strong').click();check(`02 outside click dismisses ${i}`,await page.locator('.ux-popup').count()===0);
  await trigger.click();await page.keyboard.press('Escape');check(`02 Escape restores trigger ${i}`,await trigger.evaluate(x=>x===document.activeElement));
 }
 await page.locator('.ux-model-trigger').click();
 check('11 no provider model count',await page.locator('.ux-provider-list button small').count()===0);
 await page.locator('.ux-provider-list button').filter({hasText:'ChatGPT'}).hover();await page.waitForTimeout(120);
 const long=page.locator('.ux-model-list .ux-marquee-text').first();await page.locator('.ux-model-list button').first().hover();
 const movement=await long.evaluate(x=>{const s=getComputedStyle(x),p=x.parentElement;return{timing:s.animationTimingFunction,duration:s.animationDuration,shift:Math.abs(parseFloat(p.style.getPropertyValue('--marquee-shift'))),name:s.animationName};});
 check('01 faster linear marquee without endpoint dwell',movement.timing==='linear'&&movement.name==='ux-label-travel'&&parseFloat(movement.duration)<=Math.max(1.2,movement.shift/72)+.02);
 const frames=await long.evaluate(async x=>{const a=x.getAnimations()[0];a.pause();const duration=a.effect.getTiming().duration;const values=[.02,.12,.8,.9].map(t=>{a.currentTime=duration*t;return new DOMMatrix(getComputedStyle(x).transform).m41});return values;});
 check('01 constant velocity at start and end',Math.abs(Math.abs(frames[1]-frames[0])-Math.abs(frames[3]-frames[2]))<1);
 measurements.push({marquee:movement,frames});await noAnnotations('model menu');await shot('model-menu');await page.keyboard.press('Escape');
 // Every message action footer follows every content result, in DOM and geometry.
 const last=page.locator('.ux-message').last();
 check('04 references precede message actions in source row',await last.evaluate(x=>{const row=x.querySelector('.chat-message-row'),footer=row.querySelector(':scope>.message-actions');return [...x.querySelectorAll('.canvas-open-card,.ux-workspace-reference')].length===3&&[...x.querySelectorAll('.canvas-open-card,.ux-workspace-reference')].every(card=>card.compareDocumentPosition(footer)&Node.DOCUMENT_POSITION_FOLLOWING)}));
 check('04 footer physically below all outputs',await last.evaluate(x=>{const footer=x.querySelector('.message-actions').getBoundingClientRect();return [...x.querySelectorAll('.canvas-open-card,.ux-workspace-reference')].every(c=>c.getBoundingClientRect().bottom<=footer.top+1)}));
 const table=await last.locator('.message-table-actions button').evaluateAll(xs=>xs.map(x=>{const r=x.getBoundingClientRect(),s=getComputedStyle(x),img=x.querySelector('img'),i=img?.getBoundingClientRect();return{w:r.width,h:r.height,rad:s.borderRadius,pad:s.padding,img:i?{w:i.width,h:i.height,dx:i.x+i.width/2-r.x-r.width/2,dy:i.y+i.height/2-r.y-r.height/2}:null};}));
 check('08 symmetric standard table actions',table.length===2&&table.every(x=>x.w===40&&x.h===40&&x.rad==='10px'&&x.pad==='8px'&&x.img?.w===18&&x.img?.h===18&&Math.abs(x.img.dx)<1&&Math.abs(x.img.dy)<1));
 measurements.push({table});const [csv]=await Promise.all([page.waitForEvent('download'),b('ייצוא CSV',last).click()]);await csv.saveAs(path.join(output,'table.csv'));check('08 actual CSV contents',(await fs.readFile(path.join(output,'table.csv'),'utf8')).includes('Discover needs before planning'));
 await page.waitForTimeout(100);check('13 table export success stays quiet',await page.locator('.message-table-feedback:visible').count()===0);
 await page.locator('.ux-messages').evaluate(x=>x.scrollTop=x.scrollHeight);await shot('chat-outputs');
 // Newly sent bubble animates briefly, old history never replays it.
 await b('שיחה חדשה').click();await draft().fill('A short English message');await b('שליחת הודעה').click();
 const bubble=page.locator('.ux-user .chat-message--user').last();
 check('15 new bubble entry animation',await bubble.evaluate(x=>getComputedStyle(x).animationName==='ux-user-enter'));
 const shape=await bubble.evaluate(x=>{const r=x.getBoundingClientRect(),row=x.closest('.ux-message').getBoundingClientRect(),s=getComputedStyle(x);return{right:r.right,rowRight:row.right,radii:[s.borderTopLeftRadius,s.borderTopRightRadius,s.borderBottomLeftRadius,s.borderBottomRightRadius],bg:s.backgroundColor,accent:getComputedStyle(document.querySelector('.ux-prototype')).getPropertyValue('--accent-soft').trim()};});
 check('09 all user corners rounded and physical right alignment',shape.radii.every(v=>v==='16px')&&Math.abs(shape.right-shape.rowRight)<1);
 check('10 light blue user bubble',await bubble.evaluate(x=>{const c=document.createElement('span');c.style.background='var(--accent-soft)';x.append(c);const same=getComputedStyle(c).backgroundColor===getComputedStyle(x).backgroundColor;c.remove();return same}));
 await page.waitForTimeout(300);check('15 animation consumed once',await bubble.evaluate(x=>getComputedStyle(x).animationName==='none'));await b('עצירה').click();
 await page.locator('.ux-conversation').filter({hasText:'מרחב חדש לקהילה'}).click();await page.locator('.ux-conversation').first().click();check('15 no animation replay on history navigation',await bubble.evaluate(x=>getComputedStyle(x).animationName==='none'));
 await page.emulateMedia({reducedMotion:'reduce'});await b('שיחה חדשה').click();await draft().fill('הודעה בעברית');await b('שליחת הודעה').click();check('09 Hebrew bubble right alignment',await bubble.evaluate(x=>Math.abs(x.getBoundingClientRect().right-x.closest('.ux-message').getBoundingClientRect().right)<1));check('15 reduced motion disables entry',await bubble.evaluate(x=>getComputedStyle(x).animationName==='none'));await b('עצירה').click();await page.emulateMedia({reducedMotion:'no-preference'});
 await b('שיחה חדשה').click();await draft().fill('שיחה עם שם ארוך מאוד לבדיקת קריאות ותנועה אחידה בלי האטה מיותרת בהיסטוריית השיחות');await b('שליחת הודעה').click();await b('עצירה').click();const historyLong=page.locator('.ux-conversation').first();await historyLong.hover();check('01 history uses same fast linear motion',await historyLong.locator('.ux-marquee-text').evaluate(x=>getComputedStyle(x).animationTimingFunction==='linear'&&getComputedStyle(x).animationName==='ux-label-travel'));await page.mouse.move(600,80);
 // Waiting approval -> running retains the exact timeline DOM and expanded I/O.
 await page.locator('.ux-conversation').filter({hasText:'מחקר לקראת הסדנה'}).click();
 const proc=page.locator('.ux-activity .agent-process');await proc.locator(':scope>summary').click();const group=proc.locator('.agent-tool-group').first();await group.locator(':scope>summary').click();const tool=group.locator('.agent-tool-row').first();await tool.locator(':scope>summary').click();
 await page.evaluate(()=>window.__qaTimeline=document.querySelector('.ux-activity .agent-process'));
 await b('אישור לפעולה הזו').click();await page.waitForTimeout(350);
 check('16 timeline stays visible immediately after approval',await proc.isVisible()&&await page.locator('.ux-activity .agent-initial-thinking').count()===0);
 check('16 DOM identity and expanded hierarchy retained',await proc.evaluate(x=>x===window.__qaTimeline&&x.open&&x.querySelector('.agent-tool-group').open&&x.querySelector('.agent-tool-row').open));
 check('16 actual tool I/O still available',(await tool.innerText()).includes('meetings,1200'));
 await shot('approval-continued');await b('עצירה').click();
 // Management presentation remains connected to original handlers.
 await b('הגדרות וספקים').click();
 for(const id of ['settings_ai','settings_security','settings_tools','settings_appearance','settings_advanced','workspace','usage','tools','memory','tasks','diagnostics','logs','about']){await nav(id);await noAnnotations(id);}
 await nav('workspace');
 check('14 coherent workspace groups and standard switches',await page.locator('.ux-workspace-settings .ux-settings-group').count()===3&&await page.locator('.ux-workspace-settings .source-switch').evaluateAll(xs=>xs.length===2&&xs.every(x=>x.getBoundingClientRect().width===44&&x.getBoundingClientRect().height===26)));
 check('12 workspace refresh is icon only',await b('רענן').evaluate(x=>x.querySelector('img')&&x.textContent.trim()===''));
 const switched=page.getByRole('checkbox',{name:'סרגל השיחות פתוח בכניסה'});await switched.uncheck();
 check('14 workspace preference real path retained',await page.evaluate(()=>window.__UX1_DEMO__.settings().values.ui_preferences.workspace_sidebar_collapsed===true));
 check('13 workspace has no save success status',!(await page.locator('.ux-workspace-settings').innerText()).includes('נשמר'));
 await b('רענן').click();await page.waitForTimeout(200);check('14 refreshed preference retained',!(await switched.isChecked()));await shot('workspace-settings');
 await nav('tasks');check('12 task refresh icon with accessible name',await b('רענן').evaluate(x=>x.dataset.compactAction==='true'&&getComputedStyle(x).fontSize==='0px'));
 const before=await page.evaluate(()=>window.__UX1_DEMO__.trace.length);await b('רענן').click();await page.waitForTimeout(150);check('12 original task refresh handler',await page.evaluate(n=>window.__UX1_DEMO__.trace.slice(n).some(t=>t.path==='/v2/management/tasks'&&t.method==='GET'),before));
 await nav('memory');for(const label of ['זיכרון חדש','ייבוא מוצפן','ייצוא מוצפן'])check(`12 memory toolbar semantic icon ${label}`,await b(label).evaluate(x=>!!x.dataset.demoIcon||!!x.querySelector('img')));
 const memory=page.locator('.management-cards article').first();await memory.getByRole('button',{name:/^(הצמד|בטל הצמדה)$/}).click();await page.waitForTimeout(150);check('13 routine memory success hidden',await page.locator('.management-notice:visible,.settings-status:visible').evaluateAll(xs=>xs.every(x=>!x.textContent.includes('הפעולה הושלמה'))));
 await nav('tools');await page.getByRole('checkbox',{name:'כבה file_manager',exact:true}).click();await page.waitForTimeout(150);check('13 routine tool success hidden',await page.locator('.settings-status:visible').evaluateAll(xs=>xs.every(x=>!x.textContent.includes('הפעולה הושלמה'))));
 await nav('usage');check('12 usage clear/refresh icon only',await b('ניקוי נתונים').evaluate(x=>getComputedStyle(x).fontSize==='0px')&&await b('רענון').evaluate(x=>getComputedStyle(x).fontSize==='0px'));await b('ניקוי נתונים').click();check('12 usage confirmation still required',await page.getByRole('alertdialog').isVisible());await b('ביטול',page.getByRole('alertdialog')).click();
 await nav('settings_ai');await page.locator('[data-setting-path="provider_api_key"] input').fill('bad-demo');await page.getByText('המפתח נדחה.',{exact:false}).waitFor();check('13 meaningful provider error retained',true);
 for(const theme of ['light','dark']){if(await page.locator('.ux-prototype').getAttribute('data-theme')!==theme)await b(theme==='dark'?'מעבר למצב כהה':'מעבר למצב בהיר').click();await nav('workspace');for(const width of [360,900,1380]){await page.setViewportSize({width,height:780});const layout=await page.locator('.ux-management-body').evaluate(x=>({w:x.clientWidth,s:x.scrollWidth,v:innerWidth,page:document.documentElement.scrollWidth}));check(`14 workspace fits ${theme}/${width}`,layout.s<=layout.w+1&&layout.page<=layout.v+1);await shot(`workspace-${theme}-${width}`);}}
 await page.setViewportSize({width:1380,height:900});await b('חזרה לשיחה').click();await b('פתיחת סביבת העבודה').click();await page.locator('.ux-workbench-launch-grid button').filter({hasText:'דפדפן'}).click();await page.waitForTimeout(200);await noAnnotations('browser');await shot('workspace-browser');
 check('no remote requests',remote.length===0);check('no runtime errors',errors.length===0);check('all bridge paths implemented and isolated',await page.evaluate(()=>window.__UX1_DEMO__.isolated&&!window.__UX1_DEMO__.trace.some(t=>t.unsupported)));
 await report();console.log(JSON.stringify({checks:checks.length,output},null,2));
 }catch(e){await shot('failure');await report(e);throw e;}finally{await browser.close();}
}
run().catch(e=>{console.error(e);process.exitCode=1});
