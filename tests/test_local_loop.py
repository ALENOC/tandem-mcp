"""The local loop against a scripted server: what it sends to the model from one step to the next.

- The conversation only grows at its end, so the model server can reuse the prompt it has cached: the task
  message is never rewritten and the state of the work rides at the end of each request.
- A write stays visible until the file changes again; then, or when the context fills up, it is compacted for good.
- Past its budget the conversation is cut once, well below the budget, not a little at every step.
- A reply cut off by the token budget is asked again with a larger one instead of being taken for prose.
- Evidence that matches the files is kept from one finish to the next, and checked again each time.
- After a call repeated three times the next replies are sampled less greedily.
- A failing line is kept in a long check output; three finishes in a row with the same failure end the job, and
  the receipt then tells the orchestrator to fix it rather than send it on.
- A check that passes only after a long run goes back to the executor once, with the line that ended the silence."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['TANDEM_HOME'] = tempfile.mkdtemp()
os.environ['TANDEM_STRICT'] = '0'
os.environ['TANDEM_WEB_CHECK'] = '0'
os.environ['TANDEM_CONTEXT'] = '65536'
for name in ('TANDEM_BASE_URL', 'LM_STUDIO_BASE_URL', 'TANDEM_MODEL', 'TANDEM_REPLY_TOKENS'):
    os.environ.pop(name, None)
from fake_server import Fake  # noqa: E402
from tandem_mcp import agent, engine, sandbox, store  # noqa: E402

checks = 0
PY = os.path.normpath(sys.executable)


def ok(cond, what):
    global checks
    assert cond, what
    checks += 1


def project():
    root = Path(tempfile.mkdtemp())
    (root / 'calc.py').write_text('def dbm_to_mw(dbm):\n    return 10 ** (dbm / 20)\n')
    (root / 'test_calc.py').write_text('from calc import dbm_to_mw\nassert abs(dbm_to_mw(10) - 10) < 1e-9, dbm_to_mw(10)\nprint("ok")\n')
    (root / 'notes.txt').write_text(''.join(f'line {i} of the notes\n' for i in range(1, 201)))
    return root


def run(root, script, fake, verify=None, **more):
    fake.script = list(script)
    fake.requests.clear()
    ws = sandbox.Workspace(root, more.pop('write_globs', None), more.pop('allow_run', None))
    job = agent.start('Fix calc.py so that the test passes.', ws, [f'{PY} test_calc.py'] if verify is None else verify,
                      more.pop('max_steps', 14), more.pop('max_repairs', 3), '', '', **more)
    agent.RUNNING[job][0].join(60)
    work = [r for r in fake.requests if 'Task:' in json.dumps(r['messages'][:2])]
    return job, store.read_job(job), work


def bare(messages):
    """The messages of a request without the state of the work at its end."""
    out = [dict(m) for m in messages]
    if out and isinstance(out[-1].get('content'), str):
        out[-1]['content'] = out[-1]['content'].split(agent.STATE_MARK)[0]
    return out


def shown(messages):
    """Contents of the write_file calls as a request shows them."""
    return [json.loads(tc['function']['arguments']).get('content', '') for m in messages
            for tc in (m.get('tool_calls') or []) if tc['function']['name'] == 'write_file']


fake = Fake(tools=True, schema=True)
engine.connect(url=fake.url)
BIG = ''.join(f'def helper_{i}(x):\n    return x + {i}\n' for i in range(40))
FIX = ('replace_in_file', {'path': 'calc.py', 'old': 'dbm / 20', 'new': 'dbm / 10'})

# 1. every request starts with the whole previous one: nothing before the end is rewritten -----------------
job, data, work = run(project(), [
    ('read_file', {'path': 'calc.py'}),
    ('write_file', {'path': 'helpers.py', 'content': BIG}),
    ('list_files', {'glob': '*'}),
    ('finish', {'summary': 'first try'}),                     # the check still fails: a repair is asked
    FIX,
    ('read_file', {'path': 'notes.txt', 'start': 1, 'end': 5}),
    ('finish', {'summary': 'Fixed the exponent.'}),
], fake)
ok(data['state'] == 'verified' and data['repairs'] == 1, f'job verified after one repair: {data["state"]}')
ok(len(work) == 7, f'one request per step: {len(work)}')
for k in range(len(work) - 1):
    a, b = bare(work[k]['messages']), bare(work[k + 1]['messages'])
    ok(b[:len(a)] == a, f'request {k + 2} starts with request {k + 1} unchanged')
ok(all(agent.STATE_MARK not in str(r['messages'][1]['content']) for r in work), 'the task message is never rewritten')
ok(agent.STATE_MARK + '\n- changed calc.py (+1 -1)' in work[-1]['messages'][-1]['content'],
   'the state of the work ends the last request')
ok(BIG in shown(work[-1]['messages']), 'a write of a file that did not change again stays whole')
ok(all(r['max_tokens'] == agent.REPLY_TOKENS for r in work), f'room for a whole file in each reply: {[r["max_tokens"] for r in work]}')

# 2. a write is compacted once its file changes again, and stays compacted --------------------------------
root = project()
job, data, work = run(root, [
    ('write_file', {'path': 'helpers.py', 'content': BIG}),
    ('list_files', {'glob': '*'}),
    ('list_files', {'glob': '*.py'}),
    ('replace_in_file', {'path': 'helpers.py', 'old': 'return x + 0\n', 'new': 'return x\n'}),
    ('list_files', {'glob': '*.txt'}),
    ('write_file', {'path': 'helpers.py', 'content': BIG + 'VALUE = 1\n'}),
    ('list_files', {'glob': 'c*'}),
    FIX,
    ('finish', {'summary': 'Fixed the exponent.'}),
], fake)
ok(data['state'] == 'verified', f'job verified: {data["state"]}')
stub = '[compacted persisted write_file: helpers.py'
ok(BIG in shown(work[3]['messages']) and stub not in json.dumps(work[3]['messages']),
   'three steps after the write the model still sees it whole')
ok(stub in json.dumps(work[5]['messages']), 'after an edit of the file the first write is compacted')
first = [i for i, r in enumerate(work) if stub in json.dumps(r['messages'])][0]
ok(all(stub in json.dumps(r['messages']) for r in work[first:]), 'once compacted, a write never comes back whole')
ok('VALUE = 1' in json.dumps(work[-1]['messages']), 'the latest write of the file is shown whole')
ok(len(data.get('compact_ids') or []) == 1, f'only the superseded write is compacted: {data.get("compact_ids")}')

# 3. past its budget the conversation is cut once, down to 70% of it ------------------------------------
os.environ['TANDEM_CONTEXT'] = '3000'                        # a budget of 3000 * 0.6 * 3.2 = 5760 characters
reads = [('read_file', {'path': 'notes.txt', 'start': 1 + 10 * i, 'end': 10 + 10 * i}) for i in range(14)]
job, data, work = run(project(), reads + [FIX, ('finish', {'summary': 'done'})], fake, max_steps=20)
budget = int(3000 * 0.6 * 3.2)
sizes = [agent._size(r['messages']) for r in work]
ok(data['state'] == 'verified' and 1 <= data['shrinks'] < len(reads) // 2,
   f'the cut happens rarely, not at every step: {data["shrinks"]} cuts in {len(work)} steps')
ok(max(sizes) <= budget + 1500, f'requests stay near the budget: {max(sizes)} chars for a budget of {budget}')
os.environ['TANDEM_CONTEXT'] = '65536'

# 4. a reply cut off by the token budget is asked again with a larger budget ----------------------------
cut_prose = {'content': 'The workspace is ready. I will now write the whole file with', 'finish': 'length'}
cut_call = {'calls': [('write_file', '{"path": "calc.py", "content": "def dbm_to_mw(dbm):\\n    return 10 ** (dbm')],
            'finish': 'length'}
job, data, work = run(project(), [cut_prose, FIX, cut_call, ('read_file', {'path': 'calc.py'}),
                                  ('finish', {'summary': 'Fixed the exponent.'})], fake)
budgets = [r['max_tokens'] for r in work]
ok(data['state'] == 'verified', f'job verified: {data["state"]}')
ok(budgets[:2] == [agent.REPLY_TOKENS, 2 * agent.REPLY_TOKENS], f'prose cut off: asked again with twice the room: {budgets}')
ok(budgets[2:4] == [agent.REPLY_TOKENS, 2 * agent.REPLY_TOKENS], f'half written call: asked again too: {budgets}')
ok(not any('not a tool call' in json.dumps(r['messages']) for r in work), 'a cut reply is never taken for prose')
ok(not any('not valid JSON' in json.dumps(r['messages']) for r in work), 'a half written call never reaches the executor')
ledger = [json.loads(line) for line in store.LEDGER.read_text().splitlines()]
ok(sum(1 for r in ledger if r.get('kind') == 'retry' and 'cut off' in str(r.get('error'))) >= 2, 'the repeats are in the ledger')

# 5. in a small context the reply budget leaves room for the prompt ----------------------------------------
os.environ['TANDEM_CONTEXT'] = '4096'
job, data, work = run(project(), [FIX, ('finish', {'summary': 'Fixed the exponent.'})], fake)
ok(all(1024 <= r['max_tokens'] <= 4096 - agent._size(r['messages']) // 3 - 512 for r in work),
   f'reply budget within the context: {[r["max_tokens"] for r in work]}')
job, data, work = run(project(), [cut_prose, FIX, ('finish', {'summary': 'Fixed the exponent.'})], fake)
ok(data['state'] == 'verified' and work[1]['max_tokens'] == work[0]['max_tokens'],
   f'the repeat of a cut reply stays within the context too: {[r["max_tokens"] for r in work]}')
os.environ['TANDEM_CONTEXT'] = '65536'

# 6. evidence is kept from one finish to the next, and checked again against the files --------------------
CONS = ['calc.py dbm_to_mw divides dbm by 10', 'calc.py keeps the signature def dbm_to_mw(dbm)']
both = [{'constraint': 1, 'path': 'calc.py', 'quote': 'return 10 ** (dbm /'},
        {'constraint': 2, 'path': 'calc.py', 'quote': 'def dbm_to_mw(dbm):'}]
job, data, work = run(project(), [
    ('replace_in_file', {'path': 'calc.py', 'old': 'dbm / 20', 'new': 'dbm / 11'}),
    ('finish', {'summary': 'first try', 'evidence': both}),   # the check fails; the evidence matches
    ('replace_in_file', {'path': 'calc.py', 'old': 'dbm / 11', 'new': 'dbm / 10'}),
    ('finish', {'summary': 'Fixed the exponent.'}),            # no evidence given again
], fake, constraints=CONS, require_proof=True)
ok(data['state'] == 'verified' and data['repairs'] == 1 and not data['unproven'],
   f'evidence given before still counts at the next finish: {data["state"]} unproven={data["unproven"]}')
ok('evidence you gave that matches the files is kept' in json.dumps(work[2]['messages']),
   'the repair message says the evidence is kept')
job, data, work = run(project(), [
    ('finish', {'summary': 'first try', 'evidence': [{'constraint': 1, 'path': 'calc.py', 'quote': 'return 10 ** (dbm / 20)'},
                                                     both[1]]}),
    FIX,                                                       # the quoted line is edited away
    ('finish', {'summary': 'Fixed the exponent.'}),
    ('finish', {'summary': 'Fixed the exponent.', 'evidence': [{'constraint': 1, 'path': 'calc.py',
                                                                'quote': 'return 10 ** (dbm / 10)'}]}),
], fake, constraints=CONS, require_proof=True)
ok(data['state'] == 'verified' and data['repairs'] == 2, f'a stale quote no longer counts: {data["state"]} {data["repairs"]}')
ok('Constraint 1 has no checked evidence' in json.dumps(work[3]['messages'])
   and 'Constraint 2 has no checked evidence' not in json.dumps(work[3]['messages']),
   'only the constraint whose line changed is asked again')

# 7. after a call repeated three times the next two replies are sampled less greedily ----------------------
same = ('read_file', {'path': 'calc.py'})
job, data, work = run(project(), [same, same, same, ('list_files', {'glob': '*'}), ('list_files', {'glob': '*.py'}),
                                  FIX, ('finish', {'summary': 'Fixed the exponent.'})], fake)
temps = [r['temperature'] for r in work]
ok(data['state'] == 'verified' and temps[:3] == [0.1, 0.1, 0.1] and temps[3:5] == [agent.HOT_TEMPERATURE] * 2
   and temps[5:] == [0.1, 0.1], f'temperature raised for two replies after the third identical call: {temps}')

# 8. a conversation saved by an older version loses the state it kept in the task message ------------------
root = project()
fake.script = [FIX, ('finish', {'summary': 'Fixed the exponent.'})]
fake.requests.clear()
(store.JOBS / 'job-legacy').mkdir(parents=True, exist_ok=True)
task = agent.Task('job-legacy', store.JOBS / 'job-legacy', 'Fix calc.py so that the test passes.',
                  sandbox.Workspace(root), [f'{PY} test_calc.py'], max_steps=6)
messages = task.opening()
messages[1]['content'] += agent.STATE_MARK + '\n- no file changed yet\n- step 4, repairs asked 0.'
ok(task.loop(messages) == 'verified', 'legacy conversation runs')
ok(all(agent.STATE_MARK not in str(r['messages'][1]['content']) for r in fake.requests if 'Task:' in json.dumps(r['messages'][:2])),
   'the old state note is taken out of the task message')

# 9. a long check output is cut around the lines that name a failure, not only at its end ------------------
steps = ['FAIL: ui_test'] + [f'  ok  step {i} {{"js": "window.app.value_{i} === {i}"}}: -> true' for i in range(1, 5)]
steps += ['  BAD step 5 {"js": "window.app.speed === 1.5"}: window.app.speed === 1.5 -> false']
steps += [f'  ok  step {i} {{"js": "window.app.value_{i} === {i}"}}: window.app.value_{i} === {i} -> true' for i in range(6, 60)]
long = '\n'.join(steps)
cut = agent._focus(long, 1500)
ok(len(long) > 3000 and len(cut) <= 1500 and 'BAD step 5' in cut and cut.endswith('-> true')
   and 'step 59' in cut, f'the failing step is kept with the end of the output: {len(cut)} chars')
ok('BAD step 5' not in long[-1500:], 'the plain tail would have lost it')
pytest_out = ('test_a.py::test_one PASSED\n' * 80 + 'E   AssertionError: assert 3 == 4\n'
              + 'test_a.py::test_two PASSED\n' * 80 + '1 failed, 160 passed in 0.5s')
cut = agent._focus(pytest_out, 1500)
ok('AssertionError: assert 3 == 4' in cut and cut.endswith('1 failed, 160 passed in 0.5s'),
   'a test runner failure in the middle of its output is kept')
ok(agent._focus('x' * 3000, 1500) == 'x' * 1500 and agent._focus('short output\n', 1500) == 'short output',
   'without a failure line, or when short, the output is cut as before')

# 10. three finishes in a row that change nothing and fail the same way end the job ------------------------
from tandem_mcp import server  # noqa: E402
done = ('finish', {'summary': 'All checks pass.'})
job, data, work = run(project(), [done, done, done, FIX, done], fake)
ok(data['state'] == 'stuck' and data['repairs'] == 2 and len(work) == 3,
   f'stopped at the third identical finish: {data["state"]} repairs={data["repairs"]} requests={len(work)}')
ok('Nothing changed since your last finish' in json.dumps(work[2]['messages'])
   and 'Nothing changed since your last finish' not in json.dumps(work[1]['messages']),
   'the second identical finish is warned before the job ends')
receipt = server._auto_receipt(job)
ok('FAILED (stuck)' in receipt and '- stopped: finished three times' in receipt and 'AssertionError' in receipt,
   f'the receipt says why it stopped and what fails: {receipt}')
job, data, work = run(project(), [
    done, ('replace_in_file', {'path': 'calc.py', 'old': 'dbm / 20', 'new': 'dbm / 11'}), done,
    ('replace_in_file', {'path': 'calc.py', 'old': 'dbm / 11', 'new': 'dbm / 12'}), done,
    ('replace_in_file', {'path': 'calc.py', 'old': 'dbm / 12', 'new': 'dbm / 10'}), done], fake, max_repairs=4)
ok(data['state'] == 'verified' and data['repairs'] == 3, f'a finish after a change is not stale: {data["state"]}')
aside = [('replace_in_file', {'path': 'notes.txt', 'old': f'line {i} of', 'new': f'line {i} in'}) for i in (1, 2, 3)]
job, data, work = run(project(), [done, aside[0], done, aside[1], done, aside[2], done, FIX, done], fake, max_repairs=6)
ok(data['state'] == 'stuck' and data['repairs'] == 2 and 'at 3 finishes in a row' in data['summary'],
   f'changes that leave the failure as it was end the job at the third finish: {data["state"]} {data["summary"]}')
ok('This is finish 2 in a row with exactly the same failure' in json.dumps(work[-1]['messages']),
   'the second identical failure is warned before the job ends')
receipt = server._auto_receipt(job)
ok('the same way at its last 3 finishes, so a hint rarely helps' in receipt and 'job_continue(' in receipt,
   f'the receipt of a repeated failure tells the orchestrator to fix it, not to send it on: {receipt}')
job, data, work = run(project(), [done], fake, max_repairs=0)
receipt = server._auto_receipt(job)
ok(data['state'] == 'checks_failed' and 'hint rarely helps' not in receipt and 'sends it on locally' in receipt,
   f'a failure seen once is sent on as before: {receipt}')

# 11. a check that passes only after a long run goes back once, with the line that came after the silence ---
timing = {}
probe = Path(tempfile.mkdtemp()) / 'probe.py'
probe.write_text('import time\nprint("first", flush=True)\ntime.sleep(0.8)\nprint("after the wait")\n')
code, out = sandbox.run(f'{PY} {probe}', probe.parent, 30, timing=timing)
ok(code == 0 and timing['seconds'] >= 0.8 and timing['gaps'][0][1] == 'after the wait' and timing['gaps'][0][0] >= 0.7,
   f'the run time and the line that ended the longest silence: {timing}')
os.environ['TANDEM_SLOW_CHECK_S'] = '1'


def slow_project():
    root = project()
    (root / 'calc.py').write_text('SLOW = True\n\n\ndef dbm_to_mw(dbm):\n    return 10 ** (dbm / 20)\n')
    (root / 'test_calc.py').write_text('import time\nfrom calc import dbm_to_mw, SLOW\n'
                                       'assert abs(dbm_to_mw(10) - 10) < 1e-9, dbm_to_mw(10)\nprint("value ok")\n'
                                       'if SLOW:\n    time.sleep(1.6)\nprint("edge case ok")\n')
    return root


SPEED = ('replace_in_file', {'path': 'calc.py', 'old': 'SLOW = True', 'new': 'SLOW = False'})
job, data, work = run(slow_project(), [FIX, done, SPEED, done], fake)
told = json.dumps(work[-1]['messages'])
ok(data['state'] == 'verified' and data['repairs'] == 1 and data['slow'] == [],
   f'the slow check went back once and passed fast: {data["state"]} repairs={data["repairs"]} slow={data["slow"]}')
ok('All checks pass, but they are slow' in told and 'edge case ok' in told,
   'the executor is told which output line came after the long silence')
ok('passes but takes' not in server._auto_receipt(job), 'a check made fast leaves no note')
job, data, work = run(slow_project(), [FIX, done, done], fake)
ok(data['state'] == 'verified' and data['repairs'] == 1 and len(data['slow']) == 1,
   f'a check still slow at the next finish is accepted: {data["state"]} slow={data["slow"]}')
ok(json.dumps(work[-1]['messages']).count('All checks pass, but they are slow') == 1, 'the slow check goes back only once')
receipt = server._auto_receipt(job)
ok('ACCEPTED' in receipt and 'passes but takes 2 s' in receipt, f'the orchestrator learns it is slow: {receipt}')
os.environ['TANDEM_SLOW_CHECK_S'] = '0'
job, data, work = run(slow_project(), [FIX, done], fake)
ok(data['state'] == 'verified' and data['repairs'] == 0, 'TANDEM_SLOW_CHECK_S=0 turns the slow check off')
os.environ.pop('TANDEM_SLOW_CHECK_S')

# 12. a job that fails on the model server before it saved anything says why, and is not offered job_continue -
job, data, work = run(project(), [{'status': 400, 'error': None}], fake)
receipt = server._auto_receipt(job)
ok(data['state'] == 'error' and '- error: ExecutorError' in receipt and 'delegate again' in receipt
   and 'job_continue(' not in receipt, f'the error and the way on are in the receipt: {receipt}')

fake.close()
print(f'test_local_loop: {checks} checks, 0 failures')
