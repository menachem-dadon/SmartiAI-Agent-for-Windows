// Direct CDP avoids Playwright's unsupported Vite shared_worker target.
// No worker suppression or page API patches are needed. Requires Node >=22.
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
async function connectOwned(mode){
 const launch=JSON.parse(await fs.readFile(`.codex-local/ux-6/native-${mode}-launch.json`,'utf8'));
 assert.equal(launch.identifier,'ai.smarti.ux6'+mode);assert.match(String(launch.pid),/^\d+$/);
 assert.ok(path.resolve(launch.data).startsWith(path.resolve('.codex-local/ux-6')+path.sep));
 const exe=execFileSync('pwsh',['-NoProfile','-Command',`[Console]::OutputEncoding=[Text.UTF8Encoding]::new();(Get-Process -Id ${launch.pid}).Path`],{windowsHide:true,encoding:'utf8'}).trim();
 assert.equal(path.resolve(exe),path.resolve(launch.executable));assert.equal(path.win32.basename(exe),'ux6-'+mode+'.exe');
 const targets=await(await fetch(launch.cdp+'/json/list')).json();
 const target=targets.find(t=>t.type==='page'&&!t.url.includes('voice-overlay=1')&&(mode==='dev'?t.url.startsWith(launch.devUrl||'http://127.0.0.1:1446'):t.url.startsWith('http://tauri.localhost')));
 assert.ok(target?.webSocketDebuggerUrl,'Owned main page');
 const socket=new WebSocket(target.webSocketDebuggerUrl),pending=new Map(),events=[];let id=0;
 await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
 socket.addEventListener('message',({data})=>{const msg=JSON.parse(data);if(msg.id){const p=pending.get(msg.id);if(p){pending.delete(msg.id);clearTimeout(p.timer);msg.error?p.reject(Error(JSON.stringify(msg.error))):p.resolve(msg.result);}}else events.push(msg);});
 socket.addEventListener('close',()=>{for(const p of pending.values()){clearTimeout(p.timer);p.reject(Error('Owned CDP disconnected'));}pending.clear();});
 const send=(method,params={})=>new Promise((resolve,reject)=>{const requestId=++id;const timer=setTimeout(()=>{pending.delete(requestId);reject(Error('CDP deadline: '+method));},30000);pending.set(requestId,{resolve,reject,timer});socket.send(JSON.stringify({id:requestId,method,params}));});
 const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text+': '+(result.exceptionDetails.exception?.description||''));return result.result.value;};
 const invoke=(cmd,args={})=>evaluate(`window.__TAURI_INTERNALS__.invoke(${JSON.stringify(cmd)},${JSON.stringify(args)})`);
 try{await send('Runtime.enable');await send('Page.enable');assert.equal(await invoke('plugin:app|identifier'),launch.identifier);}catch(error){socket.close();throw error;}
 const waitFor=async(expression,timeout=30000)=>{const deadline=Date.now()+timeout;while(Date.now()<deadline){if(await evaluate(expression).catch(()=>false))return;await new Promise(r=>setTimeout(r,50));}throw Error('Page deadline: '+expression);};
 return{launch,send,evaluate,invoke,waitFor,events,close:()=>socket.close()};
}
module.exports={connectOwned};
