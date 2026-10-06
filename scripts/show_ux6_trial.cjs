// Run only after automated UI QA. This helper never reads account/key fields.
const {connectOwned}=require('./ux6_raw_cdp.cjs');
const path=require('node:path'),fs=require('node:fs/promises'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
async function main(){
 const q=await connectOwned('built');
 try{
  assert.equal(q.launch.deterministic,false,'Restart with -LiveProviders first');
  const root=path.join(q.launch.data,'workspace');
  await q.invoke('core_api',{request:{method:'PATCH',path:'/v2/workbench/root',body:{path:root},idempotencyKey:crypto.randomUUID()}});
  await q.invoke('core_api',{request:{method:'PATCH',path:'/v2/settings',body:{values:{updates_auto_check:false,voice_hotkey:'',ui_preferences:{theme_mode:'light',settings_show_advanced:true,workspace_sidebar_collapsed:false}}},idempotencyKey:crypto.randomUUID()}});
  await q.send('Page.reload');await q.waitFor("!!document.querySelector('.chat-column')");
  // QA session marker only: no production source or design tokens are replaced.
  await q.send('Page.addScriptToEvaluateOnNewDocument',{source:`document.addEventListener('DOMContentLoaded',()=>{const observer=new MutationObserver(()=>{const root=document.querySelector('.chat-design');if(root&&!document.getElementById('ux6-qa-label')){const label=document.createElement('div');label.id='ux6-qa-label';label.textContent='UX6 QA • נתונים מבודדים';label.style.cssText='position:fixed;top:36px;left:90px;z-index:9999;pointer-events:none;padding:4px 8px;background:var(--sds-color-surface);color:var(--sds-color-text);border:1px solid var(--sds-color-border);border-radius:var(--sds-radius-control);font:var(--sds-font-caption) var(--sds-font-family)';root.append(label);}});observer.observe(document.body,{childList:true,subtree:true});});`});
  await q.send('Page.reload');await q.waitFor("!!document.getElementById('ux6-qa-label')&&!!document.querySelector('.chat-column')");
  execFileSync('pwsh',['-NoProfile','-File','scripts/resize_ux6_window.ps1','-ProbeProcessId',String(q.launch.pid),'-Width','1280','-Height','750'],{windowsHide:true,stdio:'ignore'});
  await q.invoke('desktop_focus_main');
  await q.evaluate("[...document.querySelectorAll('button')].find(e=>e.getAttribute('aria-label')==='הגדרות'||e.textContent.trim()==='הגדרות')?.click()");
  await q.waitFor("!!document.querySelector('.management-overlay')");
  await fs.writeFile('.codex-local/ux-6/trial-ready.json',JSON.stringify({source_sha256:q.launch.source_sha256,executable_sha256:q.launch.sha256,mode:'built frontend / source Core, live providers',label:'UX6 QA • נתונים מבודדים',profile:'native QA, ephemeral provider keyring and private CODEX_HOME',user_checks:'docs/ux6_user_checklist.md',scope:'UI automation is finished. No secrets were read. No personal installation.'},null,2));
  console.log('Isolated live-provider QA window is ready; automation closed');
 }finally{q.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
