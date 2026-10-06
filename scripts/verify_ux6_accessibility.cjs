const {browserQA}=require('./ux6_browser_support.cjs');
const {sampleContrast}=require('./ux6_contrast.cjs');
const fs=require('node:fs/promises'),path=require('node:path');
const {performance}=require('node:perf_hooks');
async function main(){
 const output=path.resolve(process.argv[3]||'.codex-local/ux-6/after/accessibility');await fs.mkdir(output,{recursive:true});
 const qa=await browserQA(),{page,api}=qa,checks=[],failures=[],contrast=[],timings=[],errors=[];
 const check=(name,ok)=>{(ok?checks:failures).push(name);};page.on('pageerror',e=>errors.push(e.name));
 const ready=()=>page.locator('.chat-column').waitFor({timeout:30000});
 try{
  await page.goto(process.argv[2]||'http://127.0.0.1:1446');await ready();
  for(const theme of ['light','dark'])for(const width of [360,1380]){
   await api('PATCH','/v2/settings',{values:{ui_preferences:{theme_mode:theme}}});await page.reload();await ready();await page.setViewportSize({width,height:900});
   const values=await sampleContrast(page),bad=values.filter(v=>v.ratio<v.threshold);
   contrast.push({theme,width,samples:values.length,min:Math.min(...values.map(v=>v.ratio)),failures:bad});check(`${theme}/${width} sampled effective contrast`,bad.length===0);
   check(`${theme}/${width} Hebrew document language`,await page.locator('html').getAttribute('lang')==='he');
  }
  await page.setViewportSize({width:1380,height:900});const trigger=page.getByRole('button',{name:'הגדרות',exact:true});await trigger.focus();
  const start=performance.now();await page.keyboard.press('Enter');await page.waitForFunction(()=>document.activeElement?.getAttribute('aria-label')==='חזרה לצ׳אט');timings.push({action:'management keyboard opening',ms:performance.now()-start});
  for(let n=0;n<40;n++){await page.keyboard.press(n%5===0?'Shift+Tab':'Tab');check(`management keyboard ${n} avoids inert chat`,await page.evaluate(()=>!document.activeElement.closest('[inert]')));}
  await page.keyboard.press('Escape');await page.locator('.management-overlay').waitFor({state:'hidden'});check('keyboard management restores trigger',await trigger.evaluate(e=>e===document.activeElement));
  const modelTrigger=page.locator('.model-quick-pill > summary');await modelTrigger.click();
  await page.getByRole('menuitem',{name:'הגדרות מודלים ומועדפים',exact:true}).click();await page.getByRole('button',{name:'חזרה לצ׳אט',exact:true}).waitFor();
  await page.keyboard.press('Escape');await page.locator('.management-overlay').waitFor({state:'hidden'});
  check('model settings returns focus to persistent model trigger',await modelTrigger.evaluate(e=>e===document.activeElement));
  await page.emulateMedia({forcedColors:'active'});await trigger.focus();await page.keyboard.press('Tab');check('forced colors visible focus',await page.evaluate(()=>getComputedStyle(document.activeElement).outlineStyle!=='none'));await page.screenshot({path:path.join(output,'forced-colors.png')});await page.emulateMedia({forcedColors:'none'});
  const draft=page.getByRole('textbox',{name:'הודעה',exact:true});await draft.fill('שלום English recovery draft');
  for(let n=0;n<12;n++){const start=performance.now();await page.getByRole('button',{name:n%2?'סגירת סביבת העבודה':'פתיחת סביבת העבודה',exact:true}).click();timings.push({action:'workspace toggle',ms:performance.now()-start});}
  await page.waitForFunction(()=>document.querySelector('.workspace')?.classList.contains('workbench-closed')||!document.querySelector('.workbench')?.classList.contains('is-open'));
  check('settled repeated transitions preserve draft',await draft.inputValue()==='שלום English recovery draft');
  const reversal=await page.evaluate(async()=>{
   const before=performance.now();
   for(let n=0;n<12;n++){
    const name=n%2?'סגירת סביבת העבודה':'פתיחת סביבת העבודה';
    const button=[...document.querySelectorAll('button')].find(b=>b.getAttribute('aria-label')===name);
    if(!button)throw Error('Missing reversal control');button.click();await new Promise(r=>setTimeout(r,40));
   }
   return {requestedIntervalMs:40,totalMs:performance.now()-before};
  });
  await page.waitForTimeout(400);timings.push({action:'twelve mid-transition reversals',...reversal});
  check('mid-transition reversals finish closed with retained draft',await draft.inputValue()==='שלום English recovery draft'&&await page.locator('.workspace').evaluate(e=>!e.classList.contains('has-workbench')));
  await page.emulateMedia({reducedMotion:'reduce'});await page.getByRole('button',{name:'פתיחת סביבת העבודה',exact:true}).click();check('live reduce cancels painted layer',await page.locator('.chat-column').evaluate(e=>e.getAnimations().every(a=>a.playState!=='running')));await page.getByRole('button',{name:'סגירת סביבת העבודה',exact:true}).click();
  await fs.writeFile(path.join(output,'accessibility-tree.yaml'),await page.locator('body').ariaSnapshot());
  check('ordinary renderer has no JavaScript exceptions',errors.length===0);
  // Deliberate failed App module: recovery is tested separately from ordinary errors.
  await page.route('**/src/App.tsx*',route=>route.abort('failed'));await page.reload();await page.getByRole('alert').filter({hasText:'הממשק לא נטען'}).waitFor();
  check('module fault leaves accessible recovery action',await page.getByRole('button',{name:'טעינת הממשק מחדש',exact:true}).isVisible());
  await page.screenshot({path:path.join(output,'module-recovery.png')});await page.unroute('**/src/App.tsx*');await page.getByRole('button',{name:'טעינת הממשק מחדש',exact:true}).click();await ready();
  check('explicit reload recovers retained draft',await draft.inputValue()==='שלום English recovery draft');
  await fs.writeFile(path.join(output,'report.json'),JSON.stringify({checks,failures,contrast,timings,ordinaryErrors:errors,scope:'actual isolated Core/adapted native IPC; sampled solid contrast/AX/keyboard; no spoken screen reader or Windows text-scale proof'},null,2));if(failures.length)process.exitCode=1;
 }catch(e){await page.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});await fs.writeFile(path.join(output,'failure.json'),JSON.stringify({error:String(e),checks,failures,contrast,timings},null,2));throw e;}finally{await qa.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
