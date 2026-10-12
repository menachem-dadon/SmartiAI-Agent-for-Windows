"""Called by the isolated native harness; never connects to a user's Core/profile."""
import json
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tests  # Isolate data and keyring before importing Smarti.
from smarti.browser_control import SmartiBrowserController, UNTRUSTED_BROWSER_PREFIX
from smarti.agent.automation import AutomationMixin
from tests.test_doctor import _BrowserAutomationCore
from contextlib import nullcontext


def main():
    core = _BrowserAutomationCore()
    core.settings['browser_allow_private_network'] = True
    core._execution_context = SimpleNamespace(target_session_id='fixture-session', run_id='bridge-test', cancel_event=threading.Event())
    controller = core.browser_controller = SmartiBrowserController(core)
    core.run_resource_guard = lambda resource: nullcontext()
    tab = os.environ['SMARTI_TEST_BROWSER_TAB']
    def call(action, **args):
        print('bridge check: ' + action, flush=True)
        output = AutomationMixin.run_browser_action(core, {'action': action, 'tabId': tab, **args})
        if output.startswith('ERROR'):
            raise AssertionError(output)
        if output.startswith('ATTACHMENT_JSON:'):
            return json.loads(output.removeprefix('ATTACHMENT_JSON:'))
        assert output.startswith(UNTRUSTED_BROWSER_PREFIX), output
        value = json.loads(output.removeprefix(UNTRUSTED_BROWSER_PREFIX))
        assert value['ok'], value
        return value
    downloaded = None
    try:
        assert call('doctor')['protocolVersion'] == 2
        assert call('snapshot')['tabId'] == tab
        call('act', request={'kind': 'fill', 'selector': '#message', 'text': 'HTTP bridge verified'})
        assert call('evaluate', script='document.body.dataset.typed')['result'] == 'HTTP bridge verified'
        call('storage', op='add', storage='local', key='bridge-fixture', value=42)
        assert call('evaluate', script="localStorage.getItem('bridge-fixture')")['result'] == '42'
        call('storage', op='delete', key='bridge-fixture')
        assert call('evaluate', script="localStorage.getItem('bridge-fixture')")['result'] is None
        url=call('snapshot')['result']['url']
        call('cookies', op='add', cookies=[{'name':'bridge-fixture','value':'private-cookie-value','url':url}])
        cookies=call('cookies', op='get')['result']['cookies']
        assert any(cookie['name']=='bridge-fixture' and cookie['value']=='[redacted]' for cookie in cookies)
        call('cookies', op='delete', key='bridge-fixture')
        assert not any(cookie['name']=='bridge-fixture' for cookie in call('cookies')['result']['cookies'])
        image = call('screenshot', fullPage=True)
        assert Path(image['attachments'][0]['path']).read_bytes().startswith(b'\x89PNG')
        pdf = call('pdf')
        assert Path(pdf['path']).read_bytes().startswith(b'%PDF')
        upload = Path(core.tempdir.name, 'upload.txt')
        upload.write_text('native upload', encoding='utf-8')
        call('upload', selector='#upload', paths=[str(upload)])
        assert call('evaluate', script="document.querySelector('#upload').files[0].name")['result'] == 'upload.txt'
        value = call('click', selector='#download', expectDownload=True, downloadPath='bridge-fixture.txt')
        downloaded = Path(value['result']['path']).resolve()
        assert Path(value['path']).read_text(encoding='utf-8') == 'bridge download fixture'
        timer = threading.Timer(0.35, core._execution_context.cancel_event.set)
        timer.start()
        try:
            result = AutomationMixin.run_browser_action(core, {'action': 'wait', 'tabId': tab, 'selector': '#never-created', 'timeoutMs': 5000})
            assert result.startswith('ERROR: Browser run cancelled'), result
        finally:
            timer.cancel()
        core._execution_context.cancel_event.clear()
        core._execution_context.run_id = 'bridge-next-run'
        call('fill', selector='#message', text='next run works')
        print(json.dumps({'ok': True, 'checks': ['real Core controller HTTP routing', 'nested action', 'trusted typing', 'storage writes/removal', 'cookie redaction/removal', 'image attachment', 'PDF artifact', 'native upload', 'completed download artifact', 'in-flight cancellation fences input', 'next run can continue']}))
    finally:
        # Remove only the unique file created by this fixture from Downloads.
        if downloaded and downloaded.is_file() and downloaded.name.startswith('fixture') and downloaded.suffix == '.txt':
            downloaded.unlink()
        core.cleanup()


if __name__ == '__main__':
    main()
