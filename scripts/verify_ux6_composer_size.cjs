// Focused browser regression on the real Composer fixture. No Core/account/native UI.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

async function main() {
  const base = process.argv[2] || 'http://127.0.0.1:1458';
  const output = path.resolve(process.argv[3] || '.codex-local/ux-6/central/composer-size.json');
  const source = execFileSync('python', ['scripts/verify_ux6_acceptance.py', '--fingerprint'], { windowsHide:true, encoding:'utf8' }).trim();
  const browser = await chromium.launch({channel:'msedge',headless:true});
  const cases = [], errors = [];
  try {
    for (const theme of ['light','dark']) for (const width of [360,1302]) {
      const page = await browser.newPage({viewport:{width,height:900}});
      page.on('pageerror', e => errors.push(e.message));
      await page.route('**/?visual-fixture=*', async route => {
        const response = await route.fetch();
        await route.fulfill({response,body:(await response.text()).replace('</head>','<style id="initial-width">.composer-design{width:40px!important}</style></head>')});
      });
      await page.goto(`${base}/?visual-fixture=point16a&theme=${theme}&provider=local`);
      const area = page.getByRole('textbox',{name:'הודעה',exact:true});
      await area.waitFor();
      const measure = () => area.evaluate(t => ({height:t.getBoundingClientRect().height,min:parseFloat(getComputedStyle(t).minHeight),max:parseFloat(getComputedStyle(t).maxHeight),scroll:t.scrollHeight,width:t.clientWidth}));
      const initial = await measure();
      assert.equal(initial.height, initial.min, 'A wrapped placeholder must not enlarge the empty input');
      await page.locator('#initial-width').evaluate(e => e.remove());
      await page.waitForFunction(() => {const t=document.querySelector('.composer textarea');return t.clientWidth>100 && t.getBoundingClientRect().height===parseFloat(getComputedStyle(t).minHeight);});
      const empty = await measure();
      await area.fill(Array(12).fill('שלום English').join('\n'));
      const long = await measure();
      assert.equal(long.height,long.max);assert.ok(long.scroll>long.height, 'Long drafts keep an internal scroll area');
      await area.fill('שלום English '.repeat(8));
      await page.locator('.composer-design').evaluate(e => e.style.width='60px');
      await page.waitForFunction(() => {const t=document.querySelector('.composer textarea');return t.getBoundingClientRect().height===parseFloat(getComputedStyle(t).maxHeight);});
      const narrow = await measure();
      await page.locator('.composer-design').evaluate(e => e.style.removeProperty('width'));
      await page.waitForFunction(() => {const t=document.querySelector('.composer textarea');return t.clientWidth>100 && t.getBoundingClientRect().height<parseFloat(getComputedStyle(t).maxHeight);});
      const expanded = await measure();
      assert.equal(await area.inputValue(),'שלום English '.repeat(8), 'Width changes preserve the draft');
      await area.fill('');
      const cleared = await measure();
      assert.equal(cleared.height,cleared.min);
      const controls = await page.locator('.composer').evaluate(e => {
        const r=e.getBoundingClientRect(),a=[...e.querySelectorAll('.composer-primary,.composer-tool')].map(n=>n.getBoundingClientRect());
        return a.every(q=>q.width>=40 && q.height>=40 && q.left>=r.left && q.right<=r.right && q.top>=r.top && q.bottom<=r.bottom);
      });
      assert.ok(controls, 'Send/microphone and attachment actions retain their targets and containment');
      cases.push({theme,width,initial,empty,long,narrow,expanded,cleared,controls});
      await page.close();
    }
    assert.equal(errors.length,0);
    await fs.mkdir(path.dirname(output),{recursive:true});
    await fs.writeFile(output,JSON.stringify({source_sha256:source,cases,errors,scope:'Real Composer in isolated DEV fixture, Edge headless, light/dark and narrow/wide. Initial narrow mount, same-draft width changes, long/cleared input and action containment. No Tauri/Windows DPI/package claim.'},null,2));
    console.log('Composer size regression passed: four light/dark and narrow/wide cases');
  } finally {await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
