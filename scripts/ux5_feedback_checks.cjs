// Rendered product checks, reusable for isolated Edge and native WebView2.
async function verifyManagementFeedback(page, record, prefix, requireExtensions = true) {
  const result = await page.locator('.management-overlay').evaluate(root => {
    const rect = e => { const r = e.getBoundingClientRect(); return { x:r.x, y:r.y, right:r.right, width:r.width, height:r.height }; };
    const button = name => [...root.querySelectorAll('button')].find(b => b.getAttribute('aria-label') === name || b.textContent.trim() === name);
    const adjacent = (a,b) => Boolean(a && b && rect(a).right <= rect(b).x + 1 && Math.abs(rect(a).y - rect(b).y) <= 1);
    const search = root.querySelector('.management-page>.sds-search,.source-settings-search');
    const segments = [...root.querySelectorAll('.sds-segmented')];
    const extensions = [...root.querySelectorAll('.source-tool-row:not([data-kind="builtin"])')];
    const builtins = [...root.querySelectorAll('.source-tool-row[data-kind="builtin"]')];
    return {
      navSearch: root.querySelector('nav .sds-search') !== null,
      search: search ? { ...rect(search), parent:rect(search.parentElement) } : null,
      segments: segments.length ? segments.every(e => parseFloat(getComputedStyle(e).borderTopWidth) > 0 && [...e.querySelectorAll('button')].every(b => getComputedStyle(b).borderTopWidth === '0px')) : null,
      usage: root.querySelector('.usage-page') ? adjacent(button('ניקוי נתונים'),button('רענון')) : null,
      memory: button('זיכרון חדש') ? {
        actions: adjacent(button('ניקוי כל הזיכרונות'),button('רענון זיכרונות')),
        icons: ['זיכרון חדש','ייבוא מוצפן','ייצוא מוצפן'].every(name => button(name)?.querySelector('svg')),
        primary: button('זיכרון חדש').classList.contains('sds-button--primary'),
      } : null,
      tools: builtins.length ? {
        count: builtins.length, labels: root.querySelectorAll('.source-tool-row .sds-badge').length,
        descriptions: builtins.every(e => { const d=e.querySelector('small'), style=getComputedStyle(d); return /[א-ת]/.test(d.textContent) && d.textContent.length <= 100 && rect(d).height <= 2*parseFloat(style.lineHeight)+1; }),
        extensionCount: extensions.length,
        fixtureCount: extensions.filter(e => e.querySelector('.source-tool-name b').textContent.startsWith('ux5_')).length,
        extensions: extensions.every(e => { const name=e.querySelector('.source-tool-name'), remove=e.querySelector('.source-tool-delete'), toggle=e.querySelector('.source-tool-toggle'); return getComputedStyle(name).textAlign === 'right' && rect(name).right > rect(toggle).right && (!remove || (rect(name).right > rect(remove).right && rect(remove).x >= rect(toggle).right-1)); }),
        headings: [...root.querySelectorAll('.source-tools-section>header')].filter(e => e.querySelector('button')).every(e => rect(e.querySelector('h3')).right > rect(e.querySelector('button')).right),
      } : null,
    };
  });
  record(`${prefix} navigation without screen search`, !result.navSearch);
  if (result.search) record(`${prefix} half-width search physically right`, Math.abs(result.search.width/result.search.parent.width-.5)<.02 && Math.abs(result.search.right-result.search.parent.right)<=1);
  if (result.segments !== null) record(`${prefix} unified segmented frame`, result.segments);
  if (result.usage !== null) record(`${prefix} clear left of refresh on one row`, result.usage);
  if (result.memory) record(`${prefix} memory primary icons and header clear`, result.memory.actions && result.memory.icons && result.memory.primary);
  if (result.tools) {
    const valid = result.tools.count===17 && result.tools.labels===0 && result.tools.descriptions && result.tools.extensions && result.tools.headings && (!requireExtensions || result.tools.fixtureCount===3);
    if (!valid) console.log('Tool layout diagnosis:', JSON.stringify(result.tools));
    record(`${prefix} concise Hebrew tools and physical RTL actions`, valid);
  }
  return result;
}

async function verifyFastMode(page, record, prefix) {
  const result = await page.locator('.composer').evaluate(e => {
    const rect = e => { const r=e.getBoundingClientRect(); return {x:r.x,y:r.y,right:r.right,width:r.width,height:r.height}; };
    return { model:rect(e.querySelector('.model-quick-pill summary')), fast:rect(e.querySelector('.local-fast-mode')), label:e.querySelector('.model-quick-pill .sds-hover-label').textContent, composer:rect(e) };
  });
  const valid=result.fast.x>=result.model.right-1 && Math.abs(result.fast.y+result.fast.height/2-result.model.y-result.model.height/2)<=1 && result.fast.right<=result.composer.right && result.model.x>=result.composer.x && result.model.width>=39 && result.fast.width>=44 && result.fast.height>=39 && result.composer.width<=698 && (!prefix.includes('very_long') || result.label.length>30);
  if (!valid) console.log('FastMode layout diagnosis:', JSON.stringify(result));
  record(`${prefix} FastMode right beside model`, valid);
  return result;
}
module.exports = { verifyManagementFeedback, verifyFastMode };
