"""Seed synthetic conversation/document data before launching owned UX-6 QA."""
import json
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
profile = Path(sys.argv[1]).resolve()
assert profile.is_relative_to(root / '.codex-local' / 'ux-6')
assert profile == Path(os.environ['SMARTI_DATA_DIR']).resolve()
sys.path.insert(0, str(root))
import keyring
assert type(keyring.get_keyring()).__name__ == 'Ux6Keyring'
from smarti.history import ChatSessionStore
from smarti.common import CHAT_HISTORY_FILE
from ux6_stress_fixtures import seed_messages
assert Path(CHAT_HISTORY_FILE).resolve().is_relative_to(profile)
store = ChatSessionStore()
sessions = {}
for count in (200, 1000):
    title = f'UX6 {count} messages'
    existing = next((s for s in store.data['sessions'] if s['title'] == title), None)
    if existing:
        sessions[str(count)] = existing['id']
        continue
    session = store.create_session()
    session_id = session['id']
    store.rename_session(session_id, title)
    sessions[str(count)] = session_id
    seed_messages(store, session_id, count)
(profile/'stress-sessions.json').write_text(json.dumps(sessions),encoding='utf-8')
(profile/'workspace'/'chooser.txt').write_text('UX6 isolated Open With fixture',encoding='utf-8')
print('Isolated 200/1000 message fixtures ready')
