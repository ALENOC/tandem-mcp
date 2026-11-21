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

# 2. a proven job (fully verifiable contract, no unverified constraints) is auto-accepted --------------
root = project()
fake.script = [('read_file', {'path': 'calc.py'}),
               ('replace_in_file', {'path': 'calc.py', 'old': 'dbm / 20', 'new': 'dbm / 10'}),
               ('finish', {'summary': 'Fixed the exponent.'})]
out = server.lean_delegate('Fix dbm_to_mw in calc.py so 10 dBm gives 10 mW (divide by 10)', str(root),
                           write_globs=['calc.py'], verify_commands=[f'{PY} test_calc.py'])
job = out.split()[1].rstrip(':')
data = store.read_job(job)
ok('ACCEPTED' in out and 'Nothing else to call' in out, out)
ok(len(out) < 600, f'compact receipt ({len(out)} chars)')
ok(data.get('accepted') is True and data.get('auto_accepted') is True, 'acceptance recorded in the job')
ok(any(r.get('kind') == 'feedback' and r.get('auto') and r.get('job') == job for r in store.ledger(1)),
   'acceptance recorded in the ledger')
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

# 6. an explicitly rejected job stays rejected across repeated lean_job_status calls ------------------
rej_root = project()
fake.script = [('read_file', {'path': 'calc.py'}),
               ('replace_in_file', {'path': 'calc.py', 'old': 'dbm / 20', 'new': 'dbm / 10'}),
               ('finish', {'summary': 'Fixed the exponent.'})]
rej_out = server.lean_delegate('Fix dbm_to_mw in calc.py so 10 dBm gives 10 mW (divide by 10)', str(rej_root),
                               write_globs=['calc.py'], verify_commands=[f'{PY} test_calc.py'])
rej_job = rej_out.split()[1].rstrip(':')
ok(server.job_feedback(rej_job, accepted=False) == 'recorded', 'explicit rejection recorded')
before_polls = len([r for r in store.ledger(1) if r.get('kind') == 'feedback' and r.get('job') == rej_job])
for poll_i in range(3):
    polled = server.lean_job_status(rej_job)
    ok(f'job {rej_job}: ACCEPTED' not in polled and 'NOT ACCEPTED (explicitly rejected).' in polled,
       f'poll {poll_i} preserves rejection: {polled}')
    rej_data = store.read_job(rej_job)
    ok(rej_data.get('accepted') is False, f'poll {poll_i} keeps accepted=False')
    ok(not rej_data.get('auto_accepted'), f'poll {poll_i} does not set auto_accepted')
rej_feedback = [r for r in store.ledger(1) if r.get('kind') == 'feedback' and r.get('job') == rej_job]
ok(len(rej_feedback) == before_polls, 'polling a rejected job adds no ledger feedback entries')
ok(rej_feedback[-1].get('accepted') is False, 'latest ledger feedback for rejected job is accepted=False')

# 7. irrelevant citation present in file does NOT auto-accept -----------------------------------------
irr_root = project()
fake.script = [('read_file', {'path': 'calc.py'}),
               ('replace_in_file', {'path': 'calc.py', 'old': 'dbm / 20', 'new': 'dbm / 10'}),
               ('finish', {'summary': 'Fixed it.', 'evidence': [
                   {'constraint': 1, 'path': 'calc.py', 'quote': 'def dbm_to_mw(dbm):'}]})]
irr_out = server.lean_delegate('Fix dbm_to_mw in calc.py so 10 dBm gives 10 mW (divide by 10)', str(irr_root),
                               write_globs=['calc.py'], verify_commands=[f'{PY} test_calc.py'],
                               constraints=['calc.py uses exponential smoothing alpha=0.3'])
irr_job = irr_out.split()[1].rstrip(':')
ok(f'job {irr_job}: ACCEPTED' not in irr_out and 'NOT ACCEPTED automatically' in irr_out,
   f'irrelevant quote must not auto-accept: {irr_out}')
ok(store.read_job(irr_job).get('accepted') is not True, 'constrained job left for orchestrator judgment')

# 8. visual file change is NOT auto-accepted ----------------------------------------------------------
vis_root = Path(tempfile.mkdtemp())
(vis_root / 'page.html').write_text('<div>old</div>\n')
(vis_root / 'check_html.py').write_text(
    'from pathlib import Path\nassert "new" in Path("page.html").read_text()\nprint("ok")\n')
