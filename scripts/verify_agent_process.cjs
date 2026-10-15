// Isolated product-component regression checks; no personal Core/profile or provider calls.
const fs = require('node:fs/promises');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const repo = process.cwd();
const output = path.join(repo, '.codex-local/agent-process-fixes');
const esbuild = require(require.resolve('esbuild', { paths: [path.join(repo, 'desktop')] }));
const source = `
import React from 'react';
import { createRoot } from 'react-dom/client';
import { RichMessage } from './src/RichMessage';
import { reduceStream, streamAnswer } from './src/chatStreaming';
import { palettes } from './src/design-system/tokens';
const root = createRoot(document.getElementById('root'));
const theme = new URLSearchParams(location.search).get('theme') || 'light';
document.body.style.background = palettes[theme].background;
let state, events = [], cursor = 0, stored, active = true;
const render = () => root.render(<>
  <section id="user"><RichMessage theme={theme} message={{ role:'user', content:'בדוק מקורות', metadata:{run_id:'qa'} }} stream={state} /></section>
  <section id="assistant"><RichMessage theme={theme} message={{ role:'assistant', content:streamAnswer(state), metadata:{run_id:'qa', ...(stored ? {agent_process:stored} : {})} }} stream={state} events={events} active={active} runStatus={active ? 'running' : 'completed'} /></section>
</>);
window.qa = {
  reset() { state=undefined; events=[]; stored=undefined; active=true; render(); },
  stream(values) { state = reduceStream(state, {event_id:++cursor, event_type:'run_stream', payload:{value:{events:values}}}); render(); },
  step(value) { events = [...events, {event_id:++cursor, event_type:'run_step', payload:{value}}]; render(); },
  finish() { active=false; stored={elapsed_seconds:12, events:events.map(e=>e.payload.value)}; state.blocks.ghost={kind:'tool',call_id:'old:0',name:'canvas_manager'}; render(); },
};
render();
`;
async function main() {
  await fs.mkdir(output, {recursive:true});
  await esbuild.build({stdin:{contents:source,resolveDir:path.join(repo,'desktop'),sourcefile:'activity-qa.tsx',loader:'tsx'},bundle:true,jsx:'automatic',outfile:path.join(output,'qa.js'),loader:{'.png':'file','.gif':'file','.svg':'file'},define:{'process.env.NODE_ENV':'"production"'},plugins:[{name:'qa-icons',setup(build){build.onLoad({filter:/design-system[\\/]icons\.tsx$/},async args=>({contents:(await fs.readFile(args.path,'utf8')).replace(/import\.meta\.glob<string>\([^;]+\)/,'{}'),loader:'tsx'}));}}]});
  const server=http.createServer(async(req,res)=>{
    try {
      const url=new URL(req.url,'http://localhost');
      if(url.pathname==='/'){res.setHeader('Content-Type','text/html; charset=utf-8');return res.end('<!doctype html><html dir="rtl"><meta charset="utf-8"><link rel="stylesheet" href="/qa.css"><style>body{margin:0;background:#777}#root{max-width:880px;margin:auto;padding:12px;box-sizing:border-box}.sds-root{padding:8px;box-sizing:border-box}</style><div id="root"></div><script src="/qa.js"></script></html>');}
      const file=path.resolve(output,decodeURIComponent(url.pathname).replace(/^\/+/,''));
      if(!file.startsWith(output+path.sep))throw Error('Invalid path');
      res.setHeader('Content-Type',{'.js':'text/javascript','.css':'text/css','.png':'image/png','.svg':'image/svg+xml'}[path.extname(file)]||'application/octet-stream');res.end(await fs.readFile(file));
    } catch {res.statusCode=404;res.end();}
  });
  await new Promise(done=>server.listen(0,'127.0.0.1',done));
  const browser=await chromium.launch({channel:'msedge',headless:true});
  const context=await browser.newContext();
  await context.addInitScript(()=>sessionStorage.clear());
  const page=await context.newPage();
  const errors=[],checks=[],layouts=[];
  page.on('pageerror',error=>errors.push(error.message));
  const check=(name,value)=>{assert.ok(value,name);checks.push(name);};
  try {
    for(const theme of ['light','dark'])for(const width of [1280,360])for(const reducedMotion of ['no-preference','reduce']){
      const prefix=theme+'/'+width+'/'+reducedMotion;
      await page.setViewportSize({width,height:900});await page.emulateMedia({reducedMotion});
      await page.goto('http://127.0.0.1:'+server.address().port+'/?theme='+theme);
      await page.evaluate(()=>qa.stream([{kind:'request_start',request_id:'first'},{kind:'text_delta',request_id:'first',block_id:'first',role:'report',text:'בודק את המקורות'}]));
      await page.locator('#assistant .agent-report').waitFor();
      check(prefix+': first streamed report uses activity immediately',await page.locator('#assistant .agent-report').textContent()==='בודק את המקורות'&&await page.locator('#assistant .message-content-body').count()===0);
      check(prefix+': user never owns streamed activity',await page.locator('#user .agent-process').count()===0);
      await page.evaluate(()=>qa.stream([{kind:'tool_preparing',request_id:'first',block_id:'first:0',call_id:'first:0',name:'',name_complete:false}]));
      check(prefix+': unnamed preparations are withheld',await page.locator('.agent-tool-group').count()===0);
      await page.evaluate(()=>qa.stream([{kind:'tool_preparing',request_id:'first',block_id:'first:0',call_id:'first:0',name:'web_man',name_complete:false}]));
      check(prefix+': partial names are withheld',await page.locator('.agent-tool-group').count()===0);
      await page.evaluate(()=>qa.stream([{kind:'tool_preparing',request_id:'first',block_id:'first:0',call_id:'first:0',name:'web_manager',arguments_text:'{"query":"מקור"}'}]));
      await page.locator('#assistant .agent-tool-group > summary').click();
      const summary=page.locator('#assistant .agent-tool-row > summary');
      await summary.waitFor();
      const layout=async()=>summary.evaluate(node=>{
        const box=el=>{const b=el.getBoundingClientRect();return{x:b.x,right:b.right}};
        return {indicator:box(node.querySelector('.tool-state-indicator')),text:box(node.querySelector('.agent-status-text')),icon:box(node.lastElementChild),iconName:node.lastElementChild.dataset.icon,overflow:document.documentElement.scrollWidth>innerWidth};
      });
      let geometry=await layout();layouts.push({prefix,state:'preparing',...geometry});
      await page.evaluate(()=>{window.originalGroup=document.querySelector('#assistant .agent-tool-group');window.originalTool=document.querySelector('#assistant .agent-tool-row');});
      check(prefix+': ring is physically left and tool type stays right',geometry.indicator.right<=geometry.text.x&&geometry.text.right<=geometry.icon.x&&geometry.iconName==='globe'&&!geometry.overflow);
      await page.evaluate(()=>{qa.step({type:'report',text:'בודק את המקורות'});qa.step({type:'tool_start',tools:[{event_id:'first:0',action:'web_manager',arguments_text:'{"query":"מקור"}'}]});});
      await page.waitForFunction(()=>document.querySelector('#assistant .agent-tool-row > summary')?.textContent.includes('מריץ כלי'));
      check(prefix+': preparation transitions to one executing call',await page.locator('#assistant .agent-tool-row').count()===1&&await summary.textContent().then(text=>text.includes('מריץ כלי')));
      check(prefix+': preparation and execution retain expanded group and DOM',await page.evaluate(()=>originalGroup===document.querySelector('#assistant .agent-tool-group')&&originalGroup.open&&originalTool===document.querySelector('#assistant .agent-tool-row')));
      await page.evaluate(()=>qa.step({type:'tool_finish',results:[{event_id:'first:0',action:'web_manager',status:'error',output_text:'ERROR: HTTP 429'}]}));
      await page.locator('#assistant .agent-tool-row > summary .tool-state-indicator.is-error').waitFor();
      geometry=await layout();layouts.push({prefix,state:'error',...geometry});
      check(prefix+': X stays left with original tool icon on right',geometry.indicator.right<=geometry.text.x&&geometry.text.right<=geometry.icon.x&&geometry.iconName==='globe'&&await summary.locator('[data-icon="close"]').count()===1&&await summary.locator('[data-icon="check"]').count()===0);
      await summary.focus();await page.keyboard.press('Enter');
      check(prefix+': keyboard expands exact raw output',await page.locator('#assistant .agent-tool-row pre').last().textContent()==='ERROR: HTTP 429');
      await page.evaluate(()=>qa.stream([{kind:'request_start',request_id:'final'},{kind:'text_delta',request_id:'final',block_id:'final',role:'answer',text:'הבדיקה הסתיימה'}]));
      await page.locator('#assistant .message-content-body').waitFor();
      check(prefix+': first final answer chunk uses final answer body',await page.locator('#assistant .message-content-body').textContent()==='הבדיקה הסתיימה');
      check(prefix+': no final controls while streaming',await page.locator('#assistant button[aria-label="העתק"]').count()===0);
      await page.evaluate(()=>qa.finish());await page.locator('#assistant button[aria-label="העתק"]').waitFor();
      check(prefix+': durable completion preserves one process and actual tool result',await page.locator('#assistant .agent-process').count()===1&&await page.locator('#assistant .agent-tool-row').count()===1&&await page.locator('#assistant').textContent().then(text=>!text.includes('לא הושלמה'))&&await page.locator('#user .agent-process').count()===0);
      check(prefix+': saved process keeps manually expanded tool and group',await page.evaluate(()=>originalGroup===document.querySelector('#assistant .agent-tool-group')&&originalGroup.open&&originalTool.open));
      await page.locator('#assistant .agent-process > summary').click();

      await page.evaluate(()=>{
        qa.reset();
        qa.stream([{kind:'request_start',request_id:'one'},{kind:'text_delta',request_id:'one',block_id:'one',role:'report',text:'אני פותח את האתר ומנווט לנושא האחרון'}]);
        qa.step({type:'report',report_id:'one',text:'אני פותח את האתר ומנווט לנושא האחרון'});
        qa.step({type:'tool_start',tools:[{event_id:'one:0',action:'browser_automation_manager'}]});
        qa.step({type:'tool_finish',results:[{event_id:'one:0',action:'browser_automation_manager',status:'ok',output_text:'FIRST'}]});
        qa.stream([{kind:'request_start',request_id:'two'},{kind:'text_delta',request_id:'two',block_id:'two',role:'report',text:'ניסיון קודם לפתיחת האתר'},{kind:'tool_preparing',request_id:'two',block_id:'two:0',call_id:'two:0',name:'browser_automation_manager',name_complete:true}]);
      });
      await page.waitForFunction(()=>document.querySelectorAll('#assistant .agent-tool-group').length===2);
      await page.evaluate(()=>qa.stream([{kind:'retry_wait',request_id:'two',text:'קריאה פגומה. ממתין 33 שניות לניסיון נוסף'}]));
      await page.getByText('קריאה פגומה. ממתין 33 שניות לניסיון נוסף',{exact:true}).waitFor();
      check(prefix+': retry retires unexecuted preparation but retains completed execution',await page.locator('#assistant .agent-tool-row').count()===1&&await page.locator('#assistant .tool-preparation-ring').count()===0);
      check(prefix+': retry has an accessible semantic status without countdown',await page.locator('#assistant [role="status"]').textContent()==='בקשת המודל לא הושלמה. ממתין לניסיון נוסף.');
      await page.evaluate(()=>{
        qa.stream([{kind:'request_start',request_id:'three'},{kind:'text_delta',request_id:'three',block_id:'three',role:'report',text:'אני פותח את האתר'},{kind:'tool_preparing',request_id:'three',block_id:'three:0',call_id:'three:0',name:'browser_automation_manager',name_complete:true}]);
        qa.step({type:'report',report_id:'three',text:'אני פותח את האתר'});
        qa.step({type:'tool_start',tools:[{event_id:'three:0',action:'browser_automation_manager'}]});
        qa.step({type:'tool_finish',results:[{event_id:'three:0',action:'browser_automation_manager',status:'ok',output_text:'SECOND'}]});
      });
      await page.waitForFunction(()=>[...document.querySelectorAll('#assistant .agent-tool-row>summary')].filter(node=>node.textContent==='הסתיים browser_automation_manager').length===2);
      check(prefix+': finished rows stay present before another tool starts',await page.locator('#assistant .agent-tool-group').count()===2);
      check(prefix+': similar reports keep their exact content and chronological order',JSON.stringify(await page.locator('#assistant .agent-report').allTextContents())===JSON.stringify(['אני פותח את האתר ומנווט לנושא האחרון','ניסיון קודם לפתיחת האתר','אני פותח את האתר']));
      check(prefix+': narrow raw names and RTL content stay inside the viewport',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
      check(prefix+': report contrast uses the actual theme surface',await page.evaluate(()=>{
        const rgb=value=>value.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:Math.pow((v+.055)/1.055,2.4);});
        const luminance=value=>{const [r,g,b]=rgb(value);return .2126*r+.7152*g+.0722*b;};
        const a=luminance(getComputedStyle(document.querySelector('#assistant .agent-report')).color),b=luminance(getComputedStyle(document.body).backgroundColor);
        return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)>=4.5;
      }));
      if(reducedMotion==='reduce')await page.screenshot({path:path.join(output,theme+'-'+width+'.png'),fullPage:true});
    }
    check('no browser runtime errors',errors.length===0);
    await fs.writeFile(path.join(output,'report.json'),JSON.stringify({checks,layouts,errors},null,2));
    console.log(checks.length+' checks passed; '+output);
  }finally{await browser.close();await new Promise(done=>server.close(done));}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
