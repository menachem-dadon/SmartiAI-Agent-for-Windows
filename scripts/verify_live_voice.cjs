// Real React/Core/agent/tools; synthetic microphone and deterministic providers.
const { browserQA } = require('./ux6_browser_support.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
(async () => {
  let canary;
  const q = await browserQA({ host: 'scripts/live_voice_qa_host.py', browserArgs: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--enable-unsafe-swiftshader'], invoke: (command) => {
    if (command === 'stage_attachment') return canary;
    if (command === 'read_attachment_preview') return [];
    throw Error('Unadapted live QA IPC: '+command);
  } });
  canary = q.handshake.canary;
  const { page } = q, output = '.codex-local/live-fixes';
  await fs.mkdir(output, { recursive: true });
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error' && !message.text().startsWith('Failed to load resource')) errors.push(message.text()); });
  const results = [];
  try {
    await page.addInitScript(() => { const capture = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices); window.__liveQaTracks = []; navigator.mediaDevices.getUserMedia = async options => { const stream = await capture(options); window.__liveQaTracks.push(...stream.getTracks()); return stream; }; });
    await page.goto('http://127.0.0.1:1456');
    await page.getByRole('button', { name: 'פתיחת לייב', exact: true }).waitFor();
    const centered = async () => page.locator('.live-toggle').evaluate(button => {
      const b = button.getBoundingClientRect(), i = button.querySelector('.sds-icon').getBoundingClientRect();
      return Math.abs((b.left + b.right - i.left - i.right) / 2) < .6 && Math.abs((b.top + b.bottom - i.top - i.bottom) / 2) < .6;
    });
    assert(await centered(), 'waveform centered');
    assert.equal(await page.locator('.live-toggle [data-icon="voice"]').count(), 1);
    assert(await page.locator('.action-button-host').evaluate(node => node.querySelector('.live-toggle').getBoundingClientRect().right <= node.querySelector('.is-plain-mic').getBoundingClientRect().left), 'Live physically left of dictation');
    assert.equal(await page.locator('.composer-primary.is-plain-mic').count(), 1);
    await page.getByRole('button', { name: 'פתיחת לייב', exact: true }).click();
    await page.locator('.live-toggle[aria-busy="true"]').waitFor();
    assert(await centered(), 'spinner centered');
    await page.locator('.live-orb').waitFor();
    assert(await centered(), 'close icon centered');
    assert(await page.locator('.live-orb-area [role="status"]').evaluate(node => node.getBoundingClientRect().width <= 1 && getComputedStyle(node).clipPath === 'inset(50%)'), 'orb caption visually hidden');
    assert.equal((await q.api('POST', '/v2/audio/tts', { text: 'legacy TTS must be suspended', owner_id: 'qa' })).status, 503);
    assert.equal(await page.getByRole('button', { name: 'הכתבה קולית', exact: true }).isVisible(), false);
    await page.getByRole('textbox', { name: 'הודעה', exact: true }).fill('קרא את קובץ הבדיקה');
    await page.getByRole('textbox', { name: 'הודעה', exact: true }).press('Enter');
    await page.getByText('אני מפעיל את המשימה.', { exact: true }).waitFor();
    await page.locator('.agent-process').waitFor();
    await page.locator('.chat-stage').evaluate(node => { node.scrollTop = 0; node.dispatchEvent(new Event('scroll')); });
    await page.getByRole('textbox', { name: 'הודעה', exact: true }).fill('מה נשמע בינתיים');
    await page.getByRole('textbox', { name: 'הודעה', exact: true }).press('Enter');
    await page.getByText('אני איתך, הסוכן ממשיך לעבוד.', { exact: true }).waitFor();
    await page.waitForTimeout(300);
    const anchor = await page.locator('.chat-stage').evaluate(stage => {
      const user = [...stage.querySelectorAll('[data-message-id^="user:"]')].at(-1).querySelector('.sds-user-bubble');
      return user.getBoundingClientRect().top - stage.getBoundingClientRect().top;
    });
    assert(Math.abs(anchor - 16) < 3, `new Live user message scroll anchor ${anchor}`);
    await page.getByRole('button', { name: 'השהה משימה', exact: true }).click();
    await page.getByRole('button', { name: 'המשך משימה', exact: true }).waitFor();
    let paused = false;
    const pauseDeadline = Date.now() + 15000;
    while (Date.now() < pauseDeadline) {
      paused = (await q.api('GET','/v2/runs?limit=100')).body.data.items.some(run=>run.metadata?.paused);
      if (paused) break;
      const allow = page.getByRole('button',{name:'אשר',exact:true});
      if (await allow.count() && await allow.first().isEnabled()) await allow.first().click();
      await page.waitForTimeout(100);
    }
    assert(paused, 'worker actually entered its pause checkpoint');
    await page.getByRole('button', { name: 'המשך משימה', exact: true }).click();
    // Existing policy may request an explicit file-read approval.
    const until = Date.now() + 30000;
    while (Date.now() < until && !await page.getByText('המשימה הסתיימה. קראתי את קובץ הבדיקה והכנתי את התוצאה.', { exact: true }).count()) {
      const allow = page.getByRole('button', { name: 'אשר', exact: true });
      if (await allow.count() && await allow.first().isEnabled()) await allow.first().click();
      await page.waitForTimeout(150);
    }
    await page.getByText('המשימה הסתיימה. קראתי את קובץ הבדיקה והכנתי את התוצאה.', { exact: true }).waitFor({ timeout: 3000 });
    assert.equal(await page.locator('.agent-process').count(), 1);
    await page.locator('.message-content code').filter({ hasText: 'SMARTI_LIVE_CANARY_42' }).waitFor();
    assert.equal(await page.locator('.message-content code').filter({ hasText: 'SMARTI_LIVE_CANARY_42' }).count(), 1);
    assert.equal(await page.locator('.message-content table').count(), 1);
    const order = await page.locator('.chat-message-row').evaluateAll(rows => rows.map(row => ({ process: !!row.querySelector('.agent-process'), text: row.innerText })));
    const processIndex = order.findIndex(row => row.process);
    assert.match(order[processIndex - 1].text, /أنا|אני איתך/);
    assert.match(order[processIndex + 1].text, /המשימה הסתיימה/);
    for (const theme of ['light', 'dark']) for (const width of [1380, 640, 390]) {
      await page.evaluate(async theme => { const { coreApi } = await import('/src/coreApi.ts'); await coreApi('PATCH', '/v2/settings', { values: { ui_preferences: { theme_mode: theme } } }, true); }, theme);
      await page.locator(`.chat-design[data-theme="${theme}"]`).waitFor();
      await page.setViewportSize({ width, height: 940 });
      const geometry = await page.evaluate(() => {
        const orb = document.querySelector('.live-orb').getBoundingClientRect(), composer = document.querySelector('.composer').getBoundingClientRect(), panel = document.querySelector('.chat-composer-panel').getBoundingClientRect();
        return { orb: { bottom: orb.bottom, top: orb.top }, composer: { top: composer.top, width: composer.width }, panel: { top: panel.top }, overflow: document.querySelector('.chat-column').scrollWidth > document.querySelector('.chat-column').clientWidth };
      });
      assert(geometry.orb.bottom <= geometry.composer.top); assert(!geometry.overflow);
      assert(await centered(), `${theme}/${width} centered control`);
      if (await page.locator('.chat-new-content').count()) { await page.locator('.chat-new-content').click(); await page.waitForTimeout(250); }
      await page.screenshot({ path: `${output}/${theme}-${width}.png` });
      results.push({ theme, width, geometry });
    }
    await page.getByRole('button', { name: 'השתקת המיקרופון', exact: true }).click();
    await page.getByRole('button', { name: 'ביטול השתקת המיקרופון', exact: true }).waitFor();
    await page.getByRole('button', { name: 'השתקת סמארטי', exact: true }).click();
    await page.getByRole('button', { name: 'ביטול השתקת סמארטי', exact: true }).waitFor();
    await page.locator('input[type="file"]').setInputFiles({ name: 'live-canary.txt', mimeType: 'text/plain', buffer: Buffer.from('SMARTI_LIVE_CANARY_42') });
    await page.getByRole('textbox', { name: 'הודעה', exact: true }).fill('משימה חדשה: קרא את הקובץ המצורף');
    await page.getByRole('textbox', { name: 'הודעה', exact: true }).press('Enter');
    const attachmentDeadline = Date.now() + 30000;
    while (Date.now() < attachmentDeadline && await page.locator('.message-content code').count() < 2) {
      const allow = page.getByRole('button', { name: 'אשר', exact: true });
      if (await allow.count() && await allow.first().isEnabled()) await allow.first().click();
      await page.waitForTimeout(100);
    }
    await page.waitForFunction(() => document.querySelectorAll('.message-content code').length === 2, { timeout: 30000 });
    assert.equal(await page.locator('.agent-process').count(), 2);
    await page.getByRole('button', { name: 'סגירת לייב', exact: true }).click();
    await page.locator('.live-orb').waitFor({ state: 'detached' });
    await page.getByRole('button', { name: 'פתיחת לייב', exact: true }).waitFor();
    await page.setViewportSize({width: 1380, height: 940});
    await page.locator('.drawer-management').getByRole('button', {name:'הגדרות',exact:true}).click();
    const liveSwitch = page.getByRole('switch', {name:'אפשר מצב Live',exact:true});
    await liveSwitch.waitFor();
    const settingsGroup = page.locator('.sds-settings-group').filter({has:liveSwitch});
    assert(await settingsGroup.evaluate(group => {
      const text = document.querySelector('.source-provider-workflow');
      return !!(text.compareDocumentPosition(group) & Node.DOCUMENT_POSITION_FOLLOWING);
    }), 'Live after text models');
    assert.equal(await settingsGroup.getByLabel('מפתח API ללייב',{exact:true}).getAttribute('placeholder'), (await q.api('GET','/v2/live/config')).body.data.items.find(item=>item.id==='gemini').masked);
    await liveSwitch.uncheck();
    await page.waitForFunction(() => !document.querySelector('.live-settings [role="switch"]').checked && [...document.querySelectorAll('.live-settings input,.live-settings button')].filter(node=>node.getAttribute('role')!=='switch').every(node=>node.disabled));
    await liveSwitch.check();
    await settingsGroup.getByRole('button',{name:'שפת הלייב',exact:true}).click();
    await page.getByRole('option',{name:'אנגלית',exact:true}).click();
    await page.waitForFunction(() => !document.querySelector('.live-settings [role="switch"]').disabled);
    assert.equal((await q.api('GET','/v2/live/config')).body.data.language, 'en');
    await settingsGroup.getByRole('button',{name:'שפת הלייב',exact:true}).click();
    await page.getByRole('option',{name:'עברית',exact:true}).click();
    for (const theme of ['light','dark']) for (const width of [1380,640,390]) {
      await page.evaluate(async theme => {const {coreApi}=await import('/src/coreApi.ts');await coreApi('PATCH','/v2/settings',{values:{ui_preferences:{theme_mode:theme}}},true);},theme);
      await page.locator(`.chat-design[data-theme="${theme}"]`).waitFor();
      await page.setViewportSize({width,height:940});
      await settingsGroup.scrollIntoViewIfNeeded();
      assert(await settingsGroup.evaluate(group=>group.scrollWidth <= group.clientWidth), 'Live settings fit');
      await page.screenshot({path:`${output}/settings-${theme}-${width}.png`});
    }
    assert(await page.evaluate(() => window.__liveQaTracks.length > 0 && window.__liveQaTracks.every(track => track.readyState === 'ended')));
    assert.equal((await q.api('GET', '/v2/settings')).body.data.values.read_aloud_all, true);
    const conversations = (await q.api('GET', '/v2/conversations?limit=50')).body.data.items;
    const conversation = conversations.find(row => row.message_count > 0);
    const saved = (await q.api('GET', `/v2/conversations/${conversation.id}/messages?limit=100`)).body.data.messages;
    const process = saved.filter(row => row.metadata.live_process);
    assert.equal(process.length, 2);
    assert(saved.some(row => row.metadata.live_final && row.content.includes('SMARTI_LIVE_CANARY_42')));
    assert((await q.api('GET','/v2/runs?limit=100')).body.data.items.filter(run=>run.metadata?.live_task_id).every(run=>run.status==='completed'), 'both execution tasks completed successfully');
    assert.equal(errors.length, 0, errors.join('\n'));
    await fs.writeFile(`${output}/browser-report.json`, JSON.stringify({ scope: 'Isolated actual product UI/Core/agent/tools, deterministic provider and fake audio; no live vendor or personal microphone claim', results, settingsVisualCases:6, actualPauseCheckpoint:paused, newUserAnchor:anchor, messages: saved.length, processBlocks: process.length, errors }, null, 2));
    console.log('Live UI/Core integration, task grouping, tools, pause/resume, rich final, mute and six visual cases passed');
  } catch (error) {
    await page.screenshot({ path: `${output}/failure.png` }).catch(() => {});
    const conversations = (await q.api('GET','/v2/conversations?limit=50')).body.data.items;
    const saved = await Promise.all(conversations.filter(item=>item.message_count>0).map(item=>q.api('GET',`/v2/conversations/${item.id}/messages?limit=100`)));
    await fs.writeFile(`${output}/failure.json`, JSON.stringify({ error: String(error), errors, text: await page.locator('body').innerText(), config: await q.api('GET', '/v2/live/config'), runs: await q.api('GET','/v2/runs?limit=100'), saved, calls: q.calls }, null, 2));
    throw error;
  } finally { await q.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
