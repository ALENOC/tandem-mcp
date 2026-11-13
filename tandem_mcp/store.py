"""Persistent state: token ledger, lessons learnt from the orchestrator, job folders, caches."""
import hashlib
import json
import os
import shutil
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
CACHE_KEEP = int(os.environ.get('TANDEM_CACHE_KEEP', 400))               # digest answers kept on disk
CACHE_TTL_DAYS = float(os.environ.get('TANDEM_CACHE_TTL_DAYS', 14))
JOBS_KEEP = int(os.environ.get('TANDEM_JOBS_KEEP', 200))
JOBS_TTL_DAYS = float(os.environ.get('TANDEM_JOBS_TTL_DAYS', 30))
JOBS_PENDING_TTL_DAYS = float(os.environ.get('TANDEM_JOBS_PENDING_TTL_DAYS', 120))   # jobs with changes and no verdict
LEDGER_KEEP_DAYS = float(os.environ.get('TANDEM_LEDGER_KEEP_DAYS', 180))
_lock = threading.Lock()
_last_cleanup = 0.0


def init():
    global _last_cleanup
    JOBS.mkdir(parents=True, exist_ok=True)
    now = time.time()
    if now - _last_cleanup > 3600:
        _last_cleanup = now
        try:
            os.chmod(DATA, 0o700)          # transcripts and file copies live here: not for other users
        except OSError:
            pass
        cleanup()


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
    p = CACHE / f'{key}.json'
    if not p.exists():
        return None
    if CACHE_TTL_DAYS > 0:
        try:
            if time.time() - p.stat().st_mtime > CACHE_TTL_DAYS * 86400:
                p.unlink(missing_ok=True)
                return None
        except OSError:
            return None
    return read_json(p)


def cache_put(key, data):
    CACHE.mkdir(parents=True, exist_ok=True)
    write_json(CACHE / f'{key}.json', data)
    _trim_cache(CACHE_TTL_DAYS, CACHE_KEEP)


def _trim_cache(ttl_days, keep):
    if not CACHE.exists():
        return 0
    removed = 0
    now = time.time()
    kept = []
    for p in CACHE.glob('*.json'):
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if ttl_days > 0 and now - mtime > ttl_days * 86400:
            p.unlink(missing_ok=True)
            removed += 1
        else:
            kept.append((mtime, p))
    if keep >= 0 and len(kept) > keep:
        kept.sort(key=lambda item: item[0])
        for _, old in kept[:-keep] if keep > 0 else kept:
            old.unlink(missing_ok=True)
            removed += 1
    return removed


def _trim_jobs(ttl_days, keep, preserve_pending=True):
    if not JOBS.exists():
        return 0
    removed = 0
    now = time.time()
    kept = []
    for folder in JOBS.iterdir():
        if not folder.is_dir():
            continue
        try:
            mtime = folder.stat().st_mtime
        except OSError:
            continue
        data = read_json(folder / 'job.json', {}) or {}
        # Never delete a job that is actively running recently.
        if data.get('state') == 'running' and now - mtime < 86400:
            continue
        # Preserve jobs that still have un-rolled-back, un-accepted changes.
        pending = data.get('state') != 'rolled_back' and data.get('accepted') is None and (data.get('changes') or data.get('touched'))
        if preserve_pending and pending and (JOBS_PENDING_TTL_DAYS <= 0 or now - mtime < JOBS_PENDING_TTL_DAYS * 86400):
            continue
        if ttl_days > 0 and now - mtime > ttl_days * 86400:
            shutil.rmtree(folder, ignore_errors=True)
            removed += 1
        else:
            kept.append((mtime, folder))
    if keep >= 0 and len(kept) > keep:
        kept.sort(key=lambda item: item[0])
        for _, old in kept[:-keep] if keep > 0 else kept:
            shutil.rmtree(old, ignore_errors=True)
            removed += 1
    return removed


def _trim_ledger(keep_days):
    """Drop the ledger lines older than keep_days (0: keep all)."""
    if keep_days <= 0 or not LEDGER.exists():
        return 0
    since = time.time() - keep_days * 86400
    with _lock:
        lines = LEDGER.read_text().splitlines()
        kept = []
        for line in lines:
            try:
                if json.loads(line).get('ts', 0) >= since:
                    kept.append(line)
            except (ValueError, AttributeError):
                continue
        if len(kept) == len(lines):
            return 0
        tmp = LEDGER.with_name(LEDGER.name + '.tmp')
        tmp.write_text('\n'.join(kept) + ('\n' if kept else ''))
        tmp.replace(LEDGER)
    return len(lines) - len(kept)


def cleanup(cache_ttl_days=None, cache_keep=None, jobs_ttl_days=None, jobs_keep=None, preserve_pending=True):
    """Apply retention policies to cached digest answers and persisted job folders."""
    c_ttl = CACHE_TTL_DAYS if cache_ttl_days is None else cache_ttl_days
    c_keep = CACHE_KEEP if cache_keep is None else cache_keep
    j_ttl = JOBS_TTL_DAYS if jobs_ttl_days is None else jobs_ttl_days
    j_keep = JOBS_KEEP if jobs_keep is None else jobs_keep
    return {'cache_removed': _trim_cache(c_ttl, c_keep), 'jobs_removed': _trim_jobs(j_ttl, j_keep, preserve_pending=preserve_pending),
            'ledger_removed': _trim_ledger(LEDGER_KEEP_DAYS)}