fake.script = [('replace_in_file', {'path': 'page.html', 'old': '<div>old</div>', 'new': '<div>new</div>'}),
               ('finish', {'summary': 'Updated page.html.'})]
vis_out = server.lean_delegate('Update page.html div text from old to new and keep layout clean', str(vis_root),
                               write_globs=['page.html'], verify_commands=[f'{PY} check_html.py'],
                               constraints=[])
# Note: strict contract requires constraints for _VISUAL write_globs, so test _proven directly too
vis_job_data = {'state': 'verified', 'checks': [{'command': 'check', 'exit': 0}], 'weak': False,
                'unproven': [], 'syntax': {'bad': []}, 'unbacked_files': [], 'backup_status': 'full',
                'changes': [['page.html', 'edit', 1, 1]]}
ok(bool(server._proven(vis_job_data)), '_proven rejects auto-accept for visual changes')

# 9. ledger_report separates auto-accepted from explicit user feedback --------------------------------
report = server.ledger_report()
ok('accepted by you 0 of 1' in report, f'ledger_report counts only explicit feedback in accepted by you: {report}')
ok('auto-accepted' in report, f'ledger_report reports auto-accepted separately: {report}')

# 10. worker context reductions & MCP boundary telemetry ---------------------------------------------
import hashlib as _hl
from tandem_mcp import agent as _agent, sandbox as _sandbox
iface_root = Path(tempfile.mkdtemp())
(iface_root / 'api.js').write_text('window.API = { ping: function() { return 1; } };\n')
(iface_root / 'test_api.py').write_text(
    'from pathlib import Path\nassert "API.ping()" in Path("impl.js").read_text()\n')
ws_iface = _sandbox.Workspace(str(iface_root), ['impl.js'], [], ['api.js'])
job_tmp, folder_tmp = store.new_job('delegate')
runner = _agent.Task(job_tmp, folder_tmp, 'Write impl.js calling window.API.ping()', ws_iface, [f'{PY} test_api.py'],
                     10, 1, '', '', True, 0, constraints=['impl.js calls window.API.ping()'], require_proof=True)
msgs = runner.opening()
ok('Relevant interfaces & check targets' in msgs[1]['content'] and 'window.API' in msgs[1]['content'],
   'opening() injects compact interface summary of immutable files')
wf_out = runner.call('write_file', {'path': 'impl.js', 'content': 'const x = window.API.ping();\n'})
ok('1| const x = window.API.ping();' in wf_out, f'write_file returns numbered lines when constraints exist: {wf_out}')
rf_out = runner.call('read_file', {'path': 'impl.js'})
ok('numbered lines already returned by write_file above' in rf_out, f'read_file dedups just-written file: {rf_out}')

contract_file = iface_root / 'c.json'
contract_spec = {
    'goal': 'Create impl.js calling window.API.ping() and export result cleanly',
    'write_globs': ['impl.js'],
    'read_globs': ['api.js', 'impl.js'],
    'verify_commands': [f'{PY} test_api.py'],
    'constraints': ['impl.js calls window.API.ping()'],
}
raw_c = json.dumps(contract_spec).encode('utf-8')
contract_file.write_bytes(raw_c)
fake.script = [('write_file', {'path': 'impl.js', 'content': 'const x = window.API.ping();\n'}),
               ('finish', {'summary': 'done', 'evidence': [{'constraint': 1, 'path': 'impl.js', 'quote': 'window.API.ping()'}]})]
c_out = server.lean_delegate_contract(str(iface_root), 'c.json', _hl.sha256(raw_c).hexdigest())
ok('job ' in c_out and 'ERROR' not in c_out, f'lean_delegate_contract accepts read_globs: {c_out}')
boundary_rows = [r for r in store.ledger(1) if r.get('kind') == 'mcp_boundary' and r.get('tool') == 'delegate_contract']
ok(bool(boundary_rows) and boundary_rows[-1].get('mcp_req_bytes', 0) > 0 and boundary_rows[-1].get('mcp_resp_bytes', 0) > 0,
   'mcp_boundary telemetry records req/resp bytes')

print(f'{checks} checks, 0 failures')
