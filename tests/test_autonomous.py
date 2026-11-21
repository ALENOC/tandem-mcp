"""Offline tests for TANDEM_PROFILE=autonomous: few tools, a delegate call that blocks until the local work
ends, a one-line ACCEPTED receipt, and a FAILED receipt that lists only what still fails."""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ['TANDEM_HOME'] = tempfile.mkdtemp()
os.environ['TANDEM_PROFILE'] = 'autonomous'
os.environ['TANDEM_MAX_REPAIRS'] = '3'
os.environ['TANDEM_JOB_SECONDS'] = '120'

from fake_server import Fake  # noqa: E402
from tandem_mcp import engine, server, store  # noqa: E402

PY = sys.executable
checks = 0


def ok(cond, msg):
    global checks
    assert cond, msg
    checks += 1


tools = {t.name for t in asyncio.run(server.mcp.list_tools())}
ok(tools == {'delegate', 'job_continue', 'job_status', 'job_rollback'}, f'autonomous tools: {tools}')
ok(len(server.mcp.instructions) < 1100 and 'ACCEPTED is final' in server.mcp.instructions, 'short autonomous guide')
ok(server._auto_limits() == (160, 3, 120), f'limits from env: {server._auto_limits()}')


def project():
    root = Path(tempfile.mkdtemp())
    (root / 'calc.py').write_text('def val():\n    return 1\n')
    (root / 'test_calc.py').write_text('from calc import val\nassert val() == 2\n')
    return root


GOAL = 'Fix val() in calc.py so that it returns the integer 2 instead of 1, keeping its signature unchanged'
fake = Fake(tools=True, schema=True)
engine.connect(url=fake.url)

# 1. the local model fixes it after one failed attempt: delegate returns only at the end, ACCEPTED in one line
root = project()
fake.script = [
    ('finish', {'summary': 'nothing yet', 'evidence': [{'constraint': 1, 'path': 'calc.py', 'quote': 'def val():'}]}),
    ('replace_in_file', {'path': 'calc.py', 'old': 'return 1', 'new': 'return 2'}),
    ('finish', {'summary': 'fixed', 'evidence': [{'constraint': 1, 'path': 'calc.py', 'quote': 'return 2'}]}),
]
out = server.auto_delegate(GOAL, str(root), ['calc.py'], [f'{PY} test_calc.py'], constraints=['calc.py val() returns 2'])
ok(out.startswith('job ') and 'ACCEPTED' in out and '1 local repairs' in out and out.count('\n') == 0,
   f'one-line accepted receipt after a local repair: {out}')
job = out.split()[1].rstrip(':')
ok((store.read_job(job) or {}).get('accepted') is True, 'accepted on the orchestrator\'s behalf')
ok('return 2' in (root / 'calc.py').read_text(), 'the work is on disk')

# 2. the local model never fixes it: FAILED lists only the failing check, with the way on
root2 = project()
fake.script = [('finish', {'summary': 'done', 'evidence': [{'constraint': 1, 'path': 'calc.py', 'quote': 'def val():'}]})] * 8
out2 = server.auto_delegate(GOAL, str(root2), ['calc.py'], [f'{PY} test_calc.py'], constraints=['calc.py val() returns 2'])
ok('FAILED (checks_failed) after 3 local repairs' in out2 and 'test_calc.py' in out2 and 'job_continue(' in out2,
   f'failed receipt: {out2}')
ok('ACCEPTED' not in out2 and len(out2) < 2500, 'failed receipt stays short')

# 3. job_continue blocks too and can turn it into ACCEPTED
job2 = out2.split()[1].rstrip(':')
fake.script = [
    ('replace_in_file', {'path': 'calc.py', 'old': 'return 1', 'new': 'return 2'}),
    ('finish', {'summary': 'fixed', 'evidence': [{'constraint': 1, 'path': 'calc.py', 'quote': 'return 2'}]}),
]
out3 = server.auto_job_continue(job2, 'val() must return 2')
ok('ACCEPTED' in out3, f'continued job accepted: {out3}')

# compound constraints are split by the server instead of refusing the contract (a refusal costs a rewrite)
split = server._validate_contract(GOAL, ['calc.py val() returns 2; calc.py keeps def val(). The signature stays val().'],
                                  [f'{PY} test_calc.py'], ['calc.py'])
ok(split == ['calc.py val() returns 2', 'calc.py keeps def val().', 'The signature stays val().'], f'split: {split}')

# 4. the MCP tool is async and sends progress while the local model works (clients abort silent tools)
import time  # noqa: E402

from tests.test_host_runner import SlowFake  # noqa: E402

os.environ['TANDEM_PROGRESS_SECONDS'] = '1'


class Ctx:
    def __init__(self):
        self.events = []

    async def report_progress(self, progress, total=None, message=None):
        self.events.append((progress, total, message))


slow = SlowFake(delay_s=1.2)
engine.connect(url=slow.url)
root4 = project()
slow.script = [
    ('read_file', {'path': 'calc.py'}),
    ('replace_in_file', {'path': 'calc.py', 'old': 'return 1', 'new': 'return 2'}),
    ('finish', {'summary': 'fixed', 'evidence': [{'constraint': 1, 'path': 'calc.py', 'quote': 'return 2'}]}),
]
ctx = Ctx()
t0 = time.time()
out4 = asyncio.run(server.auto_delegate_tool(GOAL, str(root4), ['calc.py'], [f'{PY} test_calc.py'],
                                             constraints=['calc.py val() returns 2'], ctx=ctx))
ok('ACCEPTED' in out4, f'async delegate accepted: {out4}')
ok(len(ctx.events) >= 2 and 'local model working' in str(ctx.events[0][2]),
   f'progress notifications sent while waiting: {ctx.events}')

print(f'test_autonomous: {checks} checks, 0 failures')
