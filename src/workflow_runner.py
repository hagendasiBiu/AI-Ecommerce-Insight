"""Persist real workflow responses before interpretation; never silently replay uncertain POSTs."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from src.dify_client import DifyClient


def load_env(root):
    path = Path(root) / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"').strip("'"))


def run_recorded(root, inputs, key_name, workflow_version, purpose, timeout=180):
    root = Path(root)
    load_env(root)
    key = os.environ.get(key_name, '')
    base = os.environ.get('DIFY_API_BASE_URL', '')
    client = DifyClient(base, key, timeout=timeout)
    digest = hashlib.sha256(json.dumps([base, key_name, workflow_version, inputs], sort_keys=True,
                                      ensure_ascii=False).encode()).hexdigest()
    directory = root / 'data/processed/phase4_runs'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{purpose}_{digest[:20]}.json'
    ledger = root / 'data/processed/workflow_requests.sqlite'
    with closing(sqlite3.connect(ledger)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS requests (digest TEXT PRIMARY KEY, state TEXT, path TEXT)')
        prior = db.execute('SELECT state,path FROM requests WHERE digest=?', (digest,)).fetchone()
        if prior:
            if prior[0] == 'received':
                return json.loads(Path(prior[1]).read_text(encoding='utf-8')), True
            if prior[0] != 'local_config_error':
                raise RuntimeError('Prior run needs Dify-log reconciliation; no automatic replay')
            db.execute('UPDATE requests SET state=? WHERE digest=?', ('inflight', digest))
        else:
            db.execute('INSERT INTO requests VALUES (?,?,?)', (digest, 'inflight', str(path)))
    try:
        response = client.run_inputs(inputs)
        response.update(purpose=purpose, request_digest=digest, declared_workflow_version=workflow_version)
        path.write_text(json.dumps(response, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        with closing(sqlite3.connect(ledger)) as db, db:
            db.execute('UPDATE requests SET state=? WHERE digest=?', ('received', digest))
        return response, False
    except Exception as exc:
        path.write_text(json.dumps({'state': 'needs_reconciliation', 'error_type': type(exc).__name__,
                                   'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
                                   'note': 'Do not resubmit before checking actual Dify logs.'}), encoding='utf-8')
        with closing(sqlite3.connect(ledger)) as db, db:
            db.execute('UPDATE requests SET state=? WHERE digest=?', ('needs_reconciliation', digest))
        raise RuntimeError(f'Real workflow request needs reconciliation ({type(exc).__name__})') from None
