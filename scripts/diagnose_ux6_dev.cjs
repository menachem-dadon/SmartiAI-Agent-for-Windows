const fs=require('node:fs/promises');
async function main(){
 const q=await require('./ux6_raw_cdp.cjs').connectOwned('dev');
 try{
  require('node:assert/strict').equal(q.launch.deterministic,true,'Never record a live-provider/account trial');
  await q.send('Network.enable');await q.send('Log.enable');await q.send('Page.reload');await new Promise(r=>setTimeout(r,5000));
  const d={dom:await q.evaluate(`({url:location.href,ready:document.readyState,root:document.querySelector('#root')?.innerHTML,body:document.body.innerText.slice(0,2400),resources:performance.getEntriesByType('resource').filter(e=>e.initiatorType==='script').map(e=>({name:e.name,status:e.responseStatus,duration:e.duration}))})`),events:q.events.filter(e=>['Runtime.exceptionThrown','Network.loadingFailed','Log.entryAdded'].includes(e.method))};
  await fs.mkdir('.codex-local/ux-6/final/dev-diagnosis',{recursive:true});await fs.writeFile('.codex-local/ux-6/final/dev-diagnosis/failure.json',JSON.stringify(d,null,2));
  const s=await q.send('Page.captureScreenshot');await fs.writeFile('.codex-local/ux-6/final/dev-diagnosis/failure.png',Buffer.from(s.data,'base64'));console.log(JSON.stringify({body:d.dom.body,rootLength:d.dom.root?.length,events:d.events}));
 }finally{q.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
