"""The same tools against a real local model. Needs a running server (LM Studio, Ollama,
llama.cpp, vLLM or any OpenAI compatible one); TANDEM_BASE_URL and TANDEM_MODEL select it.

    python tests/test_live.py            # the model as it is
    python tests/test_live.py --text     # the same model driven through JSON replies,
                                         # as a model with no native tool calling would be

Each line is one behaviour a user relies on; the exit code is the number of failures."""
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['TANDEM_HOME'] = tempfile.mkdtemp()
from tandem import engine, server, store  # noqa: E402

logging.disable(logging.INFO)
PY = sys.executable
failures = []


def check(what, cond, detail=''):
    print(f'  {"PASS" if cond else "FAIL"}  {what}' + (f'\n        {str(detail)[:700]}' if not cond else ''), flush=True)
    if not cond:
        failures.append(what)


try:
    where = engine.connect()
    model = engine.default_model()
except engine.ExecutorError as exc:
    print(f'skipped: {exc}')
    sys.exit(0)
start = time.time()
found = engine.probe(model, force=True)
print(f'{model} on {where["name"]} ({where["url"]}), context {engine.context_tokens(model)}')
print(f'  probe: {server._caps_line(found)}  [{time.time() - start:.0f} s]', flush=True)
if '--text' in sys.argv:
    engine.remember(model, tools=False)
    print('  forced: JSON replies in place of native tool calls')

# reading with checked evidence
work = Path(tempfile.mkdtemp())
spec = work / 'regulator.txt'
spec.write_text('\n'.join(
    ['Power stage notes', ''] + [f'Filler line {n}: nothing of interest here, only layout remarks.' for n in range(1, 30)] +
    ['The buck converter U7 switches at 1.2 MHz.', 'Its inductor L3 is 4.7 uH with a saturation current of 3.1 A.'] +
    [f'Filler line {n}: more remarks about silkscreen and courtyard.' for n in range(30, 60)] +
    ['The output capacitor bank is 2 x 22 uF.', '']))
start = time.time()
out = server.digest_file(str(spec), 'What is the switching frequency of the buck converter and the value of its inductor?')
print(f'digest_file [{time.time() - start:.0f} s]')
check('answers from the file', '1.2' in out and '4.7' in out, out)
check('gives quotes that are in the file', 'Evidence (checked against the source)' in out and 'regulator.txt:3' in out, out)
check('no evidence was dropped', 'WARNING' not in out, out)
start = time.time()
out = server.digest_file(str(spec), 'What is the input voltage range of the converter?')
print(f'digest_file, a question the file does not answer [{time.time() - start:.0f} s]')
check('says the file does not answer, or shows no checked quote for a made-up value',
      'Evidence (checked' not in out or any(w in out.lower() for w in ('not ', 'no ', 'does not', "doesn't", 'unknown')), out)
start = time.time()
out = server.extract_from_file(str(spec), json.dumps({'type': 'object', 'required': ['frequency_mhz', 'inductor_uh', 'saturation_a'], 'properties': {
    'frequency_mhz': {'type': 'number'}, 'inductor_uh': {'type': 'number'}, 'saturation_a': {'type': 'number'}}}),
    'The buck converter: switching frequency in MHz, inductor value in uH, saturation current in A.')
print(f'extract_from_file [{time.time() - start:.0f} s]')
try:
    data = json.loads(out.splitlines()[0])
except ValueError:
    data = {}
check('extracts the three values in the schema', data == {'frequency_mhz': 1.2, 'inductor_uh': 4.7, 'saturation_a': 3.1}, out)
start = time.time()
out = server.ask('Is 17 a prime number? Answer with the single word yes or no.', samples=3, max_tokens=1500)
print(f'ask with samples [{time.time() - start:.0f} s]')
check('agreement score on an easy fact', out.startswith('[agreement 1.00') and 'yes' in out.lower(), out)

# a delegated task under a contract
root = Path(tempfile.mkdtemp())
(root / 'calc.py').write_text('"""Radio maths."""\n\n\ndef dbm_to_mw(dbm):\n    """Power in mW from dBm."""\n    return 10 ** (dbm / 20)\n\n\n'
                              'def swr(forward, reflected):\n    """Standing wave ratio from forward and reflected power."""\n'
                              '    rho = (reflected / forward) ** 0.5\n    return (1 + rho) / (1 - rho)\n')
(root / 'test_calc.py').write_text('from calc import dbm_to_mw, swr\n\nassert abs(dbm_to_mw(0) - 1) < 1e-9\n'
                                   'assert abs(dbm_to_mw(10) - 10) < 1e-9, dbm_to_mw(10)\nassert abs(swr(100, 4) - 1.5) < 1e-9\n'
                                   'assert swr(0, 0) == 1.0\nprint("all good")\n')
start = time.time()
out = server.delegate('test_calc.py fails. Fix calc.py so that the test passes.', str(root), verify_commands=[f'{PY} test_calc.py'],
                      allow_run=[r'^\S*python\S* test_calc\.py$'], wait_seconds=1200, max_steps=20)
job = out.split()[1].rstrip(':')
data = store.read_job(job) or {}
print(f'delegate [{time.time() - start:.0f} s, {data.get("steps")} steps, {data.get("repairs")} repairs, {data.get("protocol")}]')
check('the job ends verified', data.get('state') == 'verified', out)
check('the test was failing before and passes after', '(failed before the job)' in out and 'check PASS' in out, out)
check('only calc.py changed, the test is untouched', [c[0] for c in data.get('changes', [])] == ['calc.py'] and
      'assert swr(0, 0) == 1.0' in (root / 'test_calc.py').read_text(), out)
diff = server.job_diff(job)
check('the diff holds the fix', 'dbm / 10' in diff.replace('dbm/10', 'dbm / 10'), diff)
check('rollback puts the bug back', 'restored: calc.py' in server.job_rollback(job) and 'dbm / 20' in (root / 'calc.py').read_text())
print(server.ledger_report().splitlines()[-1])
print(f'{len(failures)} failure(s)')
sys.exit(len(failures))
