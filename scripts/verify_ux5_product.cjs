// Product React with authenticated Core in temporary data/keyring/workspace.
// Edge adapts native IPC; only provider generation is deterministic.
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const {randomUUID}=require('node:crypto');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {verifyManagementFeedback,verifyFastMode}=require('./ux5_feedback_checks.cjs');
async function main(){
 const feedbackQA=process.argv.includes('--feedback');
 const fixtureExtensions=['custom','mcp','skill'].map(kind=>({kind,name:`ux5_${kind}_English_sample`,enabled:false,removable:true,description:'Synthetic extension for layout checks only',source_label:'מקור בדיקה מבודד'}));
 const output=path.resolve(process.argv[3]||'.codex-local/ux-5/product');await fs.mkdir(output,{recursive:true});
 const token=randomUUID(),host=spawn('python',['scripts/ux3_core_host.py'],{windowsHide:true,env:{...process.env,UX3_TEST_TOKEN:token,UX4_WORKBENCH_QA:'1',PYTHONUTF8:'1'}});
 let stderr='';host.stderr.on('data',x=>stderr+=x);
 const handshake=await new Promise((resolve,reject)=>{let buffer='';const timer=setTimeout(()=>reject(Error('QA Core startup timed out')),45000);
  host.once('exit',code=>{clearTimeout(timer);reject(Error('QA Core exited '+code));});
  host.stdout.on('data',chunk=>{buffer+=chunk;for(const line of buffer.split('\n'))if(line.includes('"sample"')){try{const data=JSON.parse(line);clearTimeout(timer);resolve(data);}catch{}}});
 }).catch(error=>{host.stdin.end('shutdown\n');throw error;});
 const api=async(method,route,body,key=null)=>{const response=await fetch(`http://127.0.0.1:${handshake.port}${route}`,{method,signal:AbortSignal.timeout(30000),headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json',...(key?{'Idempotency-Key':key}:{})},body:method==='GET'?undefined:JSON.stringify(body||{})});return{status:response.status,body:await response.json()};};
 const get=async route=>(await api('GET',route)).body.data;
 const patch=async values=>{const response=await api('PATCH','/v2/settings',{values},randomUUID());assert.equal(response.status,200);};
 let browser,page,failSave=false,failMemory=false;const checks=[],errors=[],geometry=[],commands=[];
 const record=(name,ok)=>{assert.ok(ok,name);checks.push(name);console.log(name);};
 try{
  browser=await chromium.launch({channel:'msedge',headless:true});
  const context=await browser.newContext({viewport:{width:1380,height:900},permissions:['clipboard-read','clipboard-write']});page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  await page.exposeFunction('__qaInvoke',async(cmd,args={})=>{
   commands.push(cmd);
   if(cmd==='core_api'){const r=args.request;
    if(failSave&&r.method==='PATCH'&&r.path==='/v2/settings'&&r.body?.values?.email_from_name==='UX5 retry sender')return{status:503,body:{error:'isolated_save_failure',detail:'שמירה נכשלה בבדיקה המבודדת'}};
    if(failMemory&&r.method==='PATCH'&&r.path.startsWith('/v2/management/memories/')){failMemory=false;return{status:503,body:{error:'isolated_memory_failure',detail:'כשל מבודד'}};}
    const result=await api(r.method,r.path,r.body,r.idempotencyKey);
    if(r.method==='PATCH'&&r.path==='/v2/settings'&&r.body?.values?.email_from_name)await fs.writeFile(path.join(output,'email-save.json'),JSON.stringify({status:result.status,error:result.body.error,detail:result.body.detail,email:result.body.data?.values?.email_from_name},null,2));
    if(feedbackQA&&r.path==='/v2/management/tools'&&result.body.data)result.body.data.extensions=[...result.body.data.extensions,...fixtureExtensions];
    return result;
   }
   if(cmd==='core_status')return{state:handshake.state,generation:1,pid:handshake.pid,port:handshake.port,stderrTail:[]};
   if(cmd==='core_health')return handshake.health;
   if(cmd==='browser_status')return{tabs:[],available:true,profile_dir:handshake.workbench?.root};
   if(cmd==='desktop_diagnostic_snapshot')return{items:[]};
   if(cmd==='plugin:window|is_maximized')return false;
   if(cmd==='plugin:event|listen')return commands.length;
   if(['plugin:event|unlisten','desktop_finish_startup','desktop_set_close_to_tray','desktop_set_voice_hotkey','desktop_set_unread','desktop_notify'].includes(cmd))return true;
   if(cmd==='save_text_file'){await fs.writeFile(path.join(output,'export.txt'),args.contents);return true;}
   if(cmd==='pick_management_path')return null;
   throw Error('Unadapted native IPC: '+cmd);
  });
  await page.addInitScript(()=>{let id=0;window.__TAURI_INTERNALS__={metadata:{currentWindow:{label:'main'},currentWebview:{label:'main',windowLabel:'main'}},transformCallback:()=>++id,unregisterCallback:()=>{},invoke:(cmd,args)=>window.__qaInvoke(cmd,args)};window.__TAURI_EVENT_PLUGIN_INTERNALS__={unregisterListener:()=>{}};});
  const base=process.argv[2]||'http://127.0.0.1:1439';await page.goto(base);
  await page.getByRole('heading',{name:'מדיניות פרטיות ותנאי שימוש'}).waitFor();
  record('first launch requires explicit unchecked consent',await page.getByRole('button',{name:'אני מסכים',exact:true}).isDisabled());
  await page.screenshot({path:path.join(output,'legal-light.png')});
  await page.getByRole('checkbox').check();await page.getByRole('button',{name:'אני מסכים',exact:true}).click();await page.locator('.chat-column').waitFor();
  record('consent persists through actual Core authority',(await get('/v2/management/legal')).accepted);
  await patch({ui_preferences:{settings_show_advanced:true,theme_mode:'light'}});
  await page.locator('.conversation-select').filter({hasText:'מחקר לקראת המפגש'}).click();
  const draft=page.getByRole('textbox',{name:'הודעה',exact:true});await draft.fill('UX-5 retained draft');
  const chatScroll=page.locator('.messages');if(await chatScroll.count())await chatScroll.evaluate(e=>e.scrollTop=320);
  await page.getByRole('button',{name:'הגדרות',exact:true}).click();await page.locator('.management-overlay').waitFor();
  const nav=page.getByRole('navigation',{name:'ניווט הגדרות וניהול'});
  const go=async name=>{await nav.getByRole('button',{name,exact:true}).click();await page.waitForTimeout(180);};
  await page.getByRole('switch',{name:'הצג הגדרות מתקדמות',exact:true}).waitFor();
  record('loaded advanced state is preserved',await page.getByRole('switch',{name:'הצג הגדרות מתקדמות',exact:true}).isChecked());
  await page.locator('[data-setting-path="api_mode"] button').click();
  record('all eighteen real provider choices remain',(await page.getByRole('listbox',{name:'ספקי מודלים'}).getByRole('option').count())===18);
  await page.keyboard.press('Escape');
  const modelTrigger=page.locator('.source-model-picker > button');await modelTrigger.click();const picker=page.getByRole('dialog');
  record('model search receives keyboard focus',await picker.getByRole('searchbox',{name:'חפש מודל'}).evaluate(e=>e===document.activeElement));
  await page.keyboard.press('ArrowDown');record('model list supports keyboard selection',await picker.getByRole('option').first().evaluate(e=>e===document.activeElement));
  await page.keyboard.press('Escape');record('model Escape returns to trigger without closing management',await modelTrigger.evaluate(e=>e===document.activeElement)&&await page.locator('.management-overlay').isVisible());
  await page.getByPlaceholder('חפש הגדרה').fill('SSL');await page.getByRole('button',{name:/אמון HTTPS ורשת מסוננת/}).click();
  await page.getByText('המצב הפעיל כעת',{exact:true}).waitFor();record('cross-section search reaches advanced SSL',await nav.getByRole('button',{name:'מתקדם ומפתחים'}).getAttribute('aria-current')==='page');
  await page.getByRole('button',{name:'הגדר',exact:true}).click();await page.getByRole('button',{name:'ללא אימות',exact:true}).click();
  record('insecure SSL cannot silently apply without acknowledgement',!(await page.getByRole('switch',{name:/ברור לי/}).isChecked()));
  await page.locator('.source-ssl-editor').getByRole('button',{name:'ביטול',exact:true}).click();
  await go('כלים ותקשורת');const email=page.locator('[data-setting-path="email_from_name"] input');
  await email.waitFor();await email.fill('UX5 sender');await email.blur();
  for(let i=0;i<30&&(await get('/v2/settings')).values.email_from_name!=='UX5 sender';i++)await page.waitForTimeout(100);
  record('autosave persists to actual Core',(await get('/v2/settings')).values.email_from_name==='UX5 sender');
  record('routine save success remains silent',!await page.getByText('נשמר',{exact:true}).count());
  const address=page.locator('[data-setting-path="email_address"] input');await address.fill('qa@example.test');
  for(let i=0;i<30&&!(await get('/v2/settings')).secrets.email_address.configured;i++)await page.waitForTimeout(100);
  const protectedAddress=await get('/v2/settings');record('email address uses protected authority without plaintext readback',protectedAddress.secrets.email_address.configured&&!Object.hasOwn(protectedAddress.values,'email_address'));

  failSave=true;await email.fill('UX5 retry sender');await email.blur();await page.getByRole('alert').filter({hasText:'השמירה נכשלה'}).first().waitFor();
  record('failed setting keeps editable draft',await email.inputValue()==='UX5 retry sender');
  failSave=false;await email.focus();await email.blur();for(let i=0;i<30&&(await get('/v2/settings')).values.email_from_name!=='UX5 retry sender';i++)await page.waitForTimeout(100);record('explicit retry persists setting',(await get('/v2/settings')).values.email_from_name==='UX5 retry sender');
  await page.reload();await page.locator('.chat-column').waitFor();await page.getByRole('button',{name:'הגדרות',exact:true}).click();await go('כלים ותקשורת');
  record('reload retains saved setting',await page.locator('[data-setting-path="email_from_name"] input').inputValue()==='UX5 retry sender');
  await go('מרכז משימות');await page.locator('.sds-page-header').getByRole('button',{name:'משימה חדשה'}).click();
  await page.getByPlaceholder('מה Smarti יבצע?').fill('UX5 scheduled task');await page.locator('.task-create input[type="number"]').fill('1000');await page.getByRole('button',{name:'יצירת משימה',exact:true}).click();
  await page.locator('.management-cards article').filter({hasText:'UX5 scheduled task'}).waitFor();
  const task=(await get('/v2/management/tasks')).items.find(item=>item.prompt==='UX5 scheduled task');record('task creation keeps dedicated conversation target',task?.conversation_mode==='dedicated');
  await page.locator('.management-cards article').filter({hasText:'UX5 scheduled task'}).getByRole('button',{name:'עריכה',exact:true}).click();
  const td=page.getByRole('dialog');await td.getByRole('textbox').fill('UX5 edited task');await td.getByRole('button',{name:'שמירה',exact:true}).click();await td.waitFor({state:'hidden'});
  record('task edit persists',(await get('/v2/management/tasks')).items.some(item=>item.prompt==='UX5 edited task'));
  await go('זיכרונות');await page.getByRole('button',{name:'זיכרון חדש',exact:true}).click();let md=page.getByRole('dialog');await md.getByRole('textbox').first().fill('UX5 synthetic memory');await md.getByRole('button',{name:'שמירה',exact:true}).click();await md.waitFor({state:'hidden'});
  await page.locator('.management-cards article').filter({hasText:'UX5 synthetic memory'}).waitFor();record('real memory creation persists encrypted collection',(await get('/v2/management/memories')).items.some(item=>item.content==='UX5 synthetic memory'));
  const memoryDialogButton=page.getByRole('button',{name:'זיכרון חדש',exact:true});await memoryDialogButton.click();let focusDialog=page.getByRole('dialog');
  await focusDialog.getByRole('button',{name:'שמירה',exact:true}).focus();await page.keyboard.press('Tab');record('memory dialog contains Tab focus',await focusDialog.evaluate(e=>e.contains(document.activeElement)));await page.keyboard.press('Escape');record('dialog Escape returns focus and retains management',await memoryDialogButton.evaluate(e=>e===document.activeElement)&&await page.locator('.management-overlay').isVisible());
  const mem=page.locator('.management-cards article').filter({hasText:'UX5 synthetic memory'});await mem.getByRole('button',{name:'עריכה',exact:true}).click();md=page.getByRole('dialog');await md.getByRole('textbox').first().fill('UX5 recovered memory');failMemory=true;await md.getByRole('button',{name:'שמירה',exact:true}).click();await md.getByRole('alert').waitFor();record('failed memory edit keeps modal draft',await md.getByRole('textbox').first().inputValue()==='UX5 recovered memory');
  await md.getByRole('button',{name:'שמירה',exact:true}).click();await md.waitFor({state:'hidden'});record('memory retry succeeds',(await get('/v2/management/memories')).items.some(item=>item.content==='UX5 recovered memory'));
  await go('כלים וחיבורים');await page.locator('.management-overlay').getByRole('switch').first().waitFor();const toggle=page.locator('.management-overlay').getByRole('switch').first();const before=await toggle.isChecked();await toggle.click();await page.waitForTimeout(500);record('tool toggle reaches real trust/enable authority',await toggle.isChecked()!==before);await toggle.click();
  await page.getByPlaceholder('חיפוש כלים וחיבורים').fill('no_matching_ux5_tool');record('tool search filters catalog',await page.locator('.source-tool-row').count()===0);await page.getByPlaceholder('חיפוש כלים וחיבורים').fill('');
  const screens=['מודלי AI וספקים','אבטחה ופרטיות','כלים ותקשורת','קול, מראה ומערכת','מתקדם ומפתחים','סביבת עבודה ודפדפן','מרכז משימות','זיכרונות','כלים וחיבורים','נתוני שימוש','Smarti Diagnostic','מעקב למפתחים','אודות והסכמות'];
  for(const theme of ['light','dark']){
   await patch({ui_preferences:{theme_mode:theme}});await page.reload();await page.locator('.chat-column').waitFor();await page.getByRole('button',{name:'הגדרות',exact:true}).click();
   for(const width of [360,500,900,1380,1920]){
    await page.setViewportSize({width,height:900});
    for(const screen of screens){await go(screen);await page.waitForTimeout(150);
     const bounds=await page.locator('.management-overlay').evaluate(root=>{const r=root.getBoundingClientRect(),main=root.querySelector('.management-scroll-viewport');return{width:r.width,right:r.right,overflow:main.scrollWidth-main.clientWidth,buttons:[...root.querySelectorAll('button')].filter(e=>e.getClientRects().length).map(e=>({h:e.getBoundingClientRect().height,w:e.getBoundingClientRect().width})),legacy:root.querySelectorAll('.legacy-icon,.ui-button,.source-switch').length};});
     record(`${theme}/${width}/${screen} bounds and shared controls`,bounds.right<=width+1&&bounds.overflow<=1&&bounds.legacy===0&&bounds.buttons.every(b=>b.h>=39));geometry.push({theme,width,screen,...bounds});
     if(feedbackQA)geometry[geometry.length-1].feedback=await verifyManagementFeedback(page,record,`${theme}/${width}/${screen}`);
     if([360,1380].includes(width)&&['מודלי AI וספקים','זיכרונות','קול, מראה ומערכת'].includes(screen))await page.screenshot({path:path.join(output,`${theme}-${width}-${screens.indexOf(screen)}.png`)});
    }
   }
  }
  await page.setViewportSize({width:1380,height:900});await go('סביבת עבודה ודפדפן');record('startup maximization setting describes real behavior without writing old preference',!await page.getByRole('switch',{name:'פתיחה בחלון מוגדל'}).count());
  await page.getByRole('button',{name:'חזרה לצ׳אט',exact:true}).click();record('return to chat preserves draft',await draft.inputValue()==='UX-5 retained draft');
  if(feedbackQA){
   for(const theme of ['light','dark'])for(const model of ['ux3-local','ux5_very_long_local_model_name_for_physical_layout']){
    await patch({api_mode:'local',selected_local_model:model,selected_model_source:{local:'user'},model_selection_provenance_version:1,ui_preferences:{theme_mode:theme}});await page.evaluate(()=>{localStorage.clear();sessionStorage.clear();});await page.reload();await page.locator('.chat-column').waitFor();
    for(const width of [360,500,900,1380,1920]){
     await page.setViewportSize({width,height:900});await verifyFastMode(page,record,`${theme}/${width}/${model}`);
    }
   }
  }
  record('no renderer exceptions',errors.length===0);
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({checks,geometry,errors,native:'Edge IPC adapted; system dialogs/hardware/OAuth not exercised',version:browser.version()},null,2));
 }catch(error){if(page){await page.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});await fs.writeFile(path.join(output,'failure.json'),JSON.stringify({error:String(error),checks,errors},null,2));}throw error;}
 finally{await browser?.close();host.stdin.end('shutdown\n');const ended=new Promise(resolve=>host.once('exit',resolve));await Promise.race([ended,new Promise(resolve=>setTimeout(resolve,5000))]);if(host.exitCode===null)host.kill();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
