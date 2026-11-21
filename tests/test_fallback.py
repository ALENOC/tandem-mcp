"""Offline tests: host_runner falls back to the direct path when the local job does not verify,
and makes no fallback call when it does."""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ['TANDEM_HOME'] = tempfile.mkdtemp()
os.environ['TANDEM_PROFILE'] = 'lean'
os.environ['TANDEM_WAIT_SECONDS'] = '0'

from fake_server import Fake  # noqa: E402
from tandem_mcp import engine, host_runner, server  # noqa: E402

PY = sys.executable
checks = 0


def ok(cond, msg):
    global checks
    assert cond, msg
    checks += 1


class SlowFake(Fake):
    def __init__(self, delay_s):
        self.delay_s = delay_s
        super().__init__(tools=True, schema=True)

    def answer(self, body):
        time.sleep(self.delay_s)
        return super().answer(body)


def project():
    root = Path(tempfile.mkdtemp())
    (root / 'calc.py').write_text('def val():\n    return 1\n')
    (root / 'test_calc.py').write_text('from calc import val\nassert val() == 2\n')
    return root


def planner(root, fake, fix):
    def _plan(_url):
        fake.script = ([('replace_in_file', {'path': 'calc.py', 'old': 'return 1', 'new': 'return 2'})] if fix else []) + [
            ('finish', {'summary': 'done'})] * 4
        out = server.lean_delegate('Fix val() in calc.py so it returns 2 instead of 1', str(root),
                                   write_globs=['calc.py'], verify_commands=[f'{PY} test_calc.py'], constraints=[])
        return {'status': 'SUCCESS', 'usage': {'total_tokens': 100}, 'response': out}
    return _plan


calls = []


def fallback(root):
    def _fb(job_id, receipt):
        calls.append((job_id, receipt))
        (root / 'calc.py').write_text('def val():\n    return 2\n')       # the cloud does the work itself
        return {'status': 'SUCCESS', 'usage': {'total_tokens': 500}}
    return _fb


# 1. local job fails -> exactly one fallback call, recorded as its own phase
fake = SlowFake(0.01)
engine.connect(url=fake.url)
root = project()
res = host_runner.run_host_managed(planner(root, fake, fix=False), poll_interval_s=0.03, timeout_s=30.0,
                                   cloud_fallback_fn=fallback(root))
ok(res.state != 'verified' and res.fallback_used, f'failed job falls back: {res.state} {res.fallback_used}')
ok(len(calls) == 1 and calls[0][0] == res.job_id and res.receipt in calls[0][1], 'fallback receives job id and receipt')
ok([c['phase'] for c in res.cloud_calls] == ['plan', 'fallback'], f'phases: {res.cloud_calls}')
ok('return 2' in (root / 'calc.py').read_text(), 'fallback result is delivered')

# 2. local job verifies -> no fallback call
calls.clear()
root2 = project()
res2 = host_runner.run_host_managed(planner(root2, fake, fix=True), poll_interval_s=0.03, timeout_s=30.0,
                                    cloud_fallback_fn=fallback(root2))
ok(res2.state == 'verified' and not res2.fallback_used and not calls, f'verified job: no fallback ({res2.state})')
ok([c['phase'] for c in res2.cloud_calls] == ['plan'], 'only the plan call')

# 3. review sends the job on: the host waits for that run before deciding on the fallback
calls.clear()
root3 = project()


def reviewer(job_id, receipt):
    fake.script = [('replace_in_file', {'path': 'calc.py', 'old': 'return 1', 'new': 'return 2'}),
                   ('finish', {'summary': 'fixed after hint'})]
    server.lean_job_continue(job_id, 'val() must return 2')
    return {'status': 'SUCCESS', 'usage': {'total_tokens': 200}}


res3 = host_runner.run_host_managed(planner(root3, fake, fix=False), poll_interval_s=0.03, timeout_s=30.0,
                                    cloud_reviewer_fn=reviewer, cloud_fallback_fn=fallback(root3))
ok(res3.state == 'verified' and not res3.fallback_used and not calls,
   f'review fixed it, no fallback: {res3.state} {res3.fallback_used}')

print(f'test_fallback: {checks} checks, 0 failures')
