// QA only. Real authenticated Core; adapted IPC and deterministic generation.
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const {randomUUID}=require('node:crypto');
const assert=require('node:assert/strict');
async function browserQA() {
 const token=randomUUID();
 const host=spawn('python',['scripts/ux3_core_host.py'],{windowsHide:true,env:{...process.env,UX3_TEST_TOKEN:token,UX6_STRESS_QA:'1',UX4_WORKBENCH_QA:'1',PYTHONUTF8:'1'}});
 let stderr='';host.stderr.on('data',b=>stderr+=b);
 let handshake;
 try{handshake=await new Promise((resolve,reject)=>{
  let buffer='';const timer=setTimeout(()=>reject(Error('Isolated Core handshake timeout')),120000);
  host.once('exit',code=>{clearTimeout(timer);reject(Error('Isolated Core exited '+code));});
  host.stdout.on('data',b=>{buffer+=b;for(const line of buffer.split('\n'))if(line.includes('"sample"'))try{const value=JSON.parse(line);clearTimeout(timer);resolve(value);}catch{}});
 });}catch(e){host.stdin.end('shutdown\n');throw e;}
 const api=async(method,route,body)=>{
  const r=await fetch(`http://127.0.0.1:${handshake.port}${route}`,{method,signal:AbortSignal.timeout(30000),headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json',...(method==='GET'?{}:{'Idempotency-Key':randomUUID()})},body:method==='GET'?undefined:JSON.stringify(body||{})});return{status:r.status,body:await r.json()};
 };
 const legal=(await api('GET','/v2/management/legal')).body.data;
 assert.equal((await api('POST','/v2/management/legal',{accepted:true,version:legal.version})).status,200);
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:1380,height:900}}),page=await context.newPage();
 const calls=[];let native={tabs:[],activeTabId:null,available:true};
 await page.exposeFunction('__qaInvoke',async(cmd,args={})=>{
  calls.push(cmd);
  if(cmd==='core_api'){const r=args.request;return api(r.method,r.path,r.body);}
  if(cmd==='core_status')return{state:'ready',generation:1,pid:handshake.pid,port:handshake.port,stderrTail:[]};
  if(cmd==='core_health')return handshake.health;
  if(cmd==='browser_status'||cmd==='browser_metadata')return native;
  if(cmd==='browser_open'){const tab={tabId:randomUUID(),workspaceId:args.workspaceId,url:args.url,title:'QA browser',profile:args.profile,active:true,loading:false,pinned:false};native={...native,tabs:[...native.tabs,tab],activeTabId:tab.tabId};return native;}
  if(cmd==='browser_close_workspace'){native={...native,tabs:native.tabs.filter(t=>t.workspaceId!==args.workspaceId)};return native;}
  if(cmd==='browser_action')return{result:args.action.method==='Page.captureScreenshot'?{data:'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg=='}:{}};
  if(cmd==='plugin:window|is_maximized')return false;
  if(cmd==='plugin:event|listen')return calls.length;
  if(['browser_set_visible','browser_set_bounds','plugin:event|unlisten','desktop_finish_startup','desktop_set_close_to_tray','desktop_set_voice_hotkey','desktop_set_unread','desktop_notify'].includes(cmd))return true;
  throw Error('Unadapted native IPC: '+cmd);
 });
 await page.addInitScript(()=>{let id=0;window.__TAURI_INTERNALS__={metadata:{currentWindow:{label:'main'},currentWebview:{label:'main',windowLabel:'main'}},transformCallback:()=>++id,unregisterCallback:()=>{},invoke:(cmd,args)=>window.__qaInvoke(cmd,args)};window.__TAURI_EVENT_PLUGIN_INTERNALS__={unregisterListener:()=>{}};});
 return{page,browser,api,handshake,calls,close:async()=>{await browser.close();host.stdin.end('shutdown\n');await Promise.race([new Promise(r=>host.once('exit',r)),new Promise(r=>setTimeout(r,5000))]);if(host.exitCode===null)host.kill();}};
}
module.exports={browserQA};
