// Real isolated Tauri/Core processes. No personal app, profile or provider calls.
const fs = require('node:fs/promises');
const path = require('node:path');
const net = require('node:net');
const {spawn, execFileSync} = require('node:child_process');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..'), output = path.join(root, '.codex-local/startup');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const alive = pid => { try { process.kill(pid, 0); return true; } catch { return false; } };
async function until(check, timeout=30000) { const end=Date.now()+timeout; while(Date.now()<end) { if(await check())return; await pause(100); } throw Error('Verification deadline'); }
async function freePort() { return new Promise(resolve => { const server=net.createServer(); server.listen(0,'127.0.0.1',()=>{const port=server.address().port;server.close(()=>resolve(port));}); }); }

async function connect(port, identifier) {
  let target;
  await until(async()=>{try{const items=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();target=items.find(t=>t.type==='page'&&!t.url.includes('voice-overlay'));return !!target;}catch{return false;}});
  const ws=new WebSocket(target.webSocketDebuggerUrl), pending=new Map(); let id=0;
  await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
  ws.addEventListener('message',({data})=>{const item=JSON.parse(data),task=pending.get(item.id);if(task){clearTimeout(task.timer);pending.delete(item.id);item.error?task.reject(Error(JSON.stringify(item.error))):task.resolve(item.result);}});
  ws.addEventListener('close',()=>{for(const task of pending.values()){clearTimeout(task.timer);task.reject(Error('Owned app disconnected'));}pending.clear();});
  const send=(method,params={})=>new Promise((resolve,reject)=>{const request=++id,timer=setTimeout(()=>{pending.delete(request);reject(Error('CDP timeout: '+method));},30000);pending.set(request,{resolve,reject,timer});ws.send(JSON.stringify({id:request,method,params}));});
  const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value;};
  const invoke=(command,args={})=>evaluate(`window.__TAURI_INTERNALS__.invoke(${JSON.stringify(command)},${JSON.stringify(args)})`);
  await send('Runtime.enable'); await send('Page.enable');
  await until(()=>evaluate('!!window.__TAURI_INTERNALS__').catch(()=>false));
  assert.equal(await invoke('plugin:app|identifier'),identifier);
  return {send,evaluate,invoke,close:()=>ws.close(),wait:expression=>until(()=>evaluate(expression).catch(()=>false)),screenshot:async name=>{const r=await send('Page.captureScreenshot');await fs.writeFile(path.join(output,name),Buffer.from(r.data,'base64'));}};
}

