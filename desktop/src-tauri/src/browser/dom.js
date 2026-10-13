// Installed in a named isolated world, never exposed to site scripts. DOM is
// untrusted data. References identify actual nodes and expire with the document.
(request) => {
  // getRandomValues also works on HTTP/about:blank; randomUUID requires HTTPS.
  const state = globalThis.__smartiAgent ??= {epoch: Array.from(crypto.getRandomValues(new Uint8Array(16)), b=>b.toString(16).padStart(2,'0')).join(''), refs: new Map(), sequence: 0, highlights: new WeakMap()};
  const roots = [];
  const collect = root => {
    roots.push(root);
    for (const el of root.querySelectorAll('*')) if (el.shadowRoot) collect(el.shadowRoot);
  };
  collect(document);
  const all = selector => roots.flatMap(root => [...root.querySelectorAll(selector)]);
  const role = el => el.getAttribute('role') || ({A:'link',BUTTON:'button',TEXTAREA:'textbox',SELECT:'combobox',IMG:'img',SUMMARY:'button',H1:'heading',H2:'heading',H3:'heading',H4:'heading',H5:'heading',H6:'heading',MAIN:'main',NAV:'navigation',DIALOG:'dialog'}[el.tagName]) || (el.tagName === 'INPUT' ? ({checkbox:'checkbox',radio:'radio',button:'button',submit:'button',range:'slider'}[el.type] || 'textbox') : el.tagName.toLowerCase());
  const name = el => (el.getAttribute('aria-label') || (el.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ').trim() || [...(el.labels || [])].map(l => l.textContent).join(' ') || el.getAttribute('alt') || el.getAttribute('placeholder') || el.innerText || el.getAttribute('title') || '').trim().replace(/\s+/g,' ').slice(0,240);
  const visible = el => {const r=el.getBoundingClientRect(),s=getComputedStyle(el);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'&&s.opacity!=='0';};
  const info = el => {
    const r=el.getBoundingClientRect();
    const parent=el.parentElement||el.getRootNode().host;
    return {role:role(el),name:name(el),tag:el.tagName.toLowerCase(),level:/^H[1-6]$/.test(el.tagName)?Number(el.tagName[1]):undefined,parentRole:parent?role(parent):undefined,visible:visible(el),enabled:!el.disabled&&el.getAttribute('aria-disabled')!=='true',editable:el.isContentEditable||(!el.readOnly&&(el.tagName==='TEXTAREA'||el.tagName==='INPUT'&&!['checkbox','radio','button','submit','reset','file','range','hidden'].includes(el.type))),checked:el.checked??el.getAttribute('aria-checked'),value:el.type==='password'?'[redacted]':('value' in el?String(el.value):undefined),options:el.tagName==='SELECT'?[...el.options].map(o=>({value:o.value,label:o.label,selected:o.selected,disabled:o.disabled})):undefined,href:el.tagName==='A'?el.href:undefined,box:{x:r.x,y:r.y,width:r.width,height:r.height}};
  };
  const resolve = () => {
    if (request.snapshotEpoch && request.snapshotEpoch !== state.epoch || request.refEpoch && request.refEpoch !== state.epoch) throw Error('STALE_REF: request a new snapshot');
    let candidates;
    if(request.ref){const el=state.refs.get(request.ref);if(!el?.isConnected)throw Error('STALE_REF: request a new snapshot');candidates=[el];}
    else if(request.selector)candidates=all(request.selector);
    else if(request.role)candidates=all('*').filter(el=>role(el)===request.role&&(!request.name||(request.exact?name(el)===request.name:name(el).includes(request.name))));
    else if(request.textSelector)candidates=all('*').filter(el=>(request.exact?name(el)===request.textSelector:name(el).includes(request.textSelector))&&!Array.from(el.children).some(c=>name(c).includes(request.textSelector)));
    else throw Error('TARGET_REQUIRED: use ref, role/name, textSelector or selector');
    if(request.nth!==undefined)candidates=candidates.slice(Number(request.nth),Number(request.nth)+1);
    if(candidates.length!==1)throw Error(candidates.length?'AMBIGUOUS_TARGET: '+candidates.length+' matches; narrow the target':'TARGET_NOT_FOUND');
    return candidates[0];
  };
  const snapshot = () => {
    const max=Math.min(500,Math.max(1,Number(request.limit??request.maxElements??80))),offset=Math.max(0,Number(request.offset||0));
    const elements=all('a,button,input,textarea,select,summary,img,h1,h2,h3,h4,h5,h6,main,nav,dialog,[role],[contenteditable=true]').filter(el=>(request.includeHidden||visible(el))&&(!request.selector||el.matches(request.selector))&&(!request.role||role(el)===request.role)&&(!request.name||name(el).includes(request.name))&&(!request.textSelector||name(el).includes(request.textSelector)));
    // Keep old refs valid in the same document, but bound detached-node retention.
    for(const [ref,el] of state.refs)if(!el.isConnected)state.refs.delete(ref);
    const reverse=new Map([...state.refs].map(([ref,el])=>[el,ref]));
    const refs={};
    for(const el of elements.slice(offset,offset+max)){let ref=reverse.get(el);if(!ref){ref=`e${state.epoch.replaceAll('-','').slice(0,12)}-${++state.sequence}`;state.refs.set(ref,el);reverse.set(el,ref);}refs[ref]={ref,...info(el)};}
    for(const el of elements.slice(offset,offset+max)){let parent=el.parentElement||el.getRootNode().host;while(parent){const ref=reverse.get(parent);if(ref){refs[reverse.get(el)].parentRef=ref;break;}parent=parent.parentElement||parent.getRootNode().host;}}
    const originalText=document.body?.innerText||'';
    let text=originalText,removedAds=0;
    if(request.detail!=='full')for(const ad of all('ins.adsbygoogle,[data-ad-slot],[data-google-query-id]')){
      // Explicit ad-provider markers only. Never infer ads from words, banner
      // roles, or CSS class substrings; preserve forms and dialogs even here.
      if(ad.closest('form,[contenteditable=true],[role=dialog]')||ad.querySelector('form,input,textarea,[contenteditable=true],[role=dialog]'))continue;
      const value=ad.innerText?.trim();
      if(value&&text.indexOf(value)>=0&&text.indexOf(value)===text.lastIndexOf(value)){text=text.replace(value,'');removedAds++;}
    }
    const textOffset=Math.max(0,Number(request.textOffset||0)),chars=request.bodyChars===undefined?text.length:Math.max(0,Number(request.bodyChars));
    return {snapshotEpoch:state.epoch,title:document.title,url:location.href,readyState:document.readyState,bodyText:text.slice(textOffset,textOffset+chars),textOffset,textLength:text.length,textTruncated:textOffset+chars<text.length,...(removedAds?{originalBodyText:originalText,contentFilter:{removedAds,originalTextLength:originalText.length}}:{}),refs,snapshot:Object.values(refs).map(e=>`${e.ref} ${e.role} ${JSON.stringify(e.name)}${e.enabled?'':' [disabled]'}${e.checked===true?' [checked]':''}`).join('\n'),offset,total:elements.length,hasMore:offset+max<elements.length,frames:all('iframe,frame').map(el=>({name:el.name,src:el.src,title:el.title})),dir:document.dir||getComputedStyle(document.documentElement).direction};
  };
  if(request.op==='snapshot')return snapshot();
  if(request.op==='text'){
    const text=request.selector||request.ref||request.role||request.textSelector?resolve().innerText:document.body?.innerText||'';
    const offset=Math.max(0,Number(request.offset||0)),limit=request.limit===undefined?text.length:Math.max(1,Number(request.limit));
    return {text:text.slice(offset,offset+limit),offset,total:text.length,hasMore:offset+limit<text.length};
  }
  const el=resolve();
  if(request.op==='object')return el;
  if(request.op==='select'){
    if(el.tagName!=='SELECT')throw Error('NOT_SELECT');
    const wanted=request.values||[request.value??request.text],options=[...el.options];
    if(!wanted.every(value=>options.some(o=>o.value===String(value)||o.label===String(value))))throw Error('OPTION_NOT_FOUND');
    for(const option of options)option.selected=wanted.some(v=>String(v)===option.value||String(v)===option.label);
    el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));
    return {values:[...el.selectedOptions].map(o=>o.value),verified:true};
  }
  if(request.op==='focus'){el.focus();return info(el);}
  if(request.op==='scroll'){el.scrollIntoView({block:'center',inline:'center'});return info(el);}
  if(request.op==='describe')return info(el);
  if(request.op==='prepare'){
    el.scrollIntoView({block:'center',inline:'center'});
    const i=info(el),r=el.getBoundingClientRect(),x=Math.max(0,Math.min(innerWidth-1,r.x+r.width/2)),y=Math.max(0,Math.min(innerHeight-1,r.y+r.height/2));
    const hit=el.getRootNode().elementFromPoint?.(x,y)||document.elementFromPoint(x,y);
    if(!i.visible)throw Error('TARGET_NOT_VISIBLE');
    if(!i.enabled)throw Error('TARGET_DISABLED');
    if(!hit||!(hit===el||el.contains(hit)))throw Error('TARGET_OBSCURED');
    if(['fill','type'].includes(request.action)&&!i.editable)throw Error('TARGET_NOT_EDITABLE');
    // Brief highlight follows the actual resolved element, with no fabricated cursor.
    const prior=state.highlights.get(el),record=prior||{outline:el.style.outline,offset:el.style.outlineOffset,timer:0};
    if(prior)clearTimeout(prior.timer);
    // Smarti's shared action color is identical in light and dark palettes.
    el.style.outline='2px solid #397bfa';el.style.outlineOffset='3px';
    record.timer=setTimeout(()=>{el.style.outline=record.outline;el.style.outlineOffset=record.offset;state.highlights.delete(el);},650);
    state.highlights.set(el,record);
    return {...i,x,y,verified:true};
  }
  throw Error('UNKNOWN_DOM_OPERATION');
}
