"""Strategy review lifecycle with immutable decision events and version-bound approvals."""
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from contextlib import closing


class ReviewStore:
    def __init__(self, path):
        self.path = str(path)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS strategy_drafts (draft_id TEXT PRIMARY KEY, body TEXT NOT NULL, status TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS strategy_events (event_id INTEGER PRIMARY KEY, draft_id TEXT, decision TEXT, actor TEXT, note TEXT, created_at TEXT)')

    def save_draft(self, body, supersedes=None):
        payload = json.dumps(body, sort_keys=True, ensure_ascii=False, allow_nan=False)
        draft_id = hashlib.sha256(payload.encode()).hexdigest()
        with closing(sqlite3.connect(self.path)) as db, db:
            if supersedes:
                if supersedes == draft_id or not db.execute('SELECT 1 FROM strategy_drafts WHERE draft_id=?', (supersedes,)).fetchone():
                    raise ValueError('Edited content must differ and refer to an existing draft')
                db.execute('UPDATE strategy_drafts SET status=? WHERE draft_id=?', ('superseded', supersedes))
            db.execute('INSERT OR IGNORE INTO strategy_drafts VALUES (?,?,?)', (draft_id, payload, 'pending'))
        return draft_id

    def decide(self, draft_id, decision, actor, note):
        if decision not in {'approved', 'rejected', 'changes_requested'} or not actor.strip() or not note.strip():
            raise ValueError('Explicit decision, reviewer and rationale are required')
        with closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute('SELECT status FROM strategy_drafts WHERE draft_id=?', (draft_id,)).fetchone()
            if not row:
                raise ValueError('Unknown draft')
            if row[0] == 'superseded':
                raise ValueError('Superseded content cannot be approved')
            db.execute('UPDATE strategy_drafts SET status=? WHERE draft_id=?', (decision, draft_id))
            db.execute('INSERT INTO strategy_events (draft_id,decision,actor,note,created_at) VALUES (?,?,?,?,?)',
                       (draft_id, decision, actor, note, datetime.now(timezone.utc).isoformat()))

    def approved(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            return [{'draft_id': row[0], 'body': json.loads(row[1])} for row in db.execute(
                'SELECT draft_id,body FROM strategy_drafts WHERE status=?', ('approved',))]
