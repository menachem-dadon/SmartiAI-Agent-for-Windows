// Product UI QA: isolated real Core, adapted native IPC, no model/account calls.
const {browserQA}=require('./ux6_browser_support.cjs');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict');
async function main(){
 const base=process.argv[2]||'http://127.0.0.1:1439';
 const output=path.resolve(process.argv[3]||'.codex-local/browser-agent-ui');
 await fs.mkdir(output,{recursive:true});
 let qa,state;const errors=[],commands=[];
 qa=await browserQA({env:{UX6_STRESS_QA:'0',UX4_WORKBENCH_QA:'1'},invoke:async(command,args)=>{
  commands.push({command,args});
  if(command==='browser_activate'){
   state={...state,activeTabId:args.tabId,tabs:state.tabs.map(tab=>({...tab,active:tab.tabId===args.tabId}))};
   qa.setNative(state);await qa.emit('browser://state',state);return state;
  }
  if(command==='browser_agent_control'){
   const status=args.action==='resume'?'ready':args.action==='stop'?'stopped':'paused';
   state={...state,agent:{...state.agent,state:status}};state.agents=[state.agent];
   qa.setNative(state);await qa.emit('browser://state',state);return {ok:true};
  }
  return true;
 }});
 const {page,api,handshake}=qa;
 page.on('pageerror',error=>errors.push(error.message));
 const frame=()=>page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 try{
  await page.goto(base);await page.locator('.chat-column').waitFor({timeout:45000});
  await page.locator('.conversation-select').filter({hasText:'מחקר לקראת המפגש'}).click();
  await page.getByRole('heading',{name:'מחקר לקראת המפגש',exact:true}).waitFor();
  await page.getByRole('button',{name:'פתיחת סביבת העבודה',exact:true}).click();
  await page.locator('.workbench-empty').getByRole('button',{name:'קבצים',exact:true}).click();
  const selected=await page.locator('.workbench-tabs [aria-selected=true]').getAttribute('data-tab-id');
  const tab={tabId:'agent-qa-tab',targetId:'agent-qa-target',webviewLabel:'browser-qa',workspaceId:'agent-qa-workspace',profile:'persistent',url:'https://example.test/task',title:'פעולה ברקע',active:false,loading:false,crashed:false,pinned:false,faviconUrl:'',audioPlaying:false};
  const agent={tabId:tab.tabId,workspaceId:tab.workspaceId,sessionId:handshake.sample,state:'running',action:'click',presentation:'preview'};
  state={tabs:[tab],activeTabId:null,transport:'webview2-in-process-cdp',remoteDebuggingPort:null,agent,agents:[agent]};
  qa.setNative(state);await qa.emit('browser://state',state);
  await page.getByLabel('תצוגה מקדימה של הדפדפן',{exact:true}).waitFor();
  assert.equal(await page.locator('.workbench-tabs [aria-selected=true]').getAttribute('data-tab-id'),selected,'background adoption must retain selected files');
  await qa.emit('browser://presentation',{workspaceId:'another-workspace',tabId:'another-tab',sessionId:'another-conversation',mode:'preview'});
  await frame();
  assert.equal(await page.locator('.workbench-tabs [aria-selected=true]').getAttribute('data-tab-id'),selected,'another conversation quiet task must not switch UI');
  await page.getByRole('button',{name:'השהיה והעברת השליטה אליי',exact:true}).click();
  await page.getByRole('button',{name:'החזרת השליטה ל־Smarti',exact:true}).waitFor();
  assert(commands.some(call=>call.command==='browser_agent_control'&&call.args.tabId===tab.tabId));
  await page.getByRole('button',{name:'החזרת השליטה ל־Smarti',exact:true}).click();
  await page.getByRole('button',{name:'השהיה והעברת השליטה אליי',exact:true}).waitFor();
  const geometry=[];
  for(const theme of ['light','dark']){
   await api('PATCH','/v2/settings',{values:{ui_preferences:{theme_mode:theme}}});
   await page.evaluate(value=>window.dispatchEvent(new CustomEvent('smarti:settings-changed',{detail:{values:{ui_preferences:{theme_mode:value}}}})),theme);
   // The regular settings refresh applies the actual Core preference on reload.
   await page.reload();await page.locator('.chat-column').waitFor();
   await qa.emit('browser://state',state);
   for(const width of [360,900,1600]){
    await page.setViewportSize({width,height:900});await frame();
    await page.waitForFunction(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth<=1,{},{timeout:3000});
    const card=page.getByLabel('תצוגה מקדימה של הדפדפן',{exact:true});await card.waitFor();
    const g=await card.evaluate(el=>{const r=el.getBoundingClientRect();return{x:r.x,right:r.right,width:r.width,viewport:innerWidth,overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth,buttons:[...el.querySelectorAll('button')].map(b=>{const r=b.getBoundingClientRect();return{x:r.x,right:r.right,width:r.width,label:b.getAttribute('aria-label')};})};});
    if(!(g.x>=-1&&g.right<=width+1&&g.overflow<=1))console.error(JSON.stringify({theme,width,geometry:g}));
    assert(g.x>=-1&&g.right<=width+1&&g.overflow<=1,`${theme}/${width}: preview exceeds viewport`);
    assert(g.buttons.every(b=>b.x>=g.x-1&&b.right<=g.right+1),`${theme}/${width}: control exceeds card`);
    assert(await card.evaluate(el=>{const r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}),`${theme}/${width}: preview is covered by another surface`);
    geometry.push({theme,width,...g});
    await page.screenshot({path:path.join(output,`${theme}-${width}.png`)});
   }
  }
  await page.setViewportSize({width:1600,height:900});
  await qa.emit('browser://presentation',{requestId:'view-qa',workspaceId:tab.workspaceId,tabId:tab.tabId,sessionId:handshake.sample,mode:'visible',operation:'split'});
  await page.waitForFunction(()=>document.querySelector('.workbench-tabs [aria-selected=true]')?.getAttribute('data-tab-id')==='agent-qa-workspace');
  await page.waitForTimeout(400);
  assert(commands.some(call=>call.command==='browser_activate'&&call.args.tabId===tab.tabId));
  assert(commands.some(call=>call.command==='browser_presentation_ack'&&call.args.requestId==='view-qa'));
  await qa.emit('browser://workspace-closed',{workspaceId:tab.workspaceId});
  await page.getByRole('tab',{name:'דפדפן Smarti',exact:true}).waitFor({state:'hidden'});
  assert.deepEqual(errors,[]);
  const report={ok:true,scope:'isolated Core + rendered product UI with adapted native IPC',geometry,checks:['background target adoption retains files','quiet work in another conversation retains UI','preview controls address owned target','light/dark RTL at 360/900/1600 without covered preview','presentation activates same target and acknowledges','closed workspace removed'],errors};
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify({ok:true,checks:report.checks,output}));
 }catch(error){
  await page.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});
  const controls=await page.locator('.browser-agent-controls').evaluateAll(elements=>elements.map(el=>({html:el.outerHTML,rect:el.getBoundingClientRect().toJSON(),hidden:!!el.closest('[hidden],[inert]')})));
  console.error(JSON.stringify({controls,workspace:await page.locator('.workspace').getAttribute('class')},null,2));
  throw error;
 }finally{await qa.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
