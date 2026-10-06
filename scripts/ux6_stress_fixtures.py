"""QA-only bulk seed: avoid timing 1000 individual SQLite commits as UI startup."""
import datetime
import os
from pathlib import Path


def seed_messages(store, session_id, count):
    assert Path(store.path).resolve().is_relative_to(Path(os.environ['SMARTI_DATA_DIR']).resolve())
    rows = []
    for index in range(count):
        content = f'Message {index} — שלום, Hebrew / English mixed text. ' + 'תוכן לקריאה ' * 12
        if index % 20 == 1:
            content += "\n\n```python\n" + "print('long output')\n" * 12 + '```\n\n| שם | Value |\n|---|---|\n| בדיקה | 42 |'
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        rows.append((session_id, index, 'user' if index % 2 == 0 else 'assistant', content, now, '{}'))
    with store._lock, store._connect() as db:
        db.executemany('INSERT INTO messages(session_id,ordinal,role,content,created_at,metadata_json) VALUES(?,?,?,?,?,?)', rows)
        db.execute('UPDATE sessions SET updated_at=? WHERE id=?', (rows[-1][4], session_id))
