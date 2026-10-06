const {connectOwned}=require('./ux6_raw_cdp.cjs');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {randomUUID}=require('node:crypto'),{performance}=require('node:perf_hooks');
async function main(){
 const output=path.resolve('.codex-local/ux-6/final/dev-stability');await fs.mkdir(output,{recursive:true});
 const q=await connectOwned('dev'),checks=[],metrics=[];
 assert.equal(q.launch.deterministic,true,'No mutation or recording of an account trial');
 const api=(method,route,body)=>q.invoke('core_api',{request:{method,path:route,body:body??null,idempotencyKey:method==='GET'?null:randomUUID()}});
 const ready=()=>q.waitFor("!!document.querySelector('.chat-column')");
 const check=(name,ok)=>{assert.ok(ok,name);checks.push(name);console.log(name);};
 const root=path.resolve('.codex-local/ux-6/frozen-after/desktop');
 assert.equal(q.launch.devUrl,'http://127.0.0.1:1448');
 const css=path.join(root,'src/interfaceRecovery.css'),js=path.join(root,'src/App.tsx');
 const originalCss=await fs.readFile(css,'utf8'),originalJs=await fs.readFile(js,'utf8');
 try{
  const legal=(await api('GET','/v2/management/legal')).body.data;
  if(!legal.accepted){await api('POST','/v2/management/legal',{accepted:true,version:legal.version});}
  await q.send('Page.reload');
  await ready();const status=await q.invoke('core_status');
  for(let n=0;n<10;n++){
   const start=performance.now();await q.send('Page.reload');
   await q.waitFor("document.readyState==='complete'&&!!document.querySelector('.chat-column')");
   metrics.push({kind:'actual dev WebView reload',ms:performance.now()-start});
  }
  check('ten actual dev reloads retain populated root and Core PID',(await q.invoke('core_status')).pid===status.pid);
  await q.evaluate("(()=>{const e=document.querySelector('.composer textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(e,'UX6 HMR retained draft');e.dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('.chat-stage').scrollTop=40;})()");
  const before=await q.evaluate("({draft:document.querySelector('.composer textarea').value,scroll:document.querySelector('.chat-stage').scrollTop})");
  const marker=randomUUID().replaceAll('-','');
  let start=performance.now();await fs.writeFile(css,originalCss+`\nhtml { --ux6-hmr-probe: ${marker}; }\n`);
  await q.waitFor(`getComputedStyle(document.documentElement).getPropertyValue('--ux6-hmr-probe').trim()==='${marker}'`);metrics.push({kind:'actual CSS HMR',ms:performance.now()-start});
  start=performance.now();await fs.writeFile(js,originalJs+`\ndocument.documentElement.dataset.ux6Hmr=${JSON.stringify(marker)};\n`);
  await q.waitFor(`document.documentElement.dataset.ux6Hmr==='${marker}'`);await ready();metrics.push({kind:'actual React HMR',ms:performance.now()-start});
  const after=await q.evaluate("({draft:document.querySelector('.composer textarea').value,scroll:document.querySelector('.chat-stage').scrollTop})");
  check('actual CSS and React HMR preserve draft, scroll and Core',JSON.stringify(after)===JSON.stringify(before)&&(await q.invoke('core_status')).pid===status.pid);
  const workerTargets=await(await fetch(q.launch.cdp+'/json/list')).json();
  const errors=q.events.filter(e=>e.method==='Runtime.exceptionThrown');check('ordinary dev lifecycle has no JavaScript exceptions',errors.length===0);
  const image=await q.send('Page.captureScreenshot',{format:'png'});await fs.writeFile(path.join(output,'dev.png'),Buffer.from(image.data,'base64'));
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({checks,metrics,errors,sharedWorkerPresent:workerTargets.some(t=>t.type==='shared_worker'),corePid:status.pid,scope:'actual isolated Tauri dev/WebView2/Core on frozen current source; direct CDP, Vite worker unchanged; CSS/React HMR mutations in owned snapshot only; original UX5 blank root not reproduced'},null,2));
 }catch(e){await fs.writeFile(path.join(output,'failure.json'),JSON.stringify({error:String(e),checks,metrics},null,2));throw e;}
 finally{await fs.writeFile(css,originalCss);await fs.writeFile(js,originalJs);q.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
