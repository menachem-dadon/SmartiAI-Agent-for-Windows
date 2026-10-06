// One ordinary reload of the final candidate; no native IPC monkeypatching.
const {connectOwned}=require('./ux6_raw_cdp.cjs');
const fs=require('node:fs/promises'),assert=require('node:assert/strict');
async function main(){
 const q=await connectOwned('built'),checks=[];let probe;
 try{
  assert.notEqual(q.launch.deterministic,false,'Refusing automation on the live-provider user trial');
  await q.waitFor("!!document.querySelector('.chat-column')");
  const before=await q.invoke('core_status');
  await q.evaluate("(()=>{const e=document.querySelector('.composer textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(e,'UX6 final recovery draft');e.dispatchEvent(new Event('input',{bubbles:true}));})()");
  const epoch=crypto.randomUUID();
  probe=await q.send('Page.addScriptToEvaluateOnNewDocument',{source:`window.__ux6StartupEpoch=${JSON.stringify(epoch)};`});
  await q.send('Page.reload');
  await q.waitFor(`window.__ux6StartupEpoch===${JSON.stringify(epoch)}`);
  await q.waitFor("!!document.querySelector('.chat-column')");
  assert.equal((await q.invoke('core_status')).pid,before.pid);checks.push('final built candidate reloads a new populated root without replacing Core');
  await q.send('Page.removeScriptToEvaluateOnNewDocument',{identifier:probe.identifier});
  probe=null;
  assert.equal(await q.evaluate("document.querySelector('.composer textarea').value"),'UX6 final recovery draft');
  assert.equal((await q.invoke('core_status')).pid,before.pid);checks.push('final candidate reload retains the active owner draft');
  await fs.writeFile('.codex-local/ux-6/final/lastchanges.json',JSON.stringify({checks,source_sha256:q.launch.source_sha256,executable_sha256:q.launch.sha256,scope:'actual final built Tauri QA; one ordinary reload with unique new-document marker. Native invoke is read-only, so attempted stall injection was ineffective and excluded. Watchdog is unit-tested only; original blank-screen cause unproved.'},null,2));
  console.log(checks.join('\n'));
 }finally{if(probe){await q.send('Page.removeScriptToEvaluateOnNewDocument',{identifier:probe.identifier}).catch(()=>{});await q.send('Page.reload').catch(()=>{});}q.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
