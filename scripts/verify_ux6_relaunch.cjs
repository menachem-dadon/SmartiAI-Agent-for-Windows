const {connectOwned}=require('./ux6_raw_cdp.cjs');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process'),{randomUUID}=require('node:crypto');
async function main(){
 const mode=process.argv.includes('--dev')?'dev':'built',output=path.resolve(`.codex-local/ux-6/final/relaunch-${mode}`);await fs.mkdir(output,{recursive:true});
 let q=await connectOwned(mode);const checks=[],metrics=[],check=(name,ok)=>{assert.ok(ok,name);checks.push(name);console.log(name);};
 assert.notEqual(q.launch.deterministic,false,'Refusing automation on the live-provider user trial');
 const api=async(method,route,body)=>{const r=await q.invoke('core_api',{request:{method,path:route,body:body??null,idempotencyKey:method==='GET'?null:randomUUID()}});assert.equal(r.status,200);return r.body.data;};
 try{
  await q.waitFor("!!document.querySelector('.chat-column')");
  await api('PATCH','/v2/settings',{values:{email_from_name:'UX6 restart QA',updates_auto_check:false}});
  const consent=await api('GET','/v2/management/legal'),artifacts=await api('GET','/v2/workbench/artifacts');
  let previous=(await q.invoke('core_status')).pid;
  for(let n=0;n<3;n++){
   await q.invoke('desktop_quit').catch(()=>{});q.close();
   for(let tries=0;tries<40;tries++){
    const alive=execFileSync('pwsh',['-NoProfile','-Command',`[bool](Get-Process -Name 'ux6-${mode}' -ErrorAction SilentlyContinue)`],{windowsHide:true,encoding:'utf8'}).trim();
    if(alive==='False')break;if(tries===39)throw Error('Owned process did not quit');await new Promise(r=>setTimeout(r,100));
   }
   execFileSync('pwsh',['-NoProfile','-File','scripts/restart_ux6_native.ps1','-Mode',mode],{windowsHide:true,stdio:'ignore'});
   const deadline=Date.now()+30000;
   while(Date.now()<deadline){try{q=await connectOwned(mode);break;}catch(e){if(Date.now()+100>=deadline)throw e;await new Promise(r=>setTimeout(r,100));}}
   await q.waitFor("!!document.querySelector('.chat-column')");
   const status=await q.invoke('core_status');check(`${mode} relaunch ${n} starts new ready Core`,status.pid!==previous&&status.state==='ready');previous=status.pid;
   metrics.push({kind:'launch helper timestamp to observed ready root; includes CDP/identity probe overhead',ms:Date.now()-Date.parse(q.launch.launchUtc)});
   check(`${mode} relaunch ${n} retains settings and legal consent`,(await api('GET','/v2/settings')).values.email_from_name==='UX6 restart QA'&&(await api('GET','/v2/management/legal')).accepted===consent.accepted);
   check(`${mode} relaunch ${n} retains artifacts and starts empty workbench`,JSON.stringify((await api('GET','/v2/workbench/artifacts')).items)===JSON.stringify(artifacts.items)&&await q.evaluate("JSON.parse(sessionStorage.getItem('smarti-workbench-session-v2')).snapshot.tabs.length===0")&&(await q.invoke('browser_status')).tabs.length===0);
  }
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({checks,metrics,mode,scope:'actual owned process quit/reopen three times with same isolated data, private WebView profile and keyring; D43 drafts are WebView-session storage, D50 new app empty tabs; times are observed readiness upper bounds'},null,2));
 }catch(e){await fs.writeFile(path.join(output,'failure.json'),JSON.stringify({error:String(e),checks,metrics},null,2));throw e;}finally{q.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
