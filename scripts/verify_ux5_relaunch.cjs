// Restart only the verified isolated application. Preserve the same QA profile.
const {chromium}=require('playwright'),fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process'),{randomUUID}=require('node:crypto');
let browser;
async function main(){
 const output=path.resolve('.codex-local/ux-5');const checks=[],geometry=[];
 const check=(name,ok)=>{assert.ok(ok,name);checks.push(name);console.log(name);};
 const connect=async()=>{browser=await chromium.connectOverCDP('http://127.0.0.1:19457');const page=browser.contexts()[0].pages().find(p=>p.url().includes('127.0.0.1:1439'));assert.ok(page);const invoke=(cmd,args={})=>page.evaluate(({cmd,args})=>window.__TAURI_INTERNALS__.invoke(cmd,args),{cmd,args});assert.equal(await invoke('plugin:app|identifier'),'ai.smarti.ux5native');return{page,invoke};};
 let {page,invoke}=await connect();
 const api=async(method,route,body)=>{const r=await invoke('core_api',{request:{method,path:route,body:body??null,idempotencyKey:method==='GET'?null:randomUUID()}});assert.equal(r.status,200);return r.body.data;};
 const launch=JSON.parse(await fs.readFile(path.join(output,'native-launch.json'),'utf8'));
 const probe=()=>JSON.parse(String(execFileSync('pwsh',['-NoProfile','-File','scripts/probe_ux5_children.ps1','-ProbeProcessId',String(launch.pid)],{windowsHide:true})));
 await page.getByRole('button',{name:'חזרה לצ׳אט',exact:true}).click();
 const draft=page.getByRole('textbox',{name:'הודעה',exact:true});const beforeDraft=await draft.inputValue();
 await page.getByRole('button',{name:'פתיחת סביבת העבודה',exact:true}).click();await page.locator('.workbench-empty').getByRole('button',{name:'דפדפן',exact:true}).click();await page.locator('.embedded-browser').waitFor();await page.waitForTimeout(1100);
 const tabs=(await invoke('browser_status')).tabs,owner=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('smarti-workbench-session-v2')).snapshot.active);const tab=tabs.find(t=>t.workspaceId===owner);assert.ok(tab);
 const visible=probe();const view=await page.locator('.browser-viewport').boundingBox();const scale=await page.evaluate(()=>devicePixelRatio);
 const child=visible.find(w=>Math.abs(w.width-view.width*scale)<=3&&Math.abs(w.height-view.height*scale)<=3);check('actual browser child initially occupies workbench bounds',!!child&&child.x>=0);
 await page.getByRole('button',{name:'הגדרות',exact:true}).click();await page.waitForTimeout(600);
 const hidden=probe().find(w=>w.handle===child.handle);check('management moves actual native browser child outside client area',hidden.x+hidden.width<=0);geometry.push({visible:child,management:hidden});
 await page.getByRole('navigation',{name:'ניווט הגדרות וניהול'}).getByRole('button',{name:'זיכרונות',exact:true}).click();await page.getByRole('button',{name:'זיכרון חדש',exact:true}).click();await page.getByRole('dialog').waitFor();await page.getByRole('dialog').getByRole('button',{name:'ביטול',exact:true}).click();
 check('management dialog dismisses without closing page',await page.locator('.management-overlay').isVisible());
 await page.getByRole('button',{name:'חזרה לצ׳אט',exact:true}).click();await page.waitForTimeout(800);
 const restored=probe().find(w=>w.handle===child.handle);check('native browser returns with same owner and bounds',restored.x>=0&&restored.width===child.width&&restored.height===child.height&&(await invoke('browser_status')).tabs.some(t=>t.tabId===tab.tabId));
 check('browser management round trip retains draft',await draft.inputValue()===beforeDraft);
 const before=await api('GET','/v2/settings'),consent=await api('GET','/v2/management/legal'),artifacts=await api('GET','/v2/workbench/artifacts');
 const disk=JSON.parse(await fs.readFile(path.join(launch.data,'smarti_settings.json'),'utf8'));
 check('native saved value is present on QA disk',disk.email_from_name==='UX-5 native sender');
 await invoke('desktop_quit').catch(()=>{});await browser.close().catch(()=>{});
 execFileSync('pwsh',['-NoProfile','-File','scripts/restart_ux5_native.ps1'],{windowsHide:true,stdio:'ignore'});
 for(let n=0;n<40;n++){try{({page,invoke}=await connect());break;}catch(error){await browser?.close().catch(()=>{});if(n===39)throw error;await new Promise(resolve=>setTimeout(resolve,250));}}
 await page.locator('.chat-column').waitFor();const after=await api('GET','/v2/settings');
 check('setting and advanced mode survive actual process restart',after.values.email_from_name===before.values.email_from_name&&after.values.ui_preferences.settings_show_advanced===true);
 check('historical maximization preference is retained without startup maximize',after.values.ui_preferences.workspace_start_maximized===true&&!(await invoke('plugin:window|is_maximized')));
 check('agreement remains accepted after process restart',(await api('GET','/v2/management/legal')).accepted===consent.accepted);
 const session=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('smarti-workbench-session-v2')));check('new session starts with empty workbench and no browser targets',session.snapshot.tabs.length===0&&(await invoke('browser_status')).tabs.length===0);
 check('Core artifacts survive process restart',JSON.stringify((await api('GET','/v2/workbench/artifacts')).items)===JSON.stringify(artifacts.items));
 await invoke('desktop_focus_main');await page.getByRole('button',{name:'הגדרות',exact:true}).click();
 await fs.writeFile(path.join(output,'native-relaunch.json'),JSON.stringify({checks,geometry,scope:'actual isolated quit/relaunch, native child geometry at measured DPI; no external dialogs, account or hardware'},null,2));
 await browser.close();
}
main().catch(async error=>{console.error(error);await browser?.close().catch(()=>{});process.exitCode=1;});
