// Actual streamed Markdown in isolated Core/browser QA, without live inference.
const {browserQA}=require('./ux6_browser_support.cjs');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
async function main(){
 const q=await browserQA({env:{CHAT_STREAM_QA:'1',UX6_STRESS_QA:'0'}}),{page}=q;
 const output='.codex-local/chat-reveal';await fs.mkdir(output,{recursive:true});
 const results=[];
 try{
  await page.goto(process.argv[2]||'http://127.0.0.1:1453');await page.locator('.chat-welcome').waitFor();
  for(const theme of ['light','dark'])for(const width of [1380,640]){
   console.log('Checking reveal',theme,width);
   await q.api('PATCH','/v2/settings',{values:{ui_preferences:{theme_mode:theme}}});
   await page.evaluate(theme=>localStorage.setItem('smarti.desktop.theme',theme),theme);
   await page.setViewportSize({width:1380,height:900});await page.reload();
   const title='שיחה נוספת';
   await page.locator('.conversation-row').filter({has:page.getByText(title,{exact:true})}).locator('.conversation-select').click();
   await page.getByRole('heading',{name:title,exact:true}).waitFor();
   await page.setViewportSize({width,height:900});
   await page.getByRole('textbox',{name:'הודעה',exact:true}).fill('stream-reveal');await page.getByRole('textbox',{name:'הודעה',exact:true}).press('Enter');
   await page.waitForFunction(()=>{const row=[...document.querySelectorAll('.chat-message-row--assistant')].at(-1),nodes=row?.querySelectorAll('.stream-reveal');return nodes?.length>=6 && Number(getComputedStyle(nodes[0]).opacity)===1 && Number(getComputedStyle(nodes[nodes.length-1]).opacity)<.9;});
   const sample=await page.locator('.chat-message-row--assistant').last().evaluate(row=>{
    const nodes=[...row.querySelectorAll('.stream-reveal')],old=nodes[0],fresh=nodes.at(-1),s=getComputedStyle(fresh),parent=getComputedStyle(fresh.parentElement);
    const liveOpacities=nodes.slice(-5).map(node=>Number(getComputedStyle(node).opacity));
    const p=fresh.closest('p'),clone=p.cloneNode(true);clone.textContent=p.textContent;clone.style.cssText=`position:absolute;visibility:hidden;width:${p.clientWidth}px`;p.parentElement.appendChild(clone);
    const bounds=node=>{const range=document.createRange();range.selectNodeContents(node);const r=range.getBoundingClientRect();return{width:r.width,height:r.height};};const layout={actual:bounds(p),plain:bounds(clone)};clone.remove();
    const animation=fresh.getAnimations()[0];animation.pause();fresh.style.animationDelay='0ms';
    const phases=[0,150,300,450].map(time=>{animation.currentTime=time;return{time,opacity:Number(getComputedStyle(fresh).opacity)};});
    animation.play();
    return{oldOpacity:Number(getComputedStyle(old).opacity),gradient:s.backgroundImage,filter:s.filter,color:s.color,parentColor:parent.color,weight:s.fontWeight,parentWeight:parent.fontWeight,liveOpacities,layout,phases};
   });
   assert.equal(sample.gradient,'none');assert.equal(sample.filter,'none');assert.equal(sample.color,sample.parentColor);assert.equal(sample.weight,sample.parentWeight);
   assert.ok(sample.oldOpacity>.99,JSON.stringify(sample));
   assert.ok(new Set(sample.liveOpacities).size>=3,JSON.stringify(sample));
   assert.ok(sample.liveOpacities.every((opacity,index)=>!index||opacity<=sample.liveOpacities[index-1]));
   assert.ok(Math.abs(sample.layout.actual.width-sample.layout.plain.width)<1 && Math.abs(sample.layout.actual.height-sample.layout.plain.height)<1,JSON.stringify(sample.layout));
   assert.ok(sample.phases[0].opacity<.2 && sample.phases.at(-1).opacity===1);
   assert.ok(sample.phases.every((phase,index)=>!index||phase.opacity>sample.phases[index-1].opacity));
   await page.screenshot({path:`${output}/${theme}-${width}.png`});
   results.push({theme,width,sample});
   await page.getByRole('button',{name:'עצירה',exact:true}).click();
   await page.getByRole('button',{name:'עצירה',exact:true}).waitFor({state:'hidden'});
   await page.getByText('היצירה נעצרה. התשובה שהתקבלה עד העצירה נשמרה.',{exact:true}).last().waitFor();
   await page.setViewportSize({width:1380,height:900});
   const conversation=page.locator('.conversation-row').filter({has:page.getByText('בדיקת צירופים',{exact:true})});await conversation.locator('.conversation-select').click();
   await page.getByRole('button',{name:'הרחב הודעה',exact:true}).waitFor();
   await page.setViewportSize({width,height:900});
   await page.locator('.chat-stage').evaluate(stage=>{const bubble=stage.querySelector('.sds-user-bubble');stage.scrollTop+=bubble.getBoundingClientRect().top-stage.getBoundingClientRect().top-16;});
   await page.screenshot({path:`${output}/bubble-${theme}-${width}.png`});
  }
  for(const mode of ['system','preference','forced-colors']){
   await page.emulateMedia({reducedMotion:mode==='system'?'reduce':'no-preference',forcedColors:mode==='forced-colors'?'active':'none'});
   await page.locator('.chat-design').evaluate((node,mode)=>{node.dataset.reducedMotion=String(mode==='preference');const span=document.createElement('span');span.className='stream-reveal';span.id='qa-static-reveal';span.textContent='תשובה קריאה';node.appendChild(span);},mode);
   const staticText=await page.locator('#qa-static-reveal').last().evaluate(node=>{const s=getComputedStyle(node);return{animation:s.animationName,opacity:s.opacity,color:s.color};});
   assert.equal(staticText.animation,'none');assert.equal(staticText.opacity,'1');assert.notEqual(staticText.color,'rgba(0, 0, 0, 0)');results.push({mode,staticText});
  }
  await fs.writeFile(output+'/report.json',JSON.stringify({scope:'Edge browser, actual streamed Markdown from isolated Core with deterministic provider; no native inference claim',results},null,2));
  console.log('4 actual letter-by-letter streamed-text/bubble visual cases, continuous letter opacity/layout, fade phases and 3 static accessibility cases passed');
 }catch(error){await page.screenshot({path:output+'/failure.png'});console.log(await page.locator('.chat-stage').textContent());throw error;}finally{await q.close();}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
