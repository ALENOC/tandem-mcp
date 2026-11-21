"""Offline tests: the router stops delegating a task family whose local jobs usually fail."""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tandem_mcp import router, store  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix='tandem_router_p_'))
store.DATA = tmp / 'data'
store.JOBS = store.DATA / 'jobs'
store.JOBS.mkdir(parents=True)
checks = 0


def ok(cond, msg):
    global checks
    assert cond, msg
    checks += 1


def job(name, globs, state, accepted=None):
    d = store.JOBS / name
    d.mkdir()
    data = {'id': name, 'write_globs': globs, 'state': state}
    if accepted is not None:
        data['accepted'] = accepted
    (d / 'job.json').write_text(json.dumps(data))


ws = tmp / 'ws'
ws.mkdir()
REQ = 'Crea da zero index.html con una animazione canvas interattiva, privilegia il risparmio di token cloud'

ok(router.task_family(['index.html', 'app.js']) == 'web', 'web family')
ok(router.task_family(['calc.py']) == 'python', 'python family')

# no history: delegation allowed (exploration)
d = router.classify_request(REQ, ws, log_decision=False)
ok(d['route'] == 'delegate_local', f'no history delegates: {d}')

# history mostly failing for web: direct
job('a', ['index.html'], 'checks_failed')
job('b', ['index.html'], 'out_of_time')
job('c', ['index.html'], 'verified', accepted=False)
job('d', ['index.html'], 'verified')
job('e', ['calc.py'], 'verified')
est = router.local_success_estimate('web')
ok(est['n'] == 4 and est['verified'] == 1, f'estimate counts: {est}')
d = router.classify_request(REQ, ws, log_decision=False)
ok(d['route'] == 'direct_or_targeted' and 'verified 1/4' in d['reason'], f'poor history goes direct: {d}')

# local only still delegates
d = router.classify_request(REQ + ', solo locale', ws, log_decision=False)
ok(d['route'] == 'delegate_local', 'local only is honoured')

# history mostly passing: delegate again
for i in range(6):
    job(f'ok{i}', ['index.html'], 'verified')
d = router.classify_request(REQ, ws, log_decision=False)
ok(d['route'] == 'delegate_local' and d['signals']['local_success']['p'] >= 0.6, f'good history delegates: {d}')

print(f'test_router_success: {checks} checks, 0 failures')
