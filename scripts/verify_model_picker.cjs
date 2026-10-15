// Isolated product Composer/ProviderPicker; synthetic props and native IPC only.
// Does not open, restart, or mutate the personal Smarti instance or its Core.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

async function main() {
  const root = path.resolve(__dirname, '..'), desktop = path.join(root, 'desktop');
  const output = path.resolve(process.argv[2] || path.join(root, '.codex-local/model-picker-refinements'));
  await fs.mkdir(output, { recursive: true });
  const favorites = [
    { provider: 'openai_codex_signin', model: 'gpt-6.1-sol' },
    { provider: 'openai_codex_signin', model: 'gpt-6-astra' },
    { provider: 'local', model: String.raw`C:\Models\vendor\Qwen-35-Long-Model-Name-Q4-K-M.gguf` },
    { provider: 'openrouter', model: 'qwen/Qwen-35-Coder' },
    { provider: 'gemini', model: 'gemini-3.6-flash' },
  ];
  const fixture = `import React from 'react';
    import {createRoot} from 'react-dom/client';
    import {Composer} from '/src/Composer';
    import {ProviderPicker} from '/src/ProviderPicker';
    import {DesignSystemProvider} from '/src/design-system';
    import '/src/management.css';
    const params=new URLSearchParams(location.search), theme=params.get('theme')||'light';
    const favorites=${JSON.stringify(favorites)};
    const levels=['low','medium','high','xhigh','max'].map(value=>({value,label:value}));
    window.__qaEvents=[];
    window.__TAURI_INTERNALS__={invoke:async(cmd,args)=>({status:200,body:{data:{available:true,plan_type:'QA',five_hour:{remaining_percent:41,resets_at:Date.now()/1000+3600},weekly:{remaining_percent:0,resets_at:Date.now()/1000+86400}}}})};
    function Fixture(){
      const [item,setItem]=React.useState(favorites[0]),[effort,setEffort]=React.useState('xhigh'),[settings,setSettings]=React.useState(false);
      return <><header className="window-titlebar" style={{height:36,position:'fixed',top:0,left:0,right:0}}>Smarti</header>
        <div style={{position:'fixed',bottom:12,left:12,right:12,maxWidth:697,margin:'auto'}}>
          <Composer theme={theme} attachments={[]} provider={item.provider} model={item.model} favoriteModels={favorites}
            reasoningEffort={effort} reasoningOptions={item.provider==='local'?[]:levels}
            onAttachments={()=>{}} onSend={async()=>{}} onCancel={()=>{}}
            onFavoriteModel={next=>{window.__qaEvents.push(next);setItem(next);setEffort('medium');}}
            onReasoningEffort={async next=>{window.__qaEvents.push({effort:next});await window.__qaEffortGate;await new Promise(r=>setTimeout(r,30));setEffort(next);}}
            onManageModels={()=>setSettings(true)} />
        </div>
        {settings&&<DesignSystemProvider theme={theme}><div style={{position:'fixed',top:60,left:16}}><ProviderPicker value={item.provider} onSelect={async provider=>{window.__qaEvents.push({provider});setItem({provider,model:'qa-model'});}} /></div></DesignSystemProvider>}
      </>;
    }
    document.body.style.margin='0';document.body.style.background=theme==='light'?'#f3f4f6':'#101319';
    createRoot(document.getElementById('root')).render(<Fixture/>);`;
  const { createServer, transformWithEsbuild } = await import(pathToFileURL(path.join(desktop, 'node_modules/vite/dist/node/index.js')).href);
  const server = await createServer({ root: desktop, server: { port: 1497, strictPort: true, host: '127.0.0.1' },
    plugins: [{ name: 'isolated-model-picker-qa',
      resolveId(id) { if (id === '/model-picker-qa.tsx') return '\0model-picker-qa.tsx'; },
      async load(id) { if (id === '\0model-picker-qa.tsx') return (await transformWithEsbuild(fixture, 'model-picker-qa.tsx', {loader:'tsx',jsx:'automatic'})).code; },
      configureServer(vite) { vite.middlewares.use(async (req, res, next) => {
        if (!req.url?.startsWith('/__model-picker-qa')) return next();
        res.setHeader('Content-Type', 'text/html');
        res.end(await vite.transformIndexHtml(req.url, '<!doctype html><html><head><meta charset="utf-8"/></head><body><div id="root"></div><script type="module" src="/model-picker-qa.tsx"></script></body></html>'));
      }); },
    }] });
  let browser;
  const results = [], errors = [];
  try {
    await server.listen();
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();
    page.setDefaultTimeout(15000); page.setDefaultNavigationTimeout(20000);
    page.on('pageerror', error => errors.push(error.message));
    const record = (name, value) => { assert.ok(value, name); results.push(name); };
    const inside = async () => {
      const rects = await page.locator('[role=dialog]:visible,[role=tooltip]:visible').evaluateAll(nodes => nodes.map(node => {
        const r = node.getBoundingClientRect(); return { x: r.x, y: r.y, right: r.right, bottom: r.bottom, role: node.getAttribute('role') };
      }));
      const size = page.viewportSize();
      return rects.length > 0 && rects.every(r => r.x >= -0.5 && r.y >= (r.role === 'dialog' ? 36 : 0) - 0.5 && r.right <= size.width + 0.5 && r.bottom <= size.height + 0.5);
    };
    for (const theme of ['light', 'dark']) for (const [width,height] of [[1280,900],[360,640],[360,320]]) for (const scale of [1,1.5]) {
      const label = `${theme}-${width}x${height}-text${scale}`;
      await page.setViewportSize({ width, height });
      await page.goto(`http://127.0.0.1:1497/__model-picker-qa?theme=${theme}`);
      const trigger = page.getByRole('button', { name: 'בחירת מודל', exact: true });
      await trigger.waitFor();
      if (scale > 1) await page.addStyleTag({content:'.sds-root { --sds-font-control:21px!important; --sds-font-body:24px!important; --sds-font-caption:19.5px!important; }'});
      const neutral = await trigger.evaluate(n=>getComputedStyle(n).backgroundColor);
      await trigger.hover();
      await page.waitForTimeout(140);
      record(`${label}: neutral hover`, neutral !== await trigger.evaluate(n=>getComputedStyle(n).backgroundColor));
      await trigger.click();
      await page.getByRole('dialog', {name:'מודל ועוצמת חשיבה'}).waitFor();
      await page.waitForTimeout(180);
      record(`${label}: compact bounds`, await inside());
      record(`${label}: complete compact content without scrolling`, await page.locator('.model-picker-surface--effort').evaluate(n=>n.scrollHeight<=n.clientHeight+1 && getComputedStyle(n).overflowY==='hidden'));
      record(`${label}: compact header centered`, await page.locator('.model-effort-model').evaluate(n=>{
        const r=n.getBoundingClientRect(),p=n.closest('[role=dialog]').getBoundingClientRect();return Math.abs((r.left+r.right-p.left-p.right)/2)<1;
      }));
      if(width===1280) record(`${label}: popup centered on trigger`, await page.locator('[role=dialog]').evaluate(n=>{
        const p=n.getBoundingClientRect(),a=document.querySelector('.model-picker-trigger').getBoundingClientRect();return Math.abs((p.left+p.right-a.left-a.right)/2)<1;
      }));
      record(`${label}: reasoning stops`, await page.locator('.model-effort-stops i').count() === 5);
      const slider = page.getByRole('slider', {name:'עוצמת חשיבה'});
      await slider.focus(); await slider.press('End');
      await page.waitForFunction(()=>window.__qaEvents.some(e=>e.effort==='max'));
      await page.waitForTimeout(80);
      record(`${label}: keyboard native level`, await slider.getAttribute('aria-valuetext') === 'Max');
      record(`${label}: short quota reset`, await page.locator('.quota-window small').evaluateAll(nodes=>nodes.every(n=>!n.textContent.includes('בעוד') && n.scrollWidth<=n.clientWidth+1)));
      await page.screenshot({path:path.join(output,`${label}-effort.png`)});
      await page.getByRole('button',{name:'פתיחת המודלים המועדפים'}).click();
      const popup = page.getByRole('dialog',{name:'מודלים מועדפים'});
      await popup.waitFor(); await page.waitForTimeout(180);
      record(`${label}: favorites bounds`, await inside());
      if(width===1280) record(`${label}: favorites centered on trigger`, await popup.evaluate(n=>{
        const p=n.getBoundingClientRect(),a=document.querySelector('.model-picker-trigger').getBoundingClientRect();return Math.abs((p.left+p.right-a.left-a.right)/2)<1;
      }));
      const before = await popup.boundingBox();
      const local = page.getByRole('button',{name:'שרת מקומי',exact:true});
      await local.hover();
      await page.getByRole('tooltip',{name:'שרת מקומי',exact:true}).waitFor();
      record(`${label}: tooltip bounds`, await inside());
      if(width===1280) {
        const a=await local.boundingBox(),tip=await page.getByRole('tooltip',{name:'שרת מקומי',exact:true}).boundingBox();
        record(`${label}: tooltip to the right at icon center`,tip.x>=a.x+a.width+7 && Math.abs(tip.y+tip.height/2-a.y-a.height/2)<1);
      }
      record(`${label}: provider has no partial border`, await local.evaluate(n=>getComputedStyle(n).boxShadow==='none'));
      const models = page.getByRole('region',{name:'מודלים של הספק'});
      record(`${label}: local basename`, !(await models.innerText()).includes('C:') && (await models.innerText()).includes('.gguf'));
      const after = await popup.boundingBox();
      record(`${label}: stable provider browsing`, Math.abs(before.width-after.width)<1 && Math.abs(before.height-after.height)<1 && Math.abs(before.y-after.y)<1);
      const modelRect = await models.boundingBox(), railRect = await page.getByRole('region',{name:'ספקים'}).boundingBox();
      record(`${label}: physical RTL and narrow rail`, modelRect.x+modelRect.width <= railRect.x+1 && railRect.width<=57 && modelRect.width>railRect.width);
      await page.getByRole('button',{name:'OpenRouter',exact:true}).hover();
      record(`${label}: namespace preserved`, (await models.innerText()).includes('qwen/'));
      await page.mouse.move(1,Math.min(height-1,100));
      await page.screenshot({path:path.join(output,`${label}-favorites.png`)});
      await page.keyboard.press('Escape');
      record(`${label}: exit animation exists`, await page.locator('.model-picker-frame.is-closing').count() === 1);
      await page.waitForTimeout(200);
      record(`${label}: escape restores focus`, await trigger.evaluate(n=>document.activeElement===n) && await page.locator('[role=dialog]').count() === 0);
    }
    await page.emulateMedia({reducedMotion:'reduce'});
    await page.setViewportSize({width:1280,height:900});
    await page.goto('http://127.0.0.1:1497/__model-picker-qa?theme=light');
    await page.getByRole('button',{name:'בחירת מודל',exact:true}).click();
    record('reduced motion', await page.locator('.model-picker-surface').evaluate(n=>getComputedStyle(n).animationName==='none'));
    const dragSlider = page.getByRole('slider',{name:'עוצמת חשיבה'});
    await dragSlider.focus(); await dragSlider.press('Home'); await page.waitForTimeout(100);
    const callsBeforeDrag = await page.evaluate(()=>window.__qaEvents.length), track = await dragSlider.boundingBox();
    await page.mouse.move(track.x+16,track.y+track.height/2); await page.mouse.down();
    await page.mouse.move(track.x+track.width-16,track.y+track.height/2,{steps:8}); await page.mouse.up();
    await page.waitForFunction(()=>window.__qaEvents.at(-1)?.effort==='max');
    record('native pointer drag saves final level once', await page.evaluate(()=>window.__qaEvents.length) === callsBeforeDrag+1);
    await page.evaluate(()=>{window.__qaEffortGate=new Promise(resolve=>{window.__qaReleaseEffort=resolve;});});
    await dragSlider.press('Home');
    await page.waitForFunction(()=>window.__qaEvents.at(-1)?.effort==='low');
    record('model heading stays enabled while reasoning save is pending',await page.getByRole('button',{name:'פתיחת המודלים המועדפים'}).isEnabled());
    await page.getByRole('button',{name:'פתיחת המודלים המועדפים'}).click();
    record('favorites remain accessible during a pending reasoning save',await page.getByRole('button',{name:'חזרה לעוצמת החשיבה'}).isVisible());
    await page.getByRole('button',{name:'חזרה לעוצמת החשיבה'}).click();
    await page.getByRole('slider',{name:'עוצמת חשיבה'}).press('End');
    await page.waitForFunction(()=>window.__qaEvents.at(-1)?.effort==='max');
    record('next reasoning intent is delivered before the prior save completes',await page.evaluate(()=>!!window.__qaReleaseEffort));
    await page.evaluate(()=>{window.__qaReleaseEffort();delete window.__qaEffortGate;delete window.__qaReleaseEffort;});
    await page.waitForTimeout(100);
    await page.emulateMedia({reducedMotion:'no-preference'});
    const geometry = await page.evaluate(async()=>{
      const slider=document.querySelector('.model-effort-input');
      const results=[],frames=[];
      for(const value of [0,1,2,3,4]) {
        const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;setter.call(slider,String(value));
        slider.dispatchEvent(new Event('input',{bubbles:true}));
        for(let i=0;i<10;i++) {
          await new Promise(requestAnimationFrame);
          const fill=document.querySelector('.model-effort-fill').getBoundingClientRect(),thumb=document.querySelector('.model-effort-thumb').getBoundingClientRect();
          results.push(Math.abs(fill.right-(thumb.left+thumb.right)/2));
          const p=document.querySelector('[role=dialog]').getBoundingClientRect();frames.push({x:p.x,y:p.y,width:p.width,height:p.height});
        }
      }
      return {error:Math.max(...results),stable:['x','y','width','height'].every(k=>Math.max(...frames.map(p=>p[k]))-Math.min(...frames.map(p=>p[k]))<1)};
    });
    record('fill and handle stay aligned during animation',geometry.error<1);
    record('compact popup remains stable while changing effort',geometry.stable);
    const thumb=await page.locator('.model-effort-thumb').boundingBox();
    await page.mouse.move(thumb.x+thumb.width/2,thumb.y+thumb.height/2);await page.waitForTimeout(150);
    const grown=await page.locator('.model-effort-thumb').boundingBox();
    record('handle hover grows smoothly',grown.width>thumb.width+1);
    const firstStop=await page.locator('.model-effort-stops i').first().boundingBox();
    await page.mouse.move(firstStop.x+firstStop.width/2,firstStop.y+firstStop.height/2);await page.waitForTimeout(150);
    record('station hover grows smoothly',(await page.locator('.model-effort-stops i').first().boundingBox()).width>firstStop.width+1);
    await page.waitForTimeout(100);
    await page.getByRole('button',{name:'פתיחת המודלים המועדפים'}).click();
    const selected = page.getByRole('menuitemradio').filter({has:page.locator('.model-menu-check')}).first();
    const selectedColor = await selected.evaluate(n=>getComputedStyle(n).backgroundColor);
    const otherModel = page.getByRole('menuitemradio').nth(1);
    await otherModel.hover(); await page.waitForTimeout(140);
    record('hover differs from actual selection', selectedColor !== await otherModel.evaluate(n=>getComputedStyle(n).backgroundColor));
    const selectedBox=await selected.boundingBox(), hoveredBox=await otherModel.boundingBox();
    record('adjacent highlighted models have a small gap',hoveredBox.y-selectedBox.y-selectedBox.height>=1);
    const backBox=await page.getByRole('button',{name:'חזרה לעוצמת החשיבה'}).boundingBox();
    const providerBox=await page.locator('.model-menu-providers button').first().boundingBox();
    record('back and first provider have a small gap',providerBox.y-backBox.y-backBox.height>=1);
    await page.setViewportSize({width:360,height:320}); await page.waitForTimeout(200);
    record('open popup remains bounded after resize', await inside());
    await page.getByRole('button',{name:'חזרה לעוצמת החשיבה'}).click();
    await page.setViewportSize({width:1280,height:900}); await page.waitForTimeout(200);
    await page.getByRole('button',{name:'הגדרות מודלים ומועדפים',exact:true}).click();
    await page.getByRole('button',{name:/ספק המודל:/}).click();
    record('shared provider icons in settings', await page.getByRole('listbox',{name:'ספקי מודלים'}).locator('.source-provider-icon').count() === 18);
    record('settings provider popup bounds', await inside());
    const touchContext = await browser.newContext({hasTouch:true,viewport:{width:360,height:640}});
    const touch = await touchContext.newPage(); touch.setDefaultTimeout(15000);
    await touch.goto('http://127.0.0.1:1497/__model-picker-qa?theme=light');
    await touch.getByRole('button',{name:'בחירת מודל',exact:true}).tap();
    await touch.getByRole('button',{name:'פתיחת המודלים המועדפים'}).tap();
    await touch.getByRole('button',{name:'שרת מקומי',exact:true}).tap();
    await touch.getByRole('menuitemradio').tap();
    await touch.waitForFunction(()=>window.__qaEvents.some(e=>e.provider==='local'));
    record('native touch retains original local path', await touch.evaluate(()=>window.__qaEvents.at(-1).model.startsWith('C:\\Models\\')));
    record('closed local trigger uses basename', !(await touch.getByRole('button',{name:'בחירת מודל',exact:true}).innerText()).includes('C:'));
    await touch.getByRole('button',{name:'בחירת מודל',exact:true}).tap();
    record('local model without reasoning omits slider', await touch.getByRole('slider').count() === 0);
    await touchContext.close();
    assert.deepEqual(errors, []);
    await fs.writeFile(path.join(output,'report.json'),JSON.stringify({ scope:'isolated Web product components, synthetic callbacks; no live native/Core acceptance', passed:results.length, results, errors },null,2));
    console.log(JSON.stringify({passed:results.length,errors:errors.length,output}));
  } finally { await browser?.close(); await server.close(); }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
