"""The lean profile (TANDEM_PROFILE=lean): few tools, short schemas, compact receipts, and automatic
acceptance only of jobs whose checks prove the work. Runs against the scripted fake server."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ['TANDEM_HOME'] = tempfile.mkdtemp()
os.environ['TANDEM_PROFILE'] = 'lean'
os.environ['TANDEM_WAIT_SECONDS'] = '60'
for name in ('TANDEM_BASE_URL', 'LM_STUDIO_BASE_URL', 'TANDEM_MODEL', 'TANDEM_CONTEXT', 'TANDEM_STRICT'):
    os.environ.pop(name, None)
from fake_server import Fake  # noqa: E402
from tandem_mcp import engine, server, store  # noqa: E402
import logging  # noqa: E402
logging.disable(logging.INFO)

checks = 0
PY = sys.executable


def ok(cond, what):
    global checks
    assert cond, what
    checks += 1


def project():
    root = Path(tempfile.mkdtemp())
    (root / 'calc.py').write_text('def dbm_to_mw(dbm):\n    return 10 ** (dbm / 20)\n')
    (root / 'test_calc.py').write_text('from calc import dbm_to_mw\nassert abs(dbm_to_mw(10) - 10) < 1e-9\nprint("ok")\n')
    return root


# 1. exposure: fewer tools, small schemas, short guide ----------------------------------------------
tools = asyncio.run(server.mcp.list_tools())
names = {t.name for t in tools}
size = sum(len(json.dumps(t.model_dump(exclude_none=True))) for t in tools)
ok(names == set(server._LEAN_TOOLS), f'lean exposes exactly the lean tools, got {sorted(names)}')
ok({'job_feedback', 'job_evidence', 'ledger_report', 'executor_status', 'ask'}.isdisjoint(names), 'housekeeping tools hidden')
ok(size < 9000, f'lean schemas stay small ({size} bytes)')
ok(len(server.mcp.instructions) < 1000 and 'ACCEPTED is final' in server.mcp.instructions, 'short guide')
delegate_schema = next(t for t in tools if t.name == 'delegate').input_schema['properties']
ok(set(delegate_schema) == {'goal', 'workspace', 'write_globs', 'verify_commands', 'constraints', 'allow_run', 'context'},
   f'lean delegate has 7 parameters, got {sorted(delegate_schema)}')

fake = Fake(tools=True, schema=True)
engine.connect(url=fake.url)

# 2. a proven job is accepted on the orchestrator's behalf, in one short receipt ---------------------
root = project()
fake.script = [('read_file', {'path': 'calc.py'}),
               ('replace_in_file', {'path': 'calc.py', 'old': 'dbm / 20', 'new': 'dbm / 10'}),
               ('finish', {'summary': 'Fixed the exponent.', 'evidence': [
                   {'constraint': 1, 'path': 'calc.py', 'quote': 'dbm / 10'}]})]
out = server.lean_delegate('Fix dbm_to_mw in calc.py so 10 dBm gives 10 mW (divide by 10)', str(root),
                           write_globs=['calc.py'], verify_commands=[f'{PY} test_calc.py'],
                           constraints=['calc.py divides dbm by 10'])
job = out.split()[1].rstrip(':')
data = store.read_job(job)
ok('ACCEPTED' in out and 'Nothing else to call' in out, out)
ok(len(out) < 600, f'compact receipt ({len(out)} chars)')
ok(data.get('accepted') is True and data.get('auto_accepted') is True, 'acceptance recorded in the job')
ok(any(r.get('kind') == 'feedback' and r.get('auto') for r in store.ledger(1)), 'acceptance recorded in the ledger')
ok('ACCEPTED' in server.lean_job_status(job), 'job_status gives the same compact receipt')

# 3. a job whose checks passed before the work is NOT auto-accepted ---------------------------------
weak = project()
(weak / 'calc.py').write_text('def dbm_to_mw(dbm):\n    return 10 ** (dbm / 10)\n')
fake.script = [('replace_in_file', {'path': 'calc.py', 'old': 'return', 'new': 'return  '}),
               ('finish', {'summary': 'Touched calc.py.', 'evidence': [
                   {'constraint': 1, 'path': 'calc.py', 'quote': 'dbm / 10'}]})]
out = server.lean_delegate('Reformat dbm_to_mw in calc.py keeping the division by 10 intact', str(weak),
                           write_globs=['calc.py'], verify_commands=[f'{PY} test_calc.py'],
                           constraints=['calc.py divides dbm by 10'])
ok('ACCEPTED (' not in out, out)
ok(store.read_job(out.split()[1].rstrip(':')).get('accepted') is not True, 'weak job left for the orchestrator')

# 4. a failing job returns the full receipt so the orchestrator can judge ---------------------------
bad = project()
fake.script = [('replace_in_file', {'path': 'calc.py', 'old': 'dbm / 20', 'new': 'dbm / 30'}),
               ('finish', {'summary': 'Changed it.'})] * 4
out = server.lean_delegate('Fix dbm_to_mw in calc.py so 10 dBm gives 10 mW (divide by 10)', str(bad),
                           write_globs=['calc.py'], verify_commands=[f'{PY} test_calc.py'],
                           constraints=['calc.py divides dbm by 10'])
ok('ACCEPTED (' not in out and 'check FAIL' in out, out)

# 5. a strict contract is still enforced ------------------------------------------------------------
ok('contract refused' in server.lean_delegate('Fix calc.py so the test passes now please ok', str(project()),
                                              write_globs=['calc.py'], verify_commands=[]), 'no verify_commands refused')

print(f'{checks} checks, 0 failures')
