// Actual UX-5 WebView2/Rust/Core. Verify isolated identity before any mutation.
const {chromium}=require('playwright');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process'),{randomUUID}=require('node:crypto');
const {verifyManagementFeedback,verifyFastMode}=require('./ux5_feedback_checks.cjs');
async function main(){
 const feedbackQA=process.argv.includes('--feedback');
 const output=path.resolve(process.argv[3]||'.codex-local/ux-5/native');await fs.mkdir(output,{recursive:true});
 const launch=JSON.parse(await fs.readFile('.codex-local/ux-5/native-launch.json','utf8'));
 assert.match(String(launch.pid),/^\d+$/);
 const executable=String(execFileSync('pwsh',['-NoProfile','-Command',`[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); (Get-Process -Id ${launch.pid}).Path`],{windowsHide:true})).trim();
 assert.equal(path.win32.basename(executable).toLowerCase(),'ux5-native.exe');assert.equal(path.resolve(executable),path.resolve(launch.executable));
 const data=path.resolve(launch.data),allowed=path.resolve('.codex-local/ux-5');assert.ok(data.startsWith(allowed+path.sep));
 const browser=await chromium.connectOverCDP(process.argv[2]||'http://127.0.0.1:19457');
 const page=browser.contexts()[0].pages().find(p=>p.url().includes('127.0.0.1:1439'));assert.ok(page,'owned Vite page');
 const invoke=(cmd,args={})=>page.evaluate(({cmd,args})=>window.__TAURI_INTERNALS__.invoke(cmd,args),{cmd,args});
 assert.equal(await invoke('plugin:app|identifier'),'ai.smarti.ux5native');
 const api=async(method,route,body)=>{const r=await invoke('core_api',{request:{method,path:route,body:body??null,idempotencyKey:method==='GET'?null:randomUUID()}});assert.ok(r.status>=200&&r.status<300,route+': '+r.status+' '+r.body.detail);return r.body.data;};
 const checks=[],errors=[],geometry=[];page.on('pageerror',e=>errors.push(e.message));
 const check=(name,ok)=>{assert.ok(ok,name);checks.push(name);console.log(name);};
 const nav=page.getByRole('navigation',{name:'ניווט הגדרות וניהול'});
 const go=async name=>{await nav.getByRole('button',{name,exact:true}).click();await page.waitForTimeout(220);};
 const resize=width=>JSON.parse(String(execFileSync('pwsh',['-NoProfile','-File','scripts/resize_ux5_window.ps1','-ProbeProcessId',String(launch.pid),'-Width',String(width),'-Height','900'],{windowsHide:true})));
 try{
  resize(1380);
  await page.reload();let status;for(let n=0;n<100;n++){status=await invoke('core_status');if(status.state==='ready')break;await page.waitForTimeout(250);}assert.equal(status.state,'ready');
  const legal=await api('GET','/v2/management/legal');if(!legal.accepted){check('native agreement initially unchecked',!await page.getByRole('checkbox').isChecked());await page.getByRole('checkbox').check();await page.getByRole('button',{name:'אני מסכים',exact:true}).click();}
  await page.locator('.chat-column').waitFor();
  const root=path.join(data,'workspace');await fs.mkdir(root,{recursive:true});
  await api('PATCH','/v2/workbench/root',{path:root});
  await api('PATCH','/v2/settings',{values:{updates_auto_check:false,ui_preferences:{theme_mode:'light',settings_show_advanced:true,workspace_sidebar_collapsed:false}}});
  const title='UX-5 isolated trial',existing=(await api('GET','/v2/conversations')).items.find(item=>item.title===title);
  const conversation=existing||(await api('POST','/v2/conversations',{title})).conversation;
  if(!existing)await api('POST',`/v2/conversations/${conversation.id}/runs`,{text:'סביבה מבודדת להתנסות בניהול והגדרות'});
  await page.reload();await page.locator('.chat-column').waitFor();await page.locator('.conversation-select').filter({hasText:title}).click();
  const draft=page.getByRole('textbox',{name:'הודעה',exact:true});await draft.fill('טיוטה שנשמרת בזמן ניהול');
  resize(1380);await page.getByRole('button',{name:'הגדרות',exact:true}).click();
  await page.getByRole('switch',{name:'הצג הגדרות מתקדמות',exact:true}).waitFor();
  check('native saved advanced visibility',await page.getByRole('switch',{name:'הצג הגדרות מתקדמות',exact:true}).isChecked());
  await go('כלים ותקשורת');const sender=page.locator('[data-setting-path="email_from_name"] input');await sender.fill('UX-5 native sender');await sender.blur();
  for(let n=0;n<40&&(await api('GET','/v2/settings')).values.email_from_name!=='UX-5 native sender';n++)await page.waitForTimeout(100);
  check('native setting writes through Rust to actual Core',(await api('GET','/v2/settings')).values.email_from_name==='UX-5 native sender');
  await page.reload();await page.locator('.chat-column').waitFor();await page.getByRole('button',{name:'הגדרות',exact:true}).click();await go('כלים ותקשורת');
  check('native saved setting survives reload',await page.locator('[data-setting-path="email_from_name"] input').inputValue()==='UX-5 native sender');
  const screens=['מודלי AI וספקים','אבטחה ופרטיות','כלים ותקשורת','קול, מראה ומערכת','מתקדם ומפתחים','סביבת עבודה ודפדפן','מרכז משימות','זיכרונות','כלים וחיבורים','נתוני שימוש','Smarti Diagnostic','מעקב למפתחים','אודות והסכמות'];
  for(const theme of ['light','dark']){
   await api('PATCH','/v2/settings',{values:{ui_preferences:{theme_mode:theme}}});await page.reload();await page.locator('.chat-column').waitFor();await page.getByRole('button',{name:'הגדרות',exact:true}).click();
   for(const width of [360,900,1380]){
    const resized=resize(width);await page.waitForTimeout(450);
    for(const screen of screens){await go(screen);
     const g=await page.locator('.management-overlay').evaluate(root=>{const main=root.querySelector('.management-scroll-viewport');return{viewport:innerWidth,scale:devicePixelRatio,overflow:main.scrollWidth-main.clientWidth,right:root.getBoundingClientRect().right,legacy:root.querySelectorAll('.legacy-icon,.ui-button,.source-switch').length};});
     check(`native ${theme}/${width}/${screen} bounds`,Math.abs(g.viewport-width)<2&&g.right<=width+1&&g.overflow<=1&&g.legacy===0);geometry.push({theme,width,screen,...g,resized});
     if(feedbackQA)geometry[geometry.length-1].feedback=await verifyManagementFeedback(page,check,`native ${theme}/${width}/${screen}`,false);
     if(width===1380&&['מודלי AI וספקים','זיכרונות','קול, מראה ומערכת'].includes(screen))await page.screenshot({path:path.join(output,`${theme}-${screens.indexOf(screen)}.png`)});
    }
   }
  }
  resize(1380);await go('קול, מראה ומערכת');
  const rtl=await page.locator('[data-setting-path="read_aloud_all"] .sds-switch').evaluate(e=>{const t=e.querySelector('.sds-switch-track').getBoundingClientRect(),thumb=e.querySelector('.sds-switch-thumb').getBoundingClientRect();return{checked:e.querySelector('input').checked,thumb:thumb.x+t.width/2,center:t.x+t.width/2,thumbCenter:thumb.x+thumb.width/2};});
  check('native RTL switch thumb has correct physical side',rtl.checked?rtl.thumbCenter<rtl.center:rtl.thumbCenter>rtl.center);
  await page.getByRole('button',{name:'חזרה לצ׳אט',exact:true}).click();check('native management round trip preserves chat draft',await draft.inputValue()==='טיוטה שנשמרת בזמן ניהול');
  if(feedbackQA){
   for(const theme of ['light','dark'])for(const model of ['ux5-local','ux5_very_long_local_model_name_for_physical_layout']){
    await api('PATCH','/v2/settings',{values:{api_mode:'local',selected_local_model:model,selected_model_source:{local:'user'},model_selection_provenance_version:1,ui_preferences:{theme_mode:theme}}});await page.evaluate(()=>{localStorage.clear();sessionStorage.clear();});await page.reload();await page.locator('.chat-column').waitFor();
    for(const width of [360,900,1380]){resize(width);await page.waitForTimeout(150);await verifyFastMode(page,check,`native ${theme}/${width}/${model}`);}
   }
   await api('PATCH','/v2/settings',{values:{selected_local_model:'ux5-local',ui_preferences:{theme_mode:'light'}}});await page.reload();await page.locator('.chat-column').waitFor();
  }
  // Leave the prepared QA app visible on settings for central review.
  await invoke('desktop_focus_main');await page.getByRole('button',{name:'הגדרות',exact:true}).click();await go('מודלי AI וספקים');
  check('native Core identity unchanged',status.pid===(await invoke('core_status')).pid);
  check('zero native renderer errors',errors.length===0);
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({checks,errors,geometry,webview:browser.version(),data,scope:'isolated actual Rust/Core/WebView2; Windows DPI measured, no system dialogs/real providers/audio/package',openWith:'compiled from f1446ac fixed GUI dispatch; user observation remains ledger §34'},null,2));
 }catch(error){await page.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});await fs.writeFile(path.join(output,'failure.json'),JSON.stringify({error:String(error),checks,errors},null,2));throw error;}
 finally{await browser.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
