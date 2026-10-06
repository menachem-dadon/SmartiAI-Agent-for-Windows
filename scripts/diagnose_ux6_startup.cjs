// Bounded diagnostics in the already guarded QA WebView; never records bodies.
const {connectOwned}=require('./ux6_raw_cdp.cjs');
const fs=require('node:fs/promises'),path=require('node:path');
const assert=require('node:assert/strict');
async function main(){
 const q=await connectOwned('built'),out=path.resolve('.codex-local/ux-6/final/startup-diagnostic');await fs.mkdir(out,{recursive:true});
 const cycles=[];
 try{
  assert.equal(q.launch.deterministic,true,'Only explicit synthetic QA may be reloaded/recorded');
  for(let n=0;n<3;n++){
   await q.send('Page.reload');await q.waitFor("document.readyState==='complete'");
   let ok=true;try{await q.waitFor("!!document.querySelector('.chat-column')");}catch{ok=false;}
   cycles.push({n,ok});console.log('startup',n,ok);
   if(!ok){const screenshot=await q.send('Page.captureScreenshot');await fs.writeFile(path.join(out,'failure.png'),Buffer.from(screenshot.data,'base64'));break;}
  }
  await fs.writeFile(path.join(out,'bounded-report.json'),JSON.stringify({cycles,scope:'At most three actual synthetic QA root reloads; native invoke is read-only, no invocation instrumentation or fault-injection claim. Earlier diagnostic output is preserved.'},null,2));
  if(cycles.some(c=>!c.ok))process.exitCode=1;
 }finally{q.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
