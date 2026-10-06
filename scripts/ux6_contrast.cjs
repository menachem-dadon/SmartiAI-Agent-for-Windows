// Effective solid backgrounds and alpha, SVG paint and retained PNG samples.
// Derived from the UX-2 audit; this is not a complete WCAG or screen-reader audit.
async function sampleContrast(page) {
  const values = await page.evaluate(() => {
    const rgba = (value) => { const n = value.match(/[\d.]+/g)?.map(Number) || []; return [n[0] || 0, n[1] || 0, n[2] || 0, n.length > 3 ? n[3] : 1]; };
    const blend = (fg, bg) => [0,1,2].map(i => fg[i]*fg[3]+bg[i]*(1-fg[3])).concat(1);
    const background = (node) => { const chain=[]; for (let n=node;n;n=n.parentElement) chain.unshift(n); let color=[255,255,255,1]; for(const n of chain) color=blend(rgba(getComputedStyle(n).backgroundColor),color); return color; };
    const luminance = (color) => color.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
    const ratio = (fg,bg) => {const a=luminance(fg),b=luminance(bg);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);};
    const result=[];
    for(const element of document.querySelectorAll('.sds-root *')) {
      if (!element.getClientRects().length || element.closest('[hidden], [inert], [aria-hidden="true"]') || element.closest(':disabled')) continue;
      const style=getComputedStyle(element); if(style.visibility==='hidden') continue;
      if (!Array.from(element.childNodes).some(n=>n.nodeType===Node.TEXT_NODE&&n.textContent.trim()) && !element.matches('input:not([type="range"]):not([type="checkbox"]),textarea')) continue;
      const bg=background(element), fg=blend(rgba(style.color),bg);
      result.push({kind:'text',threshold:4.5,text:(element.textContent||element.value||element.placeholder||element.getAttribute('aria-label')||'').trim().slice(0,80),ratio:ratio(fg,bg),fg,bg});
      if(element.matches('input,textarea') && element.getAttribute('placeholder')) {const placeholder=blend(rgba(getComputedStyle(element,'::placeholder').color),bg);result.push({kind:'text',threshold:4.5,text:'placeholder',ratio:ratio(placeholder,bg),fg:placeholder,bg});}
    }
    for(const element of document.querySelectorAll('.sds-field:not(:disabled),.sds-switch input:not(:disabled)+.sds-switch-track,.sds-range:not(:disabled),.sds-root :focus-visible')) {
      if(!element.getClientRects().length||element.closest('[hidden], [inert], [aria-hidden="true"]'))continue;
      const style=getComputedStyle(element),bg=background(element.parentElement);
      const isRange=element.matches('.sds-range'),isField=element.matches('.sds-field'),isTrack=element.matches('.sds-switch-track');
      const border=rgba(isRange?getComputedStyle(element,'::-webkit-slider-runnable-track').outlineColor:style.borderColor);
      if(isField||isRange||isTrack)result.push({kind:'boundary',threshold:3,text:element.className,ratio:ratio(blend(border,bg),bg),fg:border,bg});
      if(element.matches(':focus-visible')&&style.outlineStyle!=='none'&&parseFloat(style.outlineWidth)>0) {const fg=rgba(style.outlineColor);result.push({kind:'focus',threshold:3,text:'focus ring',ratio:ratio(blend(fg,bg),bg),fg,bg});}
    }
    for(const element of document.querySelectorAll('.sds-icon')) {
      if(!element.getClientRects().length||element.closest('[hidden], [inert], [aria-hidden="true"]')||element.closest(':disabled'))continue;
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
  return values;
}
module.exports={sampleContrast};
