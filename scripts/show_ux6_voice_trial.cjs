// Fresh voice-only QA. Real microphone/transcription; deterministic model, no account.
const {connectOwned}=require('./ux6_raw_cdp.cjs');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
async function main(){
 const mode=process.argv.includes('--refined')?'voicefinal':'voice';
 const label=mode==='voicefinal'?'UX6 QA • קול מעודכן':'UX6 QA • בדיקת קול מבודדת';
 const q=await connectOwned(mode);
 try{
  assert.equal(q.launch.deterministic,true);
  await q.invoke('core_api',{request:{method:'PATCH',path:'/v2/workbench/root',body:{path:path.join(q.launch.data,'workspace')},idempotencyKey:crypto.randomUUID()}});
  await q.invoke('core_api',{request:{method:'PATCH',path:'/v2/settings',body:{values:{voice_hotkey:'',updates_auto_check:false}},idempotencyKey:crypto.randomUUID()}});
  await q.send('Page.addScriptToEvaluateOnNewDocument',{source:`document.addEventListener('DOMContentLoaded',()=>{const observer=new MutationObserver(()=>{const root=document.querySelector('.chat-design');if(root&&!document.getElementById('ux6-qa-label')){const label=document.createElement('div');label.id='ux6-qa-label';label.textContent=${JSON.stringify(label)};label.style.cssText='position:fixed;top:36px;left:90px;z-index:9999;pointer-events:none;padding:4px 8px;background:var(--sds-color-surface);color:var(--sds-color-text);border:1px solid var(--sds-color-border);border-radius:var(--sds-radius-control);font:var(--sds-font-caption) var(--sds-font-family)';root.append(label);}});observer.observe(document.body,{childList:true,subtree:true});});`});
  await q.send('Page.reload');await q.waitFor("!!document.getElementById('ux6-qa-label')&&!!document.querySelector('.chat-column')");
  execFileSync('pwsh',['-NoProfile','-File','scripts/resize_ux6_window.ps1','-Mode',mode,'-ProbeProcessId',String(q.launch.pid),'-Width','1280','-Height','750'],{windowsHide:true,stdio:'ignore'});
  await q.invoke('desktop_focus_main');
  await fs.writeFile(`.codex-local/ux-6/${mode}-trial-ready.json`,JSON.stringify({source_sha256:q.launch.source_sha256,executable_sha256:q.launch.sha256,label,scope:'Real microphone/transcription and built Windows overlay; deterministic model response. No login, personal profile or account reads. Original account trial left intact.'},null,2));
  console.log('Separate voice QA is visible; no account or microphone automation');
 }finally{q.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
