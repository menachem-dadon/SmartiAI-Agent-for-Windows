// Current 21-point UX-1 feedback: rendered behavior on the isolated bridge.
const { chromium }=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const base=process.argv[2]||'http://127.0.0.1:1432';
const output=path.resolve(process.argv[3]||'.codex-local/ux-1/qa/feedback-21/focused');
async function run(){
 await fs.mkdir(output,{recursive:true});
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:1380,height:900},acceptDownloads:true});
 const page=await context.newPage();const checks=[],errors=[],remote=[],measurements=[];
 page.on('pageerror',e=>errors.push(e.message));
 context.on('request',r=>{if(!r.url().startsWith(base)&&!r.url().startsWith('data:')&&!r.url().startsWith('blob:'))remote.push(r.url());});
 await context.route('**/*',r=>r.request().url().startsWith(base)||r.request().url().startsWith('data:')?r.continue():r.abort());
 const check=(name,condition)=>{assert.ok(condition,name);checks.push(name);};
 const b=(name,root=page)=>root.getByRole('button',{name,exact:true});
 const shot=async name=>page.screenshot({path:path.join(output,`${name}.png`)});
 const fresh=async(query='')=>{await page.goto(`${base}/ux-1.html?v=6${query}`,{waitUntil:'networkidle'});};
 const nav=async id=>{await page.locator(`nav button[data-section="${id}"]`).click();await page.waitForTimeout(160);};
 const draft=()=>page.getByRole('textbox',{name:'כתיבת הודעה',exact:true});
 const modelMenu=async()=>{await page.locator('.ux-model-trigger').click();await page.waitForTimeout(100);};
 const patch=async values=>page.evaluate(values=>window.__TAURI_INTERNALS__.invoke('core_api',{request:{method:'PATCH',path:'/v2/settings',body:{values}}}),values);
 const speed=async()=>{await b('תרחישי התנסות').click();await page.getByRole('combobox',{name:'השהיית מודל בהדגמה'}).selectOption('1000');await page.keyboard.press('Escape');};
 try{
 await fresh();
 // Empty drafts, chronology, delayed source thinking and cancellation.
 const initial=await page.locator('.ux-conversation').count();
 for(let i=0;i<4;i++)await b('שיחה חדשה').click();
 check('05 repeated empty drafts never enter history',await page.locator('.ux-conversation').count()===initial);
 await draft().fill('טיוטה זמנית');await page.locator('.ux-conversation').first().click();await b('שיחה חדשה').click();
 check('05 pending draft survives return',await draft().inputValue()==='טיוטה זמנית');
 await draft().fill('הודעה חדשה בראש ההיסטוריה');const began=Date.now();await b('שליחת הודעת הדגמה').click();
 check('06 first submission promotes new conversation to top',(await page.locator('.ux-conversation').first().innerText())==='הודעה חדשה בראש ההיסטוריה');
 await page.locator('.ux-activity .agent-initial-thinking').waitFor();
 check('01 actual delayed thinking text visible',(await page.locator('.ux-activity .agent-initial-thinking').innerText())==='חושב...');
 await page.waitForTimeout(3200);check('01 thinking remains during five-second model delay',await page.locator('.ux-activity .agent-initial-thinking').isVisible());
 measurements.push({thinkingObservedMs:Date.now()-began});await shot('thinking');await b('עצירת ההדגמה').click();await page.waitForTimeout(3700);
 check('01 cancellation invalidates delayed callbacks',await page.locator('.ux-activity').getAttribute('data-state')==='cancelled'&&await page.locator('.ux-approval').count()===0);
 await speed();await b('שיחה חדשה').click();await draft().fill('מסמך חדש לבדיקה');await b('שליחת הודעת הדגמה').click();
 await b('אישור לפעולה הזו').waitFor();await b('אישור לפעולה הזו').click();await page.locator('.ux-activity[data-state="completed"]').waitFor({state:'attached'});
 check('01 approval completes with content references',await page.locator('.ux-workspace-reference').count()===2&&await page.locator('.canvas-open-card').count()===1);
 // One line only; real populated history supplies overflow, no empty mock rows.
 for(let i=0;i<18;i++){await b('שיחה חדשה').click();await draft().fill(`שיחה ${i} עם שם ארוך מאוד לבדיקת תנועה ונוחות בהיסטוריית השיחות של סמארטי`);await b('שליחת הודעת הדגמה').click();await b('עצירת ההדגמה').click();}
 const row=page.locator('.ux-conversation').first();check('04 names only in history',await row.locator('small,strong').count()===0);
 check('04 history one line',await row.locator('.ux-marquee').evaluate(x=>getComputedStyle(x).whiteSpace==='nowrap'&&x.clientHeight<28));
 await row.hover();await page.waitForTimeout(1300);const motion=await row.locator('.ux-marquee-text').evaluate(x=>getComputedStyle(x).transform);
 check('04 clipped name moves on hover',motion!=='none'&&motion!=='matrix(1, 0, 0, 1, 0, 0)');
 await page.mouse.move(500,80);check('04 movement resets off hover',await row.locator('.ux-marquee-text').evaluate(x=>getComputedStyle(x).animationName==='none'));
 await page.emulateMedia({reducedMotion:'reduce'});await row.hover();check('04 marquee respects reduced motion',await row.locator('.ux-marquee-text').evaluate(x=>getComputedStyle(x).animationName==='none'));await page.emulateMedia({reducedMotion:'no-preference'});
 const fixed=await page.locator('.ux-history>.ux-new-chat,.ux-history>.ux-search').evaluateAll(xs=>xs.map(x=>x.getBoundingClientRect().y));
 check('04 history populated and scrollable',await page.locator('.ux-history-scroll').evaluate(x=>x.scrollHeight>x.clientHeight));
 await page.locator('.ux-history-scroll').evaluate(x=>x.scrollTop=x.scrollHeight);
 check('04 fixed new/search preserved',JSON.stringify(fixed)===JSON.stringify(await page.locator('.ux-history>.ux-new-chat,.ux-history>.ux-search').evaluateAll(xs=>xs.map(x=>x.getBoundingClientRect().y))));
 await b('כיווץ סרגל השיחות').click();check('07 collapsed rail has one brand reopen target',await page.locator('.ux-brand button').count()===1);
 const brand=b('הרחבת סרגל השיחות');await brand.hover();await page.waitForTimeout(180);
 check('07 hover swaps brand for reopen icon',await brand.evaluate(x=>getComputedStyle(x.querySelector('.ux-brand-logo')).opacity==='0'&&getComputedStyle(x.querySelector('.ux-icon')).opacity==='1'));
 await shot('collapsed-brand-hover');await brand.click();
 // All 36 synthetic models, with source-compatible favorites and active fallback.
 await fresh();const catalog=await page.evaluate(async()=>{const d=await import('/src/ux1/data.ts');return d.models.map(x=>({id:x.id,name:x.name,provider:x.provider,providerId:x.providerId,modelKey:x.modelKey}));});
 await patch({favorite_models:catalog.map(x=>({provider:x.providerId,model:x.modelKey}))});
 for(const model of catalog){await modelMenu();await page.locator('.ux-provider-list button').filter({hasText:model.provider}).first().click();await page.getByRole('menuitemradio',{name:model.name,exact:true}).click();await modelMenu();check(`02 reasoning for ${model.id}`,await page.getByRole('combobox',{name:'רמת חשיבה בהדגמה'}).count()===1);await page.keyboard.press('Escape');}
 await modelMenu();await page.locator('.ux-provider-list button').filter({hasText:'חשבון ChatGPT'}).click();
 check('03 redundant model/provider headings removed',await page.locator('.ux-model-columns h3').count()===0);
 const modelRows=await page.locator('.ux-model-columns button').evaluateAll(xs=>xs.map(x=>({h:x.getBoundingClientRect().height,lines:x.querySelector('.ux-marquee').clientHeight,nowrap:getComputedStyle(x).whiteSpace})));
 measurements.push({modelRows});check('03 provider/model rows single line',modelRows.every(x=>x.h===44&&x.lines<28&&x.nowrap==='nowrap'));
 check('03 provider arrows are left chevrons',await page.locator('.ux-provider-list [data-icon="chevron"]').evaluateAll(xs=>xs.every(x=>getComputedStyle(x).transform==='matrix(0, 1, -1, 0, 0, 0)'))&&await page.locator('.ux-provider-list [data-icon="back"]').count()===0);
 const longModel=page.getByRole('menuitemradio',{name:/Codex · Reasoning/});await longModel.hover();await page.waitForTimeout(1300);
 check('03 long model marquee moves',await longModel.locator('.ux-marquee-text').evaluate(x=>getComputedStyle(x).animationName==='ux-label-travel'));
 await shot('models-one-line');await page.keyboard.press('Escape');
 check('09 model chevron on physical left',await page.locator('.ux-model-trigger').evaluate(x=>x.querySelector('[data-icon="chevron"]').getBoundingClientRect().right<x.querySelector('bdi').getBoundingClientRect().left));
 const policyGeometry=await page.locator('.ux-composer-controls').evaluate(x=>{const p=x.querySelector('.ux-policy-trigger').getBoundingClientRect(),a=x.querySelector('[aria-label="צירוף קובץ הדגמה"]').getBoundingClientRect();return {p:p.x,a:a.x,gap:a.x-p.right};});measurements.push({policyGeometry});check('08 policy adjacent to plus on right',policyGeometry.p<policyGeometry.a&&policyGeometry.gap>=0&&policyGeometry.gap<20);
 await page.locator('.ux-policy-trigger').click();check('08 policy states global scope',(await page.locator('.ux-popup-note').innerText()).includes('לכל סמארטי'));await page.locator('.ux-menu-option').filter({hasText:'אוטונומי'}).click();
 await page.locator('.ux-conversation').nth(2).click();await b('שיחה חדשה').click();check('08 global policy retained across chats',(await page.locator('.ux-policy-trigger').innerText())==='אוטונומי'&&await page.evaluate(()=>window.__UX1_DEMO__.settings().values.autonomy_mode==='max_autonomy'));check('08 policy has no chevron',await page.locator('.ux-policy-trigger [data-icon="chevron"]').count()===0);
 // Workbench contracts: four launcher kinds, content-created canvas, target reuse,
 // last tab on reopen, closable local tabs and session-only lifetime.
 await fresh();await b('פתיחת סביבת העבודה').click();check('12 four launcher kinds without canvas',await page.locator('.ux-workbench-launch-grid button').count()===4&&await page.locator('.ux-workbench-launch-grid').getByText('קנבס',{exact:true}).count()===0);
 await b('הוספת לשונית סביבת עבודה').click();check('12 no canvas in add menu',await page.getByRole('menuitem',{name:'קנבס',exact:true}).count()===0);await page.keyboard.press('Escape');await b('סגירת סביבת העבודה').click();
 await page.locator('.ux-workspace-reference').filter({hasText:'מסמך Markdown'}).click();check('13 artifact reference opens its document tab',await page.getByRole('tab',{name:'תוכנית עבודה',exact:true}).getAttribute('aria-selected')==='true'&&await page.locator('.ux-document-pane').isVisible());
 await b('סגירת סביבת העבודה').click();await page.locator('.ux-workspace-reference').filter({hasText:'מסמך Markdown'}).click();check('13 repeated artifact reference reuses same tab',await page.getByRole('tab',{name:'תוכנית עבודה',exact:true}).count()===1);
 await b('סגירת סביבת העבודה').click();await page.locator('.ux-workspace-reference').filter({hasText:'דף שנבדק'}).click();await page.getByRole('textbox',{name:'כתובת או חיפוש',exact:true}).waitFor();
 check('13 browser reference targets correct content',await page.getByRole('tab',{name:'המרכז הקהילתי',exact:true}).getAttribute('aria-selected')==='true'&&(await page.getByRole('textbox',{name:'כתובת או חיפוש',exact:true}).inputValue()).includes('community.example/demo'));
 await b('סגירת סביבת העבודה').click();await page.locator('.canvas-open-card button').click();await page.locator('.canvas-panel:visible iframe').waitFor();check('12 canvas opens from dedicated chat card',await page.getByRole('tab',{name:'קנבס',exact:true}).getAttribute('aria-selected')==='true');
 await b('סגירת סביבת העבודה').click();await b('פתיחת סביבת העבודה').click();check('16 general reopen retains last active canvas',await page.getByRole('tab',{name:'קנבס',exact:true}).getAttribute('aria-selected')==='true');
 const tabWrap=page.getByRole('tab',{name:'קנבס',exact:true}).locator('..');const close=tabWrap.locator('.ux-tab-close');await page.mouse.move(900,50);await page.waitForTimeout(200);
 check('14 tab X hidden at rest',await close.evaluate(x=>getComputedStyle(x).opacity==='0'));await tabWrap.hover();await page.waitForTimeout(180);check('14 hover X visible on left of tab title',await close.evaluate(x=>getComputedStyle(x).opacity==='1'&&x.getBoundingClientRect().right<=x.previousElementSibling.getBoundingClientRect().left+1));
 await b('הרחבת סביבת העבודה').click();check('17 expansion button becomes shrink',await b('כיווץ סביבת העבודה').count()===1&&await page.locator('.ux-workbench-actions [data-icon="shrink"]').count()===1);await b('כיווץ סביבת העבודה').click();
 check('15 global workspace toggle icon only, no workspace X',await b('סגירת סביבת העבודה').innerText()===''&&await page.locator('.ux-workbench-close').count()===0&&await page.locator('.ux-workbench-actions button').count()===2);
 await tabWrap.hover();await close.click();check('14 closes active tab and selects neighbor',await page.getByRole('tab',{name:'קנבס',exact:true}).count()===0&&await page.getByRole('tab',{name:'המרכז הקהילתי',exact:true}).getAttribute('aria-selected')==='true');
 await page.getByRole('tab',{name:'תוכנית עבודה',exact:true}).press('Delete');check('14 deleting inactive tab selects remaining browser',await page.getByRole('tab',{name:'המרכז הקהילתי',exact:true}).getAttribute('aria-selected')==='true');
 await page.getByRole('tab',{name:'המרכז הקהילתי',exact:true}).press('Delete');check('14 last close returns to launcher',await page.getByRole('tab').count()===0&&await page.locator('.ux-workbench-launcher').isVisible());
 await page.getByRole('button',{name:'קבצים עיון בקבצים ותצוגה מקדימה',exact:true}).click();await fresh();await b('פתיחת סביבת העבודה').click();check('16 reload closes all session tabs',await page.getByRole('tab').count()===0);await b('סגירת סביבת העבודה').click();
 // Settings retain source autosave and errors without successful-save badges.
 await b('הגדרות וספקים').click();await page.getByRole('checkbox',{name:'הצג הגדרות מתקדמות',exact:true}).check();await nav('settings_advanced');
 const number=page.locator('[data-setting-path="command_timeout_seconds"] input');await number.fill('9');await number.blur();await page.waitForTimeout(1000);
 const savedNumber=await page.evaluate(()=>window.__UX1_DEMO__.settings().values.command_timeout_seconds);const savedBadges=await page.locator('.source-save-state').count(),fieldStatus=await page.locator('.source-settings-field [role="status"]').allTextContents();measurements.push({savedNumber,savedBadges,fieldStatus});
 check('10 numeric autosave retained with no success badge',Number(savedNumber)===9&&savedBadges===0&&await number.locator('xpath=ancestor::*[@data-setting-path]').getByRole('status').count()===0&&!fieldStatus.some(x=>/^(נשמר|שומר…|אין שינויים חדשים)$/.test(x)));
 const slider=page.locator('[data-setting-path="max_agent_loops"] input');await slider.scrollIntoViewIfNeeded();await slider.press('Home');await page.waitForTimeout(180);
 // Capture the transition in browser frames, avoiding automation round-trip
 // latency that can outlast a 120ms transition on a loaded Windows host.
 await slider.evaluate(x=>{window.__UX_RANGE_SAMPLES=[];x.addEventListener('input',()=>{let count=0;const sample=()=>{window.__UX_RANGE_SAMPLES.push(parseFloat(getComputedStyle(x).getPropertyValue('--ux-range-fill')));if(++count<15)requestAnimationFrame(sample);};requestAnimationFrame(sample);},{once:true});});await slider.press('End');await page.waitForTimeout(300);
 const mid=await slider.evaluate(x=>({samples:window.__UX_RANGE_SAMPLES,h:x.getBoundingClientRect().height,transition:getComputedStyle(x).transitionProperty,bg:getComputedStyle(x).backgroundImage}));measurements.push({slider:mid});
 check('19 full thick pill interpolates smoothly',mid.h===24&&mid.samples.some(value=>value>0&&value<100)&&mid.samples.at(-1)===100&&mid.transition.includes('--ux-range-fill')&&mid.bg.startsWith('linear-gradient'));
 check('19 keyboard saves original unlimited sentinel',await page.evaluate(()=>window.__UX1_DEMO__.settings().values.max_agent_loops===0));
 const sb=await slider.boundingBox();await page.mouse.move(sb.x+sb.width*.7,sb.y+sb.height/2);await page.mouse.down();await page.mouse.move(sb.x+sb.width*.4,sb.y+sb.height/2,{steps:12});await page.mouse.up();await page.waitForTimeout(200);
 check('19 pointer drag saves actual value',await page.evaluate(value=>window.__UX1_DEMO__.settings().values.max_agent_loops===Number(value),await slider.inputValue()));await shot('sliders-smooth');
 await nav('settings_appearance');check('18 theme options have sun moon system icons',await page.locator('[data-setting-path="ui_preferences.theme_mode"] [data-icon]').evaluateAll(xs=>xs.map(x=>x.dataset.icon).sort().join(',')==='moon,screen,sun'));
 const update=page.locator('.update-controls.compact');await update.scrollIntoViewIfNeeded();const updateData=await update.evaluate(x=>({display:getComputedStyle(x).display,border:getComputedStyle(x.querySelector('.source-update-status')).borderWidth,button:x.querySelector('button').getBoundingClientRect().width,width:x.clientWidth}));measurements.push({updateData});check('20 clear update status and natural action layout',updateData.display==='flex'&&updateData.border==='0px'&&updateData.button<updateData.width*.8);await shot('update-controls');await b('בדוק עדכונים עכשיו').click();await page.getByText('עדכון זמין: גרסה UX-1-demo',{exact:true}).waitFor();check('20 real update check path preserved',true);
 await nav('settings_ai');await page.locator('[data-setting-path="api_mode"] select').selectOption('openai');await page.locator('[data-setting-path="provider_api_key"] input').fill('bad-demo');await page.getByText('מפתח הדוגמה נדחה.',{exact:false}).waitFor();check('10 validation errors remain visible',true);
 await nav('memory');const memory=page.locator('.management-cards article').first();await memory.locator('footer').scrollIntoViewIfNeeded();await page.waitForTimeout(100);
 check('21 memory actions icons with accessible names',await memory.locator('footer button').evaluateAll(xs=>xs.every(x=>getComputedStyle(x).fontSize==='0px'&&x.getAttribute('aria-label')&&x.dataset.demoIcon==='true')));await shot('memory-icons');await b('פרטים',memory).click();check('21 memory details handler retained',await page.locator('.memory-details').count()>0||await page.getByText('העדפות כתיבה',{exact:true}).count()>1);
 await nav('tasks');const task=page.locator('.management-cards article').first();await task.locator('footer').scrollIntoViewIfNeeded();await page.waitForTimeout(100);check('21 task actions icons with accessible names',await task.locator('footer button').evaluateAll(xs=>xs.every(x=>getComputedStyle(x).fontSize==='0px'&&x.getAttribute('aria-label')&&x.dataset.demoIcon==='true')));await b('הרץ שוב',task).click();await b('ביטול',task).click();await b('המשך',task).waitFor();await b('המשך',task).click();await b('המשך',task).waitFor({state:'hidden'});check('21 task retry/cancel/resume handlers retained',true);await shot('task-icons');
 await b('חזרה לשיחה').click();const table=page.locator('.message-table-actions').last();await table.scrollIntoViewIfNeeded();await page.waitForTimeout(100);check('11 table actions icons only, labelled',await table.locator('button').evaluateAll(xs=>xs.every(x=>getComputedStyle(x).fontSize==='0px'&&x.getAttribute('aria-label')&&x.querySelector('img'))));const csvEvent=page.waitForEvent('download');await table.getByRole('button',{name:/ייצוא CSV/}).click();const csv=await csvEvent;await csv.saveAs(path.join(output,'table.csv'));check('11 table export actual CSV download',csv.suggestedFilename().endsWith('.csv')&&(await fs.readFile(path.join(output,'table.csv'),'utf8')).includes('שלב'));
 for(const theme of ['light','dark'])for(const width of [360,900,1380]){
   await page.setViewportSize({width,height:653});await fresh(`&theme=${theme}`);await modelMenu();const bounds=await page.locator('.ux-popup-models').evaluate(x=>{const r=x.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight&&r.top>=0&&x.scrollWidth<=x.clientWidth;});check(`popup contained ${theme}/${width}`,bounds);await shot(`models-${theme}-${width}`);await page.keyboard.press('Escape');await b('פתיחת סביבת העבודה').click();check(`launcher contained ${theme}/${width}`,await page.locator('.ux-artifact').evaluate(x=>x.scrollWidth<=x.clientWidth));await shot(`launcher-${theme}-${width}`);await b('סגירת סביבת העבודה').click();check(`composer contained ${theme}/${width}`,await page.locator('.ux-composer').evaluate(x=>x.scrollWidth<=x.clientWidth)&&await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 }
 check('isolated bridge no missing paths',await page.evaluate(()=>window.__UX1_DEMO__.isolated&&!window.__UX1_DEMO__.trace.some(x=>x.unsupported)));
 check('no runtime errors or remote requests',errors.length===0&&remote.length===0);
 console.log(JSON.stringify({checks:checks.length,output}));
 }catch(e){await shot('failure');throw e;}finally{await fs.writeFile(path.join(output,'report.json'),JSON.stringify({checks,errors,remote,measurements},null,2));await browser.close();}
}
run().catch(e=>{console.error(e);process.exitCode=1;});
