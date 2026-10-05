// A real application restart with the same isolated profile, without clearing UI storage.
const {chromium}=require('playwright'),fs=require('node:fs/promises'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process'),{randomUUID}=require('node:crypto');
let activeBrowser;
async function main(){
 const connect=async()=>{const b=await chromium.connectOverCDP('http://127.0.0.1:19446');activeBrowser=b;const page=b.contexts()[0].pages().find(p=>p.url().includes('localhost:1420'));assert.ok(page);const invoke=(cmd,args={})=>page.evaluate(({cmd,args})=>window.__TAURI_INTERNALS__.invoke(cmd,args),{cmd,args});assert.equal(await invoke('plugin:app|identifier'),'ai.smarti.ux4native');return {b,page,invoke};};
 let {b,page,invoke}=await connect();
 await invoke('desktop_focus_main');
 await page.locator('.chat-column').waitFor({timeout:30000});
 if(!await page.locator('.workbench-tabs [role=tab]').count()){
  await page.getByRole('button',{name:'פתיחת סביבת העבודה',exact:true}).click();await page.locator('.workbench-empty').getByRole('button',{name:'קבצים',exact:true}).click();await page.waitForTimeout(250);
 }
 const before=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('smarti-workbench-session-v2')));assert.ok(before.snapshot.tabs.length>0);
 const legacy={tabs:[{id:'legacy-files',kind:'files',title:'קבצים'}],active:'legacy-files'};
 const patch=await invoke('core_api',{request:{method:'PATCH',path:'/v2/settings',body:{values:{ui_preferences:{workspace_workbench:legacy,workspace_workbench_open:true}}},idempotencyKey:randomUUID()}});assert.equal(patch.status,200);
 const originalArtifacts=await invoke('core_api',{request:{method:'GET',path:'/v2/workbench/artifacts',body:null,idempotencyKey:null}});assert.equal(originalArtifacts.status,200);
 await invoke('desktop_quit').catch(()=>{});await b.close().catch(()=>{});
 execFileSync('pwsh',['-NoProfile','-File','scripts/restart_ux4_native.ps1'],{windowsHide:true,stdio:'ignore'});
 const pid=JSON.parse(await fs.readFile('.codex-local/ux-4/native-launch.json','utf8')).pid;
 for(let attempt=0;attempt<40;attempt++){try{({b,page,invoke}=await connect());break;}catch(error){if(attempt===39)throw error;await new Promise(resolve=>setTimeout(resolve,250));}}
 await invoke('desktop_focus_main');
 await page.locator('.chat-column').waitFor({timeout:30000});await page.waitForTimeout(250);
 const after=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('smarti-workbench-session-v2')));
 assert.equal(after.snapshot.tabs.length,0);assert.equal(after.open,false);assert.notEqual(after.owner,before.owner);
 const artifacts=await invoke('core_api',{request:{method:'GET',path:'/v2/workbench/artifacts',body:null,idempotencyKey:null}});assert.deepEqual(artifacts.body.data.items,originalArtifacts.body.data.items);
 const settings=await invoke('core_api',{request:{method:'GET',path:'/v2/settings',body:null,idempotencyKey:null}});assert.deepEqual(settings.body.data.values.ui_preferences.workspace_workbench,legacy);assert.equal(settings.body.data.values.ui_preferences.workspace_workbench_open,true);
 const browser=await invoke('browser_status');assert.equal(browser.tabs.length,0);
 await fs.writeFile('.codex-local/ux-4/native-relaunch.json',JSON.stringify({ok:true,pid,checks:5,newOwner:true,emptyTabs:true,closedPanel:true,artifactsUnchanged:true,legacyPreferencesRetained:true,noBrowserLaunched:true},null,2));
 await invoke('desktop_quit').catch(()=>{});await b.close().catch(()=>{});console.log('Five native relaunch checks passed; QA app quit.');
}
main().catch(async error=>{console.error(error.stack);await activeBrowser?.close().catch(()=>{});process.exitCode=1;});
