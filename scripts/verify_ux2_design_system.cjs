// Isolated browser QA for shared components. No Core, Tauri bridge or personal data.
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const path = require("node:path");
const base = process.argv[2] || "http://127.0.0.1:1434";
const output = path.resolve(process.argv[3] || ".codex-local/ux-2/qa");
const interactionsOnly = process.argv.includes('--interactions-only');
const checks = [], layouts = [], contrasts = [], errors = [], remote = [], storage = [];
const check = (label, passed) => { assert.ok(passed, label); checks.push(label); };
async function auditContrast(page, sample) {
  const values = await page.evaluate(() => {
    const rgba = (value) => { const n = value.match(/[\d.]+/g)?.map(Number) || []; return [n[0] || 0, n[1] || 0, n[2] || 0, n.length > 3 ? n[3] : 1]; };
    const blend = (fg, bg) => [0,1,2].map(i => fg[i]*fg[3]+bg[i]*(1-fg[3])).concat(1);
    const background = (node) => { const chain=[]; for (let n=node;n;n=n.parentElement) chain.unshift(n); let color=[255,255,255,1]; for(const n of chain) color=blend(rgba(getComputedStyle(n).backgroundColor),color); return color; };
    const luminance = (color) => color.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
    const ratio = (fg,bg) => {const a=luminance(fg),b=luminance(bg);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);};
    const result=[];
    for(const element of document.querySelectorAll('.sds-root *')) {
      if (!element.getClientRects().length || element.closest('[hidden]') || element.closest(':disabled')) continue;
      const style=getComputedStyle(element); if(style.visibility==='hidden') continue;
      if (!Array.from(element.childNodes).some(n=>n.nodeType===Node.TEXT_NODE&&n.textContent.trim()) && !element.matches('input:not([type="range"]):not([type="checkbox"]),textarea')) continue;
      const bg=background(element), fg=blend(rgba(style.color),bg);
      result.push({kind:'text',threshold:4.5,text:(element.textContent||element.value||element.placeholder||element.getAttribute('aria-label')||'').trim().slice(0,80),ratio:ratio(fg,bg),fg,bg});
      if(element.matches('input,textarea') && element.getAttribute('placeholder')) {const placeholder=blend(rgba(getComputedStyle(element,'::placeholder').color),bg);result.push({kind:'text',threshold:4.5,text:'placeholder',ratio:ratio(placeholder,bg),fg:placeholder,bg});}
    }
    for(const element of document.querySelectorAll('.sds-field:not(:disabled),.sds-switch input:not(:disabled)+.sds-switch-track,.sds-range:not(:disabled),.sds-root :focus-visible')) {
      if(!element.getClientRects().length||element.closest('[hidden]'))continue;
      const style=getComputedStyle(element),bg=background(element.parentElement);
      const isRange=element.matches('.sds-range'),isField=element.matches('.sds-field'),isTrack=element.matches('.sds-switch-track');
      const border=rgba(isRange?getComputedStyle(element,'::-webkit-slider-runnable-track').outlineColor:style.borderColor);
      if(isField||isRange||isTrack)result.push({kind:'boundary',threshold:3,text:element.className,ratio:ratio(blend(border,bg),bg),fg:border,bg});
      if(element.matches(':focus-visible')&&style.outlineStyle!=='none'&&parseFloat(style.outlineWidth)>0) {const fg=rgba(style.outlineColor);result.push({kind:'focus',threshold:3,text:'focus ring',ratio:ratio(blend(fg,bg),bg),fg,bg});}
    }
    for(const element of document.querySelectorAll('.sds-icon')) {
      if(!element.getClientRects().length||element.closest('[hidden]')||element.closest(':disabled'))continue;
      if(element instanceof SVGElement) {
        const bg=background(element);
        for(const shape of element.querySelectorAll('path,line,polyline,polygon,circle,ellipse,rect')) {
          const box=shape.getBBox(),style=getComputedStyle(shape);if(!box.width&&!box.height)continue;
          for(const paint of ['stroke','fill']) {
            if(style[paint]==='none'||(paint==='stroke'&&parseFloat(style.strokeWidth)===0))continue;
            const fg=rgba(style[paint]);fg[3]*=Number(style[`${paint}Opacity`])*Number(style.opacity);if(!fg[3])continue;
            result.push({kind:'icon',threshold:3,text:`${element.getAttribute('data-icon')} ${paint}`,ratio:ratio(blend(fg,bg),bg),fg,bg});
          }
        }
        continue;
      }
      const canvas=document.createElement('canvas');canvas.width=element.naturalWidth;canvas.height=element.naturalHeight;
      const ctx=canvas.getContext('2d');ctx.filter=getComputedStyle(element).filter;ctx.drawImage(element,0,0);
      const pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data,counts=new Map();
      for(let i=0;i<pixels.length;i+=4)if(pixels[i+3]>250){const key=[pixels[i],pixels[i+1],pixels[i+2]].join(',');counts.set(key,(counts.get(key)||0)+1);}
      const dominant=[...counts.entries()].sort((a,b)=>b[1]-a[1])[0];if(!dominant)continue;
      const fg=dominant[0].split(',').map(Number).concat(1),bg=background(element);
      result.push({kind:'icon',threshold:3,text:element.getAttribute('data-icon'),ratio:ratio(fg,bg),fg,bg});
    }
    return result;
  });
  for(const value of values) assert.ok(value.ratio>=value.threshold,`${sample}: ${value.kind} ${value.text} contrast ${value.ratio}`);
  contrasts.push({sample,count:values.length,min:Math.min(...values.map(v=>v.ratio)),values});
}
async function run() {
  await fs.mkdir(output,{recursive:true});
  const browser=await chromium.launch({channel:"msedge",headless:true});
  const context=await browser.newContext({viewport:{width:1380,height:900}});
  await context.addInitScript(() => {
    for(const name of ['localStorage','sessionStorage']) Object.defineProperty(window,name,{value:{
      getItem(){throw new Error('Storage read forbidden');},
      setItem(){throw new Error('Storage write forbidden');},
      removeItem(){throw new Error('Storage mutation forbidden');},
      clear(){throw new Error('Storage mutation forbidden');}
    }});
  });
  await context.route('**/*', route => { const url=route.request().url(); if(url.startsWith(base+'/')||url.startsWith('data:')) return route.continue(); remote.push(url); return route.abort(); });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  const button=(label)=>page.getByRole('button',{name:label,exact:true});
  const open=async(theme='light',tab='controls',width=1380,height=900,extra='')=>{await page.setViewportSize({width,height});await page.goto(`${base}/ux-2.html?theme=${theme}&tab=${tab}${extra}`,{waitUntil:'networkidle',timeout:120000});await page.locator('.gallery-frame').waitFor();await page.waitForFunction(()=>Array.from(document.querySelectorAll('.sds-icon')).filter(i=>i.getClientRects().length).every(i=>i instanceof SVGElement?i.querySelectorAll('path,line,polyline,polygon,circle,ellipse,rect').length>0:i.complete&&i.naturalWidth>0));};
  const save=async()=>fs.writeFile(path.join(output,'report.json'),JSON.stringify({checks,layouts,contrasts,errors,remote,storage,browser:browser.version(),boundary:'Edge headless; CSS px; deviceScaleFactor=1; no native or package evidence'},null,2));
  try {
    if(!interactionsOnly)for(const theme of ['light','dark'])for(const width of [320,360,500,900,1380])for(const height of [653,900])for(const tab of ['controls','message','states','tokens']) {
      await open(theme,tab,width,height);
      const geometry=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:innerWidth,frame:document.querySelector('.gallery-frame').getBoundingClientRect().toJSON(),images:Array.from(document.querySelectorAll('.sds-icon')).filter(i=>i.getClientRects().length).every(i=>i instanceof SVGElement?i.querySelectorAll('path,line,polyline,polygon,circle,ellipse,rect').length>0:i.complete&&i.naturalWidth>0)}));
      const sample=`${theme}-${width}-${height}-${tab}`;
      check(`${sample}: page fits`,geometry.scroll<=width);check(`${sample}: PNG assets load`,geometry.images);
      layouts.push({sample,...geometry});await auditContrast(page,sample);
      if(height===900&&[360,1380].includes(width)&&['controls','message'].includes(tab)) await page.screenshot({path:path.join(output,`${sample}.png`),fullPage:true});
    }
    for(const theme of ['light','dark']) {
      await open(theme,'tokens');
      check(`${theme}: all 63 semantic roles render Tabler SVG`,await page.locator('.gallery-icons svg[data-icon-family="tabler"]').count()===63);
      await button('האייקונים המקוריים').click();
      await page.waitForFunction(()=>Array.from(document.querySelectorAll('.gallery-icons img')).every(i=>i.complete&&i.naturalWidth>0));
      check(`${theme}: original 63 PNG remain restorable`,await page.locator('.gallery-icons img[data-icon-family="original"]').count()===63);
      await auditContrast(page,`${theme}-original-icons`);
      await button('Tabler SVG').click();
      check(`${theme}: switch back to SVG`,await page.locator('.gallery-icons svg[data-icon-family="tabler"]').count()===63);
      await open(theme);await button('חלון צר').click();
      check(`${theme}: internal narrow container`,(await page.locator('.gallery-frame').boundingBox()).width<=360);
      check(`${theme}: internal narrow single column`,await page.locator('.gallery-grid:visible').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length===1));
      await page.screenshot({path:path.join(output,`${theme}-internal-narrow.png`),fullPage:true});
      await open(theme);
      const control=page.getByRole('switch',{name:'הפעלת הכלי',exact:true});
      await control.scrollIntoViewIfNeeded();
      const thumb=()=>page.locator('.sds-switch').filter({has:control}).locator('.sds-switch-thumb').boundingBox();
      const track=()=>page.locator('.sds-switch').filter({has:control}).locator('.sds-switch-track').boundingBox();
      await page.waitForTimeout(200);let t=await thumb(),r=await track();check(`${theme}: RTL checked thumb on left`,t.x+t.width/2<r.x+r.width/2);
      await control.click();await page.waitForTimeout(200);t=await thumb();check(`${theme}: RTL unchecked thumb on right`,t.x+t.width/2>r.x+r.width/2);
      await button('LTR').click();await control.click();await page.waitForTimeout(200);t=await thumb();r=await track();check(`${theme}: LTR checked thumb on right`,t.x+t.width/2>r.x+r.width/2);
      await button('RTL').click();
      const range=page.getByRole('slider',{name:'עוצמת הקראה'});await range.focus();const old=Number(await range.inputValue());await range.press('ArrowLeft');check(`${theme}: native RTL range keyboard`,Number(await range.inputValue())>old);
      const rangeRect=await range.boundingBox();await page.mouse.click(rangeRect.x+rangeRect.width*.25,rangeRect.y+rangeRect.height/2);check(`${theme}: range pointer updates output`,Number(await range.inputValue())>60);
      const ring=await range.evaluate(e=>{const s=getComputedStyle(e);return{s:s.outlineStyle,c:s.outlineColor,w:s.outlineWidth};});
      // Focus after keyboard input to require :focus-visible in the browser.
      await range.press('ArrowRight');check(`${theme}: visible keyboard focus`,(await range.evaluate(e=>getComputedStyle(e).outlineWidth))==='2px');
      const field=page.getByRole('textbox',{name:'שם',exact:true});await field.focus();await field.press('ArrowRight');
      check(`${theme}: neutral input focus`,await field.evaluate(e=>{const s=getComputedStyle(e),hex=s.getPropertyValue('--sds-color-focus').trim().slice(1),rgb=[0,2,4].map(i=>parseInt(hex.slice(i,i+2),16));return s.outlineColor===`rgb(${rgb.join(', ')})`&&s.outlineWidth==='2px';}));
      await auditContrast(page,`${theme}-focused-field`);
      const send=button('שליחה');await send.hover();await auditContrast(page,`${theme}-main-action-hover`);await page.mouse.down();await auditContrast(page,`${theme}-main-action-pressed`);await page.mouse.up();await button('עצירה').click();
      const trigger=button('פעולות המסמך');await trigger.focus();await trigger.press('ArrowDown');
      check(`${theme}: first enabled menu action focused`,await page.getByRole('menuitem',{name:'שינוי שם'}).evaluate(e=>e===document.activeElement));
      await page.keyboard.press('ArrowDown');check(`${theme}: menu skips disabled`,await page.getByRole('menuitem',{name:'מחיקה'}).evaluate(e=>e===document.activeElement));
      await page.keyboard.press('Home');await page.keyboard.press('Escape');check(`${theme}: menu escape restores trigger`,await trigger.evaluate(e=>e===document.activeElement));
      await trigger.click();await trigger.click();check(`${theme}: trigger toggles menu`,await page.getByRole('menu').count()===0);
      await trigger.click();await field.click();check(`${theme}: outside closes without stealing focus`,await page.getByRole('menu').count()===0&&await field.evaluate(e=>e===document.activeElement));
      await trigger.click();await page.keyboard.press('Tab');check(`${theme}: Tab leaves menu`,await page.getByRole('menu').count()===0);
      const rename=button('שינוי שם');await rename.click();const modal=page.getByRole('dialog',{name:'שינוי שם'});
      const name=page.getByRole('textbox',{name:'שם המסמך'});check(`${theme}: modal initial focus`,await name.evaluate(e=>e===document.activeElement));
      for(let i=0;i<12;i++) {await page.keyboard.press('Tab');check(`${theme}: native modal focus containment ${i}`,await modal.evaluate(e=>e.contains(document.activeElement)));}
      for(let i=0;i<8;i++) {await page.keyboard.press('Shift+Tab');check(`${theme}: reverse modal focus containment ${i}`,await modal.evaluate(e=>e.contains(document.activeElement)));}
      await modal.getByRole('button',{name:'סגירה',exact:true}).hover();const modalTip=page.getByRole('tooltip',{name:'סגירה',exact:true});await modalTip.waitFor();
      check(`${theme}: dialog tooltip participates in top layer`,await modalTip.evaluate(e=>{const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}));
      await name.fill('שם חדש · Research');await modal.getByRole('button',{name:'שמירה',exact:true}).click();check(`${theme}: local edit handler updates title`,(await page.locator('[data-example-title]').innerText()).includes('שם חדש'));
      check(`${theme}: modal restores focus`,await rename.evaluate(e=>e===document.activeElement));
      await rename.click();await page.keyboard.press('Escape');check(`${theme}: native modal Escape`,await modal.count()===0&&await rename.evaluate(e=>e===document.activeElement));
      await rename.click();await page.mouse.click(4,4);check(`${theme}: native backdrop click`,await modal.count()===0&&await rename.evaluate(e=>e===document.activeElement));
      await button('מחיקת פריט').click();const confirm=page.getByRole('alertdialog');check(`${theme}: confirmation starts at cancel`,await confirm.getByRole('button',{name:'ביטול'}).evaluate(e=>e===document.activeElement));
      await confirm.getByRole('button',{name:'מחיקה',exact:true}).click();check(`${theme}: failed confirm remains visible`,await confirm.getByRole('alert').isVisible());await auditContrast(page,`${theme}-confirmation-error`);
      await page.screenshot({path:path.join(output,`${theme}-confirmation.png`)});await confirm.getByRole('button',{name:'ניסיון חוזר'}).click();check(`${theme}: retry handler closes`,await confirm.count()===0);
      const copy=button('העתקה');await copy.focus();check(`${theme}: tooltip on focus`,await page.getByRole('tooltip',{name:'העתקה'}).isVisible());await page.keyboard.press('Escape');check(`${theme}: tooltip Escape`,await page.getByRole('tooltip').count()===0);
      await field.focus();await copy.hover();await page.getByRole('tooltip',{name:'העתקה'}).hover();await page.waitForTimeout(220);check(`${theme}: tooltip stays hoverable`,await page.getByRole('tooltip',{name:'העתקה'}).isVisible());await page.keyboard.press('Escape');
      await page.getByRole('tab',{name:'שיחה ותוצרים'}).click();
      const bubble=await page.locator('.sds-user-bubble').last().boundingBox(), reading=await page.locator('.gallery-reading').boundingBox();check(`${theme}: English bubble physically right`,Math.abs(bubble.x+bubble.width-(reading.x+reading.width-25))<3);
      const order=await page.locator('.sds-message').evaluate(e=>Array.from(e.children).map(n=>n.className));check(`${theme}: explicit outputs before actions`,order.indexOf('sds-message-outputs')<order.indexOf('sds-message-actions'));
      await button('הצגת הודעה חדשה').click();check(`${theme}: new-only animation`,await page.locator('.sds-user-bubble--new').evaluate(e=>getComputedStyle(e).animationName)==='sds-message-enter');
      await button('צמצום תנועה').click();check(`${theme}: explicit reduced motion`,await page.locator('.sds-user-bubble').last().evaluate(e=>getComputedStyle(e).animationName)==='none');
      await button('צמצום תנועה').click();await page.emulateMedia({reducedMotion:'reduce'});check(`${theme}: OS reduced motion`,await page.locator('.sds-user-bubble').last().evaluate(e=>getComputedStyle(e).animationName)==='none');await page.emulateMedia({reducedMotion:'no-preference'});
      await page.waitForTimeout(250);check(`${theme}: entrance consumed without replay`,await page.locator('.sds-user-bubble--new').count()===0);
      const tabs=page.getByRole('tab',{name:'שיחה ותוצרים'});await tabs.focus();await tabs.press('ArrowLeft');check(`${theme}: RTL tab arrow moves visually left`,await page.getByRole('tab',{name:'מצבי מערכת'}).getAttribute('aria-selected')==='true');
      await button('חלון צר').click();await page.getByRole('tab',{name:'רכיבים',exact:true}).click();await trigger.click();const menuBox=await page.getByRole('menu').boundingBox();check(`${theme}: narrow popover stays in viewport`,menuBox.x>=0&&menuBox.x+menuBox.width<=1380);await page.keyboard.press('Escape');
      void ring;
    }
    // Actual narrow window: dialog, menu, touch targets, reduced motion and system theme.
    await open('dark','controls',360,653);await button('שינוי שם').click();let bounds=await page.getByRole('dialog').boundingBox();check('360px modal within window',bounds.x>=0&&bounds.x+bounds.width<=360&&bounds.y>=0&&bounds.y+bounds.height<=653);await page.waitForTimeout(250);await page.screenshot({path:path.join(output,'dark-narrow-dialog.png')});await page.keyboard.press('Escape');
    await button('פעולות המסמך').click();bounds=await page.getByRole('menu').boundingBox();check('360px menu within window',bounds.x>=0&&bounds.x+bounds.width<=360&&bounds.y>=0&&bounds.y+bounds.height<=653);await page.keyboard.press('Escape');
    const targets=await page.locator('button:visible').evaluateAll(nodes=>nodes.filter(n=>!n.disabled).map(n=>({label:n.getAttribute('aria-label')||n.textContent,width:n.getBoundingClientRect().width,height:n.getBoundingClientRect().height})));check('all sample button targets at least 40px',targets.every(t=>t.width>=39.9&&t.height>=39.9));
    await page.emulateMedia({colorScheme:'dark'});await button('מערכת').click();check('system theme resolves dark',await page.locator('.sds-root').getAttribute('data-theme')==='dark');await page.emulateMedia({colorScheme:'light'});await page.waitForFunction(()=>document.querySelector('.sds-root').dataset.theme==='light');check('system theme responds to OS change',await page.locator('.sds-root').getAttribute('data-theme')==='light');
    await page.emulateMedia({forcedColors:'active'});await page.getByRole('textbox',{name:'שם',exact:true}).focus();await page.keyboard.press('ArrowRight');check('forced colors retains focus outline',await page.getByRole('textbox',{name:'שם',exact:true}).evaluate(e=>getComputedStyle(e).outlineStyle!=='none'));await page.screenshot({path:path.join(output,'forced-colors.png'),fullPage:true});await page.emulateMedia({forcedColors:'none'});
    const touch=await browser.newContext({hasTouch:true,viewport:{width:360,height:653}});
    await touch.route('**/*',route=>{const url=route.request().url();if(url.startsWith(base+'/')||url.startsWith('data:'))return route.continue();remote.push(url);return route.abort();});
    const touchPage=await touch.newPage();touchPage.on('pageerror',e=>errors.push(e.message));await touchPage.goto(`${base}/ux-2.html?theme=dark`);await touchPage.locator('.gallery-frame').waitFor();
    const touchSwitch=touchPage.getByRole('switch',{name:'הפעלת הכלי',exact:true});await touchSwitch.tap();check('touch switch remains directly operable',!await touchSwitch.isChecked());
    await touchPage.getByRole('button',{name:'פעולות המסמך',exact:true}).tap();check('touch opens action menu without hover',await touchPage.getByRole('menu').isVisible());await touchPage.getByRole('menuitem',{name:'מחיקה',exact:true}).tap();check('touch selects confirmation action',await touchPage.getByRole('alertdialog').isVisible());await touchPage.getByRole('button',{name:'ביטול',exact:true}).tap();check('touch confirmation cancellation',await touchPage.getByRole('alertdialog').count()===0);await touch.close();
    check('no runtime errors',errors.length===0);check('no remote/Core requests',remote.length===0);check('no personal storage reads or writes',!errors.some(e=>e.includes('Storage')));
    const values=contrasts.flatMap(c=>c.values);
    await save();console.log(JSON.stringify({checks:checks.length,layouts:layouts.length,contrastSamples:contrasts.length,textPairs:values.filter(v=>v.kind==='text').length,minTextContrast:Math.min(...values.filter(v=>v.kind==='text').map(v=>v.ratio)),nonTextPairs:values.filter(v=>v.kind!=='text').length,minNonTextContrast:Math.min(...values.filter(v=>v.kind!=='text').map(v=>v.ratio)),errors,remote,output}));
  } catch(error) {await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});await save();throw error;} finally {await browser.close();}
}
run().catch(error=>{console.error(error);process.exitCode=1;});
