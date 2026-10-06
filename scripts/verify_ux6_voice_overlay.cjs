// Actual first native window creation, without microphone or account access.
const {connectOwned}=require('./ux6_raw_cdp.cjs');
const fs=require('node:fs/promises'),assert=require('node:assert/strict');
async function main(){
 const mode=process.argv.includes('--refined')?'voicefinal':'voice';
 const q=await connectOwned(mode);
 try{
  assert.equal(q.launch.deterministic,true);
  const before=await q.invoke('core_status');
  assert.equal(before.state,'ready');
  const legal=await q.invoke('core_api',{request:{method:'GET',path:'/v2/management/legal',body:null,idempotencyKey:null}});
  if(!legal.body.data.accepted)await q.invoke('core_api',{request:{method:'POST',path:'/v2/management/legal',body:{accepted:true,version:legal.body.data.version},idempotencyKey:crypto.randomUUID()}});
  await q.send('Page.reload');await q.waitFor("!!document.querySelector('.chat-column')");
  const start=performance.now();await q.invoke('desktop_show_voice_overlay');const ms=performance.now()-start;
  assert.ok(ms<5000,'First voice window command returns, no synchronous creation deadlock');
  const targets=await(await fetch(q.launch.cdp+'/json/list')).json();
  const overlay=targets.find(t=>t.url.includes('voice-overlay=1'));
  assert.ok(overlay,'Actual voice WebView was created');
  await q.invoke('desktop_hide_voice_overlay');
  assert.equal((await q.invoke('core_status')).pid,before.pid);
  await fs.writeFile(`.codex-local/ux-6/${mode}-native.json`,JSON.stringify({checks:['first asynchronous native voice-window creation returns','actual voice WebView exists','overlay closes and same Core remains available'],ms,source_sha256:q.launch.source_sha256,executable_sha256:q.launch.sha256,scope:'actual separate built Tauri QA, fresh profile and first voice window; no microphone capture, account or transcription read; actual dictation/visual polish requires user trial'},null,2));
  console.log('Native voice window creation, close and Core check passed: '+ms.toFixed(1)+'ms');
 }finally{q.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
