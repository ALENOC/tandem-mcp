"""Offline tests for tandem_mcp.host_runner:
1. Cloud call count is identical for short vs long local waits (> multiple polling intervals), with 0 cloud calls during wait.
2. Timeout cleanly stops the running job.
3. Cancellation (stop_event) cleanly stops the running job.
4. Reconnecting via attach_job_id monitors the existing job without starting a duplicate.
"""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ['TANDEM_HOME'] = tempfile.mkdtemp()
os.environ['TANDEM_PROFILE'] = 'lean'
os.environ['TANDEM_WAIT_SECONDS'] = '0'

from fake_server import Fake  # noqa: E402
from tandem_mcp import agent, engine, host_runner, sandbox, server, store  # noqa: E402

PY = sys.executable
checks = 0


def ok(cond, msg):
    global checks
    assert cond, msg
    checks += 1


def make_project():
    root = Path(tempfile.mkdtemp())
    (root / 'calc.py').write_text('def val():\n    return 1\n')
    (root / 'test_calc.py').write_text('from calc import val\nassert val() == 2\n')
    return root


class SlowFake(Fake):
    def __init__(self, delay_s: float):
        self.delay_s = delay_s
        super().__init__(tools=True, schema=True)

    def answer(self, body):
        time.sleep(self.delay_s)
        return super().answer(body)


