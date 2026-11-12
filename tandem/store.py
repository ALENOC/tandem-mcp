"""Persistent state: token ledger, lessons learnt from the orchestrator, job folders."""
import hashlib
import json
import os
import time
from pathlib import Path

DATA = Path(os.environ.get('TANDEM_HOME', Path.home() / '.local/share/tandem-mcp'))
JOBS = DATA / 'jobs'
LEDGER = DATA / 'ledger.jsonl'
LESSONS = DATA / 'lessons.jsonl'
CHARS_PER_TOKEN = 3.6          # rough size of a token of the orchestrator, for the savings estimate


def init():
    JOBS.mkdir(parents=True, exist_ok=True)


def scope_of(path):
    """A project scope: the git root above `path`, or the folder itself."""
    p = Path(path).resolve()
    p = p if p.is_dir() else p.parent
    for q in [p, *p.parents]:
        if (q / '.git').exists():
            return str(q)
    return str(p)


def new_job(kind):
    init()
    job = time.strftime('%Y%m%d-%H%M%S-') + hashlib.sha1(os.urandom(8)).hexdigest()[:6]
    folder = JOBS / job
    folder.mkdir()
    write_job(job, {'id': job, 'kind': kind, 'state': 'running', 'started': time.time()})
    return job, folder


def write_job(job, data):
    path = JOBS / job / 'job.json'
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)


def read_job(job):
    path = JOBS / job / 'job.json'
    return json.loads(path.read_text()) if path.exists() else None


def log(tool, **fields):
    """One ledger line per executor call or tool result."""
    init()
    with LEDGER.open('a') as f:
        f.write(json.dumps({'ts': time.time(), 'tool': tool, **fields}) + '\n')


def ledger(days=30.0):
    if not LEDGER.exists():
        return []
    since = time.time() - days * 86400
    rows = []
    for line in LEDGER.read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get('ts', 0) >= since:
            rows.append(row)
    return rows


def add_lesson(scope, text, source='orchestrator'):
    init()
    with LESSONS.open('a') as f:
        f.write(json.dumps({'ts': time.time(), 'scope': scope, 'text': text.strip(), 'source': source}) + '\n')


def lessons(scope, limit=12):
    """Lessons of this scope and the global ones, newest last."""
    if not LESSONS.exists():
        return []
    rows = []
    for line in LESSONS.read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row['scope'] in ('*', scope):
            rows.append(row)
    return rows[-limit:]


def drop_lesson(scope, fragment):
    if not LESSONS.exists():
        return 0
    kept, dropped = [], 0
    for line in LESSONS.read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row['scope'] == scope and fragment.lower() in row['text'].lower():
            dropped += 1
        else:
            kept.append(json.dumps(row))
    LESSONS.write_text('\n'.join(kept) + ('\n' if kept else ''))
    return dropped
