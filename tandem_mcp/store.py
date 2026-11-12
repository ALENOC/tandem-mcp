"""Persistent state: token ledger, lessons learnt from the orchestrator, job folders, caches."""
import hashlib
import json
import os
import threading
import time
from pathlib import Path

DATA = Path(os.environ.get('TANDEM_HOME', Path.home() / '.local/share/tandem-mcp'))
JOBS = DATA / 'jobs'
CACHE = DATA / 'cache'
LEDGER = DATA / 'ledger.jsonl'
LESSONS = DATA / 'lessons.jsonl'
MODELS = DATA / 'models.json'
CHARS_PER_TOKEN = 3.6          # rough size of a token of the orchestrator, for the savings estimate
CACHE_KEEP = 400               # digest answers kept on disk
_lock = threading.Lock()


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


def write_json(path, data):
    """Write through a temporary file, so that a crash never leaves half a file."""
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)


def read_json(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def write_job(job, data):
    with _lock:
        write_json(JOBS / job / 'job.json', data)


def read_job(job):
    if not job or '/' in job or job.startswith('.'):
        return None
    return read_json(JOBS / job / 'job.json')


def log(tool, **fields):
    """One ledger line per executor call or tool result."""
    init()
    with _lock, LEDGER.open('a') as f:
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


# lessons ---------------------------------------------------------------------------------------
def add_lesson(scope, text, source='orchestrator'):
    init()
    text = ' '.join(text.split())
    if any(r['text'].lower() == text.lower() for r in lessons(scope, 1000)):
        return False                                     # the same rule is not stored twice
    with _lock, LESSONS.open('a') as f:
        f.write(json.dumps({'ts': time.time(), 'scope': scope, 'text': text, 'source': source}) + '\n')
    return True


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
        if row.get('scope') in ('*', scope):
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


# what is known about each model ----------------------------------------------------------------
def model_caps(key):
    return (read_json(MODELS, {}) or {}).get(key)


def save_model_caps(key, caps):
    init()
    with _lock:
        data = read_json(MODELS, {}) or {}
        data[key] = caps
        write_json(MODELS, data)


# answers already given -------------------------------------------------------------------------
def cache_key(*parts):
    h = hashlib.sha256()
    for part in parts:
        h.update(str(part).encode('utf-8', 'replace'))
        h.update(b'\x00')
    return h.hexdigest()[:32]


def cache_get(key):
    return read_json(CACHE / f'{key}.json')


def cache_put(key, data):
    CACHE.mkdir(parents=True, exist_ok=True)
    write_json(CACHE / f'{key}.json', data)
    files = sorted(CACHE.glob('*.json'), key=lambda p: p.stat().st_mtime)
    for old in files[:-CACHE_KEEP]:
        old.unlink(missing_ok=True)