def make_planner(root: Path, fake_srv: Fake):
    def _plan(_mcp_url: str):
        fake_srv.script = [
            ('replace_in_file', {'path': 'calc.py', 'old': 'return 1', 'new': 'return 2'}),
            ('finish', {'summary': 'fixed', 'evidence': [{'constraint': 1, 'path': 'calc.py', 'quote': 'return 2'}]}),
        ]
        out = server.lean_delegate(
            'Fix val() in calc.py so it returns 2 instead of 1',
            str(root),
            write_globs=['calc.py'],
            verify_commands=[f'{PY} test_calc.py'],
            constraints=[],
        )
        return {'status': 'SUCCESS', 'usage': {'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120}, 'response': out}
    return _plan


# 1. Short wait vs long wait (> multiple polling intervals) -> identical cloud call count (1), 0 wait cloud calls
short_fake = SlowFake(delay_s=0.01)
engine.connect(url=short_fake.url)
res_short = host_runner.run_host_managed(make_planner(make_project(), short_fake), poll_interval_s=0.04, timeout_s=10.0)
ok(res_short.state == 'verified' and res_short.accepted, f'short run verified/accepted: {res_short}')
ok(res_short.total_cloud_calls == 1 and res_short.cloud_calls_during_wait == 0, f'short cloud calls: {res_short.cloud_calls}')

long_fake = SlowFake(delay_s=0.25)
engine.connect(url=long_fake.url)
res_long = host_runner.run_host_managed(make_planner(make_project(), long_fake), poll_interval_s=0.03, timeout_s=10.0)
ok(res_long.state == 'verified' and res_long.accepted, f'long run verified/accepted: {res_long}')
ok(res_long.wait_polls >= 3, f'expected multiple polling intervals, got {res_long.wait_polls}')
ok(res_long.total_cloud_calls == res_short.total_cloud_calls == 1,
   f'cloud calls must be identical: short={res_short.total_cloud_calls}, long={res_long.total_cloud_calls}')
ok(res_long.cloud_calls_during_wait == 0, f'zero cloud calls during wait, got {res_long.cloud_calls_during_wait}')

# 2. Timeout stops the running job cleanly
timeout_fake = SlowFake(delay_s=0.8)
engine.connect(url=timeout_fake.url)
res_to = host_runner.run_host_managed(make_planner(make_project(), timeout_fake), poll_interval_s=0.03, timeout_s=0.15)
ok(res_to.timed_out is True and res_to.state == 'timeout', f'expected timeout, got {res_to}')
ok(not agent.RUNNING[res_to.job_id][0].is_alive(), 'timed out job thread must be stopped')

# 3. Cancellation (stop_event) stops the running job cleanly
cancel_fake = SlowFake(delay_s=0.8)
engine.connect(url=cancel_fake.url)
stop_ev = threading.Event()
threading.Timer(0.12, stop_ev.set).start()
res_cancel = host_runner.run_host_managed(make_planner(make_project(), cancel_fake), poll_interval_s=0.03, timeout_s=10.0, stop_event=stop_ev)
ok(res_cancel.cancelled is True and res_cancel.state == 'cancelled', f'expected cancelled, got {res_cancel}')
ok(not agent.RUNNING[res_cancel.job_id][0].is_alive(), 'cancelled job thread must be stopped')

# 4. Reconnecting (attach_job_id) does NOT start a duplicate job
reconn_fake = SlowFake(delay_s=0.10)
engine.connect(url=reconn_fake.url)
r_proj = make_project()
reconn_fake.script = [
    ('replace_in_file', {'path': 'calc.py', 'old': 'return 1', 'new': 'return 2'}),
    ('finish', {'summary': 'fixed', 'evidence': [{'constraint': 1, 'path': 'calc.py', 'quote': 'return 2'}]}),
]
ws = sandbox.Workspace(str(r_proj), ['calc.py'], [], [])
j_existing = agent.start('Fix val() in calc.py so it returns 2', ws, [f'{PY} test_calc.py'], 10, 1, '', '', True, 0,
                         constraints=[], require_proof=True)
before_jobs = {p.name for p in store.JOBS.iterdir() if p.is_dir()}
res_reconn = host_runner.run_host_managed(attach_job_id=j_existing, poll_interval_s=0.03, timeout_s=10.0)
after_jobs = {p.name for p in store.JOBS.iterdir() if p.is_dir()}
ok(res_reconn.job_id == j_existing and res_reconn.state == 'verified' and res_reconn.accepted, f'reconnect verified: {res_reconn}')
ok(res_reconn.total_cloud_calls == 0, f'reconnect must make 0 cloud calls, got {res_reconn.total_cloud_calls}')
ok(after_jobs == before_jobs, f'reconnect must not create duplicate jobs: {after_jobs - before_jobs}')

# 5. External attach CLI (--attach --data-dir) + _host_managed_notice + disk stop on timeout
old_hm = os.environ.get('TANDEM_HOST_MANAGED')
try:
    os.environ['TANDEM_HOST_MANAGED'] = '1'
    ok('HOST-MANAGED MODE IS DEFAULT' in server._instructions(), 'instructions must advertise host-managed mode')
    j_disk = 'disk-job-1'
    (store.JOBS / j_disk).mkdir(parents=True, exist_ok=True)
    store.write_job(j_disk, {'job': j_disk, 'state': 'running', 'tokens': 123, 'checks': [{'command': 'pytest', 'exit': 0}]})
    notice = server._host_managed_notice(j_disk, 'running')
    ok('HOST_WATCHER_CMD:' in notice and f'--attach {j_disk}' in notice, f'missing watcher cmd in notice: {notice}')

    def _finish_disk_job():
        time.sleep(0.12)
        store.write_job(j_disk, {'job': j_disk, 'state': 'verified', 'tokens': 456, 'checks': [{'command': 'pytest', 'exit': 0}]})

    threading.Thread(target=_finish_disk_job, daemon=True).start()
    att_res = host_runner.attach_and_wait(j_disk, data_dir=store.DATA, poll_interval_s=0.03, timeout_s=5.0)
    ok(att_res['state'] == 'verified' and att_res['wait_polls'] >= 2, f'attach_and_wait failed: {att_res}')
    ok('CHECKS_SUMMARY:' in att_res['summary'] and 'exit=0 cmd=pytest' in att_res['summary'], f'missing checks summary: {att_res}')

    j_to = 'disk-job-timeout'
    (store.JOBS / j_to).mkdir(parents=True, exist_ok=True)
    store.write_job(j_to, {'job': j_to, 'state': 'running', 'tokens': 77, 'checks': []})
    rc_to = host_runner.main(['--attach', j_to, '--data-dir', str(store.DATA), '--poll-interval', '0.03', '--timeout', '0.1'])
    ok(rc_to == 1 and (store.JOBS / j_to / 'stop.requested').exists(), 'timeout must exit 1 and create stop.requested')
finally:
    if old_hm is None:
        os.environ.pop('TANDEM_HOST_MANAGED', None)
    else:
        os.environ['TANDEM_HOST_MANAGED'] = old_hm

print(f'{checks} checks, 0 failures')