async function main() {
  await fs.mkdir(output,{recursive:true});
  const build=JSON.parse((await fs.readFile(path.join(output,'native-build.json'),'utf8')).replace(/^\uFEFF/,''));
  assert.equal(build.identifier,'ai.smarti.startupqa');
  assert.equal(path.basename(build.executable),'smarti-startup-qa.exe');
  const cases=[],owned=[];
  async function launch(name,{delay=0,missing=false,theme='light'}={}) {
    const data=path.join(output,'data-'+name+'-'+Date.now()),project=path.join(data,'project'),isolation=path.join(data,'python');
    await fs.mkdir(project,{recursive:true}); await fs.mkdir(isolation,{recursive:true});
    await fs.writeFile(path.join(isolation,'sitecustomize.py'),`import keyring\nfrom keyring.backend import KeyringBackend\nclass IsolatedKeyring(KeyringBackend):\n    priority=1\n    def get_password(self,*args): return None\n    def set_password(self,*args): pass\n    def delete_password(self,*args): pass\nkeyring.set_keyring(IsolatedKeyring())\n`);
    await fs.writeFile(path.join(project,'smarti_core_service.py'),`import time,runpy,sys\ntime.sleep(${delay})\nsys.path.insert(0,${JSON.stringify(root)})\nrunpy.run_path(${JSON.stringify(path.join(root,'smarti_core_service.py'))},run_name='__main__')\n`);
    await fs.writeFile(path.join(data,'smarti_settings.json'),JSON.stringify({api_mode:'local',selected_local_model:'startup-qa',updates_auto_check:false,ui_preferences:{theme_mode:theme}}));
    const placement=path.join(data,'tauri-desktop/data');await fs.mkdir(placement,{recursive:true});
    await fs.writeFile(path.join(placement,'window-placement.json'),JSON.stringify({layout_version:1,x:120,y:100,width:1000,height:740,maximized:false}));
    const port=await freePort(),env={...process.env,SMARTI_PROJECT_ROOT:project,SMARTI_PYTHON:build.python,SMARTI_DATA_DIR:data,SMARTI_DETERMINISTIC_PRODUCT_SMOKE:'1',PYTHONPATH:isolation,PYTHONUTF8:'1',CODEX_HOME:path.join(data,'codex-account'),WEBVIEW2_USER_DATA_FOLDER:path.join(data,'webview'),WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:`--remote-debugging-port=${port}`};
    for(const key of Object.keys(env))if(/^(OPENAI_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY|ANTHROPIC_API_KEY|OPENROUTER_API_KEY|GROQ_API_KEY|DEEPSEEK_API_KEY|MISTRAL_API_KEY|XAI_API_KEY|HF_TOKEN|CODEX_API_KEY|CODEX_ACCESS_TOKEN|CLAUDE_CODE_OAUTH_TOKEN|SMARTI_CORE_BINARY|SMARTI_SUPERVISOR_SMOKE_FILE|SMARTI_BROWSER_SMOKE_FILE)$/.test(key))delete env[key];
    if(missing)env.SMARTI_CORE_BINARY=path.join(data,'missing-core.exe');
    const child=spawn(build.executable,[],{cwd:root,env,windowsHide:true,stdio:'ignore'}),entry={child,data,port,corePid:null,connection:null};owned.push(entry);
    return entry;
  }
  async function attach(entry) { entry.connection=await connect(entry.port,build.identifier);return entry.connection; }
  async function ready(q) {
    let snapshot;
    try {
      await until(async()=>{
        snapshot=await q.invoke('core_status');
        return snapshot.state==='ready' && q.evaluate(`document.getElementById('smarti-startup').hidden && !!(document.querySelector('.chat-column') || document.querySelector('dialog[open]'))`);
      });
    } catch(error) {
      await fs.writeFile(path.join(output,'startup-diagnostic.json'),JSON.stringify({snapshot,body:await q.evaluate('document.body.innerText.slice(0,500)').catch(()=>null)},null,2));
      await q.screenshot('startup-failure.png').catch(()=>{});
      throw error;
    }
    assert.equal(snapshot.state,'ready');return snapshot;
  }
  async function gone(entry) { await until(()=>!alive(entry.child.pid),15000); if(entry.corePid)await until(()=>!alive(entry.corePid),15000);entry.connection?.close(); }
  function windowInfo(entry) {
    const text=execFileSync('pwsh',['-NoProfile','-Command',`[Console]::OutputEncoding=[Text.UTF8Encoding]::new();$p=Get-Process -Id ${entry.child.pid};@{path=$p.Path;hwnd=$p.MainWindowHandle.ToInt64()}|ConvertTo-Json -Compress`],{windowsHide:true,encoding:'utf8'});
    const info=JSON.parse(text);assert.equal(path.resolve(info.path),path.resolve(build.executable));return info;
  }
  async function resizeOwned(entry,q,width,height) {
    const info=windowInfo(entry);assert.ok(info.hwnd);
    const scale=await q.invoke('plugin:window|scale_factor',{label:'main'});
    // Product IPC deliberately grants no set-size capability. Resize the
    // verified QA HWND through Win32 instead of broadening product privileges.
    execFileSync('pwsh',['-NoProfile','-Command',`Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;public static class StartupResize {[DllImport("user32.dll",SetLastError=true)]public static extern bool SetWindowPos(IntPtr h,IntPtr after,int x,int y,int w,int height,uint flags);}';if(-not [StartupResize]::SetWindowPos([IntPtr]${info.hwnd},[IntPtr]::Zero,0,0,${Math.round(width*scale)},${Math.round(height*scale)},22)){throw 'Owned window resize failed'}`],{windowsHide:true,encoding:'utf8'});
  }
  try {
    const first=await launch('consent',{delay:8}),q=await attach(first);
    await q.wait(`!document.getElementById('smarti-startup').hidden && document.getElementById('smarti-startup-icon').naturalWidth>0`);
    await until(()=>q.invoke('plugin:window|is_visible',{label:'main'}));
    assert.equal(await q.evaluate('document.body.innerText.trim()'),'');
    assert.equal(await q.evaluate(`document.querySelectorAll('#smarti-startup img').length`),1);
    assert.equal(await q.evaluate(`document.querySelector('#smarti-startup').getAnimations({subtree:true}).length`),0);
    const before=await q.invoke('plugin:window|inner_size',{label:'main'}),hwnd=windowInfo(first).hwnd;assert.ok(hwnd);
    await q.screenshot('startup-light.png');
    let core=await ready(q);first.corePid=core.pid;
    assert.deepEqual(await q.invoke('plugin:window|inner_size',{label:'main'}),before);assert.equal(windowInfo(first).hwnd,hwnd);
    assert.equal(await q.evaluate(`document.getElementById('smarti-startup').hidden`),true);
    const layout=await q.evaluate(`(()=>{const d=document.querySelector('dialog').getBoundingClientRect();return {x:d.x,y:d.y,width:d.width,height:d.height,vw:innerWidth,vh:innerHeight};})()`);
    assert.ok(Math.abs(layout.x+layout.width/2-layout.vw/2)<2);assert.ok(Math.abs(layout.y+layout.height/2-layout.vh/2)<2);
    assert.deepEqual(await q.evaluate(`(()=>{const s=getComputedStyle(document.querySelector('.legal-document'));return {direction:s.direction,align:s.textAlign};})()`),{direction:'rtl',align:'right'});
    await q.screenshot('consent-light.png');
    await q.evaluate(`document.querySelector('.legal-confirm input').click(); Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='אני מסכים').click()`);
    await q.wait(`!!document.querySelector('.chat-column')`);
    assert.deepEqual(await q.invoke('plugin:window|inner_size',{label:'main'}),before);assert.equal(windowInfo(first).hwnd,hwnd);
    await q.send('Page.reload');await q.wait(`!!document.querySelector('.chat-column')`);assert.equal((await q.invoke('core_status')).pid,core.pid);
    cases.push({name:'icon → consent → chat → reload',sameWindow:true,sameSize:true,corePreserved:true,size:before});
    const generation=core.generation;
    await q.invoke('core_restart');core=await ready(q);first.corePid=core.pid;
    assert.equal(core.generation,generation+1);assert.deepEqual(await q.invoke('plugin:window|inner_size',{label:'main'}),before);assert.equal(windowInfo(first).hwnd,hwnd);
    cases.push({name:'intentional Core restart',sameWindow:true,sameSize:true,newGeneration:true});
    await q.invoke('desktop_set_close_to_tray',{enabled:true});await q.invoke('plugin:window|close',{label:'main'});
    await pause(300);assert.ok(alive(first.child.pid)&&alive(core.pid));assert.equal(await q.invoke('plugin:window|is_visible',{label:'main'}),false);
    await q.invoke('desktop_focus_main');await q.wait(`!!document.querySelector('.chat-column')`);
    assert.equal(windowInfo(first).hwnd,hwnd);cases.push({name:'close to tray and reopen',corePreserved:true,sameWindow:true});
    process.kill(core.pid);await gone(first);cases.push({name:'unexpected Core exit closes desktop',ok:true});

    const dark=await launch('dark',{theme:'dark'}),dq=await attach(dark);dark.corePid=(await ready(dq)).pid;
    await dq.evaluate(`localStorage.setItem('smarti.desktop.theme','dark');location.reload()`);await dq.wait(`!!document.querySelector('dialog[open]')`);
    await resizeOwned(dark,dq,360,620);await pause(300);
    const narrow=await dq.evaluate(`(()=>{const d=document.querySelector('dialog').getBoundingClientRect();return {left:d.left,right:d.right,bottom:d.bottom,vw:innerWidth,vh:innerHeight};})()`);
    assert.ok(narrow.left>=0&&narrow.right<=narrow.vw&&narrow.bottom<=narrow.vh);
    await dq.screenshot('consent-dark-narrow.png');
    await dq.evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent==='לא מסכים — סגירה').click()`);await gone(dark);cases.push({name:'dark/narrow consent and rejection',ok:true});

    for(const timing of ['ready','starting']) {
      const entry=await launch('forced-'+timing,{delay:timing==='starting'?20:0}),probe=await attach(entry);
      if(timing==='ready')entry.corePid=(await ready(probe)).pid;
      else {await until(async()=>{const s=await probe.invoke('core_status');entry.corePid=s.pid;return !!s.pid;});}
      entry.child.kill();await gone(entry);cases.push({name:'forced desktop exit while '+timing,coreTerminated:true});
    }
    const closing=await launch('close',{delay:20}),cq=await attach(closing);
    await until(async()=>{const s=await cq.invoke('core_status');closing.corePid=s.pid;return !!s.pid;});
    await cq.invoke('desktop_set_close_to_tray',{enabled:false});void cq.invoke('plugin:window|close',{label:'main'}).catch(()=>{});await gone(closing);cases.push({name:'ordinary close during startup without tray',coreTerminated:true});

    const failure=await launch('missing',{missing:true});await gone(failure);
    const log=await fs.readFile(path.join(failure.data,'tauri-desktop/data/desktop-lifecycle.log'),'utf8');assert.ok(log.includes('SMARTI_CORE_BINARY not found'));
    cases.push({name:'Core launch failure exits and records diagnostic',ok:true});
    await fs.writeFile(path.join(output,'native-report.json'),JSON.stringify({ok:true,cases,scope:'Fresh source Tauri QA executable, embedded production Web, real isolated source Core and Windows ownership; not installer/package evidence.'},null,2));
    console.log(JSON.stringify({ok:true,cases},null,2));
  } catch(error) {
    await fs.writeFile(path.join(output,'native-report.json'),JSON.stringify({ok:false,cases,error:String(error)},null,2));throw error;
  } finally {
    for(const entry of owned){entry.connection?.close();if(alive(entry.child.pid)){entry.child.kill();await until(()=>!alive(entry.child.pid),15000).catch(()=>{});}if(entry.corePid&&alive(entry.corePid))process.kill(entry.corePid);}
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
