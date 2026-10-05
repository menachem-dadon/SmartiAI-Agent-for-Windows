// Provider artwork and selection in the owned isolated Rust/Core/WebView2 app.
const { chromium } = require('playwright');
const fs = require('node:fs/promises'), path = require('node:path'), assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process'), { randomUUID } = require('node:crypto');
async function main() {
  const output = path.resolve('.codex-local/ux-5/provider-icons-native'); await fs.mkdir(output, { recursive: true });
  const launch = JSON.parse(await fs.readFile('.codex-local/ux-5/native-launch.json', 'utf8'));
  assert.match(String(launch.pid), /^\d+$/);
  const executable = String(execFileSync('pwsh', ['-NoProfile', '-Command', `[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); (Get-Process -Id ${launch.pid}).Path`], { windowsHide: true })).trim();
  assert.equal(path.win32.basename(executable).toLowerCase(), 'ux5-native.exe');
  assert.equal(path.resolve(executable), path.resolve(launch.executable));
  assert.ok(path.resolve(launch.data).startsWith(path.resolve('.codex-local/ux-5/native-data-')));
  assert.equal(launch.cdp, 'http://127.0.0.1:19457');
  const browser = await chromium.connectOverCDP(launch.cdp);
  const page = browser.contexts()[0].pages().find(p => p.url().startsWith('http://127.0.0.1:1439/')); assert.ok(page);
  const invoke = (cmd, args = {}) => page.evaluate(({ cmd, args }) => window.__TAURI_INTERNALS__.invoke(cmd, args), { cmd, args });
  assert.equal(await invoke('plugin:app|identifier'), 'ai.smarti.ux5native');
  const api = async (method, route, body) => {
    const r = await invoke('core_api', { request: { method, path: route, body: body ?? null, idempotencyKey: method === 'GET' ? null : randomUUID() } });
    assert.equal(r.status, 200); return r.body.data;
  };
  const checks = [], geometry = [], errors = []; page.on('pageerror', e => errors.push(e.message));
  const check = (name, ok) => { assert.ok(ok, name); checks.push(name); console.log(name); };
  const resize = width => execFileSync('pwsh', ['-NoProfile', '-File', 'scripts/resize_ux5_window.ps1', '-ProbeProcessId', String(launch.pid), '-Width', String(width), '-Height', '900'], { windowsHide: true });
  const openSettings = async () => { await page.reload(); await page.locator('.chat-column').waitFor(); await page.getByRole('button', { name: 'הגדרות', exact: true }).click(); };
  const trigger = page.locator('.source-provider-picker > button'), options = page.getByRole('listbox', { name: 'ספקי מודלים' });
  try {
    resize(1380); await page.reload(); await page.locator('.chat-column').waitFor();
    await api('PATCH', '/v2/settings', { values: { api_mode: 'local', updates_auto_check: false, ui_preferences: { theme_mode: 'light', settings_show_advanced: true } } });
    for (const theme of ['light', 'dark']) {
      await api('PATCH', '/v2/settings', { values: { ui_preferences: { theme_mode: theme } } }); await openSettings();
      for (const width of [360, 500, 900, 1380]) {
        resize(width); await trigger.click(); await options.waitFor();
        await page.keyboard.press('Home');
        const measurements = await options.evaluate(async list => {
          const rect = e => { const r = e.getBoundingClientRect(); return { x: r.x, right: r.right, y: r.y, width: r.width, height: r.height }; };
          const rows = await Promise.all([...list.querySelectorAll('[role="option"]')].map(async row => {
            const icon = row.querySelector('.source-provider-icon'), name = row.querySelector('bdi');
            const style = getComputedStyle(icon), src = icon instanceof HTMLImageElement ? icon.src : style.maskImage.slice(4, -1).replace(/^["']|["']$/g, '');
            const loaded = await new Promise(resolve => { const image = new Image(); image.onload = () => resolve(image.naturalWidth > 0); image.onerror = () => resolve(false); image.src = src; });
            return { provider: row.dataset.provider, icon: rect(icon), name: rect(name), row: rect(row), loaded, color: style.backgroundColor };
          }));
          const popup = list.closest('.sds-popover'); return { rows, popup: rect(popup), radius: parseFloat(getComputedStyle(popup).borderRadius), overflow: popup.scrollWidth - popup.clientWidth, viewport: innerWidth, scale: devicePixelRatio };
        });
        const prefix = `${theme}/${width}`;
        check(`${prefix} all eighteen local assets load`, measurements.rows.length === 18 && measurements.rows.every(row => row.loaded));
        check(`${prefix} artwork physically right with consistent targets`, measurements.rows.every(row => row.icon.x >= row.name.right + 7 && row.icon.width === 20 && row.icon.height === 20 && row.row.height >= 43));
        check(`${prefix} rounded floating menu stays inside viewport`, measurements.popup.x >= 15 && measurements.popup.right <= width - 15 && measurements.overflow <= 1 && measurements.radius === 16);
        geometry.push({ theme, width, ...measurements });
        if ([360,1380].includes(width)) await page.screenshot({ path: path.join(output, `${theme}-${width}.png`) });
        await page.keyboard.press('End');
        check(`${prefix} keyboard reaches local provider`, await options.getByRole('option', { name: 'שרת מקומי', exact: true }).evaluate(e => e === document.activeElement));
        await page.keyboard.press('Escape');
        check(`${prefix} Escape keeps management and returns focus`, await page.locator('.management-overlay').isVisible() && await trigger.evaluate(e => e === document.activeElement));
      }
    }
    resize(1380); await trigger.focus(); await page.keyboard.press('ArrowDown'); await options.waitFor();
    check('opening focuses the saved provider', await options.getByRole('option', { name: 'שרת מקומי', exact: true }).evaluate(e => e === document.activeElement));
    await options.getByRole('option', { name: 'Google Gemini', exact: true }).click(); await options.waitFor({ state: 'hidden' });
    check('choosing provider saves through actual Core', (await api('GET', '/v2/settings')).values.api_mode === 'gemini');
    await openSettings();
    check('chosen provider and icon survive reload', await page.locator('.source-provider-picker').getAttribute('data-provider') === 'gemini' && await trigger.locator('.source-provider-icon').count() === 1);
    await trigger.click(); await page.keyboard.press('Tab');
    check('Tab exits the picker without writing another choice', await options.count() === 0 && (await api('GET', '/v2/settings')).values.api_mode === 'gemini');
    await api('PATCH', '/v2/settings', { values: { api_mode: 'local', ui_preferences: { theme_mode: 'light' } } }); await openSettings();
    check('no native renderer exceptions', errors.length === 0);
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify({ checks, errors, geometry, scope: 'owned isolated Rust/Core/WebView2, 125% Windows; no personal data, live provider calls, system dialogs or package acceptance' }, null, 2));
  } catch (error) {
    await page.screenshot({ path: path.join(output, 'failure.png') }).catch(() => {});
    await fs.writeFile(path.join(output, 'failure.json'), JSON.stringify({ error: String(error), checks, errors }, null, 2)); throw error;
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
