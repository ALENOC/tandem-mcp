"""Offline integration tests for not_evaluated verifier prerequisites vs genuine artifact defects."""
import hashlib
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

tmp = Path(tempfile.mkdtemp(prefix='tandem_not_eval_'))
os.environ['TANDEM_HOME'] = str(tmp / 'home')
os.environ['TANDEM_PROFILE'] = 'lean'
os.environ['TANDEM_COMPACT_RECEIPT'] = '1'

from fake_server import Fake  # noqa: E402
from tandem_mcp import agent, engine, host_runner, sandbox, store  # noqa: E402

store.init()
PY = sys.executable
checks = 0


def ok(cond, msg):
    global checks
    assert cond, msg
    checks += 1


WEB_STUB = """<!doctype html>
<html lang="it">
<head><meta charset="utf-8"><title>Counter</title></head>
<body style="background:#0b1020;color:#fff;font-family:sans-serif;padding:24px;">
  <div id="count">0</div>
  <button id="inc" type="button">Increment</button>
  <button id="reset" type="button">Reset</button>
  <script>
    // TODO: wire Increment and Reset
  </script>
</body>
</html>
"""

WEB_VERIFY = """import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const chromePath = (() => {
  const base = path.join(os.homedir(), '.cache', 'ms-playwright');
  const dirs = fs.readdirSync(base).filter((d) => d.startsWith('chromium-')).sort().reverse();
  for (const d of dirs) {
    for (const sub of ['chrome-linux64/chrome', 'chrome-linux/chrome']) {
      const p = path.join(base, d, sub);
      if (fs.existsSync(p)) return p;
    }
  }
  return '/usr/bin/chromium';
})();

const dir = process.cwd();
const srv = http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  fs.createReadStream(path.join(dir, 'index.html')).pipe(res);
});
await new Promise((r) => srv.listen(0, '127.0.0.1', r));
const port = srv.address().port;
const userDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ui-ver-'));
const chrome = spawn(chromePath, ['--headless=new', '--no-sandbox', '--disable-gpu', '--remote-debugging-port=0', `--user-data-dir=${userDir}`, 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
const errs = [];
try {
  const wsUrl = await new Promise((res, rej) => {
    let b = '';
    chrome.stderr.on('data', (c) => { b += c; const m = b.match(/DevTools listening on (ws:\\/\\/\\S+)/); if (m) res(m[1]); });
    chrome.on('exit', (c) => rej(new Error('exit ' + c)));
  });
  const targets = await (await fetch(`http://127.0.0.1:${new URL(wsUrl).port}/json`)).json();
  const ws = new WebSocket(targets.find((t) => t.type === 'page').webSocketDebuggerUrl);
  await new Promise((r) => { ws.onopen = r; });
  let seq = 1;
  const call = (method, params = {}) => new Promise((res, rej) => {
    const id = seq++;
    const h = (ev) => { const d = JSON.parse(ev.data); if (d.id === id) { ws.removeEventListener('message', h); if (d.error) rej(new Error(d.error.message)); else res(d.result); } };
    ws.addEventListener('message', h);
    ws.send(JSON.stringify({ id, method, params }));
  });
  ws.addEventListener('message', (ev) => {
    const m = JSON.parse(ev.data);
    if (m.method === 'Runtime.exceptionThrown') errs.push(m.params?.exceptionDetails?.text || 'exception');
  });
  await call('Page.enable');
  await call('Runtime.enable');
  await call('Page.navigate', { url: `http://127.0.0.1:${port}/index.html` });
  await sleep(300);
  const ev = (expr) => call('Runtime.evaluate', { expression: expr, returnByValue: true }).then((r) => r.result?.value);
  await ev(`document.querySelector('#inc').click(); document.querySelector('#inc').click();`);
  await sleep(100);
  const afterInc = Number((await ev(`document.querySelector('#count').textContent`)).trim());
  await ev(`document.querySelector('#reset').click();`);
  await sleep(100);
  const afterReset = Number((await ev(`document.querySelector('#count').textContent`)).trim());
  if (errs.length || afterInc !== 2 || afterReset !== 0) {
    console.error(`FAIL errs=${errs.length} afterInc=${afterInc} afterReset=${afterReset}`);
    process.exit(1);
  }
  const pf = process.env.TANDEM_PROOF_FILE || '';
  const nonce = process.env.TANDEM_VERIFY_NONCE || '';
  if (pf) {
    fs.writeFileSync(pf, JSON.stringify({
      nonce,
      proofs: [
        { constraint: 1, passed: true, observed: 'Increment clicked twice updated #count 0->2 (0 JS errors)' },
        { constraint: 2, passed: true, observed: 'Reset clicked restored #count 2->0 (0 JS errors)' },
      ],
    }));
  }
  console.log('VERIFY_UI_OK afterInc=2 afterReset=0');
} finally {
  chrome.kill('SIGKILL');
  srv.close();
  fs.rmSync(userDir, { recursive: true, force: true });
}
"""

CONSTRAINTS = [
    'Increment button (#inc) increments #count by 1 on each click.',
    'Reset button (#reset) resets #count to 0.',
]


try:
    fake = Fake(tools=True, schema=True)
    engine.connect(url=fake.url)

    # 1. Historical web B_save offline reproduction: Chromium cache blocked inside jail -> not_evaluated, 0 repairs, 0 post-finish LLM calls
    ws1 = tmp / 'ws_not_eval'
    ws1.mkdir()
    (ws1 / 'index.html').write_text(WEB_STUB, encoding='utf-8')
    (ws1 / 'scripts').mkdir()
    (ws1 / 'scripts' / 'verify_ui.mjs').write_text(WEB_VERIFY, encoding='utf-8')

    step2_script = (
        "    let n = 0;\n"
        "    document.querySelector('#inc').addEventListener('click', () => { n++; document.querySelector('#count').textContent = String(n); });\n"
        "    document.querySelector('#reset').addEventListener('click', () => { n = 0; document.querySelector('#count').textContent = '0'; });"
    )
    fake.script = [
        ('replace_in_file', {'path': 'index.html', 'old': '    // TODO: wire Increment and Reset', 'new': step2_script}),
        ('finish', {
            'summary': 'Wired #inc and #reset in index.html.',
            'evidence': [
                {'constraint': 1, 'path': 'index.html', 'quote': "document.querySelector('#inc').addEventListener"},
                {'constraint': 2, 'path': 'index.html', 'quote': "document.querySelector('#reset').addEventListener"},
            ],
        }),
        # Sentinel: must NEVER be reached because no repair should be requested
        ('write_file', {'path': 'index.html', 'content': 'SHOULD_NOT_RUN'}),
    ]
    t0 = time.monotonic()
    jid1 = 'not-eval-web-bsave'
    (store.JOBS / jid1).mkdir(parents=True, exist_ok=True)
    t1 = agent.Task(
        jid1, store.JOBS / jid1, 'Update index.html for #inc and #reset',
        sandbox.Workspace(str(ws1), ['index.html'], [], []),
        verify=['node scripts/verify_ui.mjs'], max_steps=8, max_repairs=2, baseline=False,
        constraints=CONSTRAINTS, require_proof=True, unjailed_checks=False,
    )
    st1 = t1.run()
    wall1 = round(time.monotonic() - t0, 2)
    r1 = host_runner.attach_and_wait(jid1, data_dir=store.DATA, poll_interval_s=0.05, timeout_s=5.0)['summary']
    print(f'=== HISTORICAL WEB B_SAVE OFFLINE REPRO (wall={wall1}s, repairs={t1.repairs}) ===\n{r1}')
    ok(st1 == 'not_evaluated', f'expected not_evaluated, got {st1}')
    ok(t1.repairs == 0, f'expected 0 repairs, got {t1.repairs}')
    ok(len(fake.script) == 1, f'expected 0 post-finish LLM calls, remaining script={fake.script}')
    ok('SHOULD_NOT_RUN' not in (ws1 / 'index.html').read_text(encoding='utf-8'), 'artifact overwritten after finish')
    ok('COVERAGE: incomplete_not_evaluated' in r1 and 'MISSING_PREREQUISITE:' in r1, f'bad receipt: {r1}')
    ok('exit=0 cmd=tandem:web_check' in r1 and 'COVERAGE: complete' not in r1, f'smoke check lost or overclaimed: {r1}')

    # 2. Browser available (unjailed_checks=True) + genuinely broken interaction -> triggers repair, then passes
    ws2 = tmp / 'ws_broken_inc'
    ws2.mkdir()
    (ws2 / 'index.html').write_text(WEB_STUB, encoding='utf-8')
    (ws2 / 'scripts').mkdir()
    (ws2 / 'scripts' / 'verify_ui.mjs').write_text(WEB_VERIFY, encoding='utf-8')
    fake.script = [
        # Broken #inc (does not update #count)
        ('replace_in_file', {'path': 'index.html', 'old': '    // TODO: wire Increment and Reset', 'new': "    document.querySelector('#reset').addEventListener('click', () => { document.querySelector('#count').textContent = '0'; });"}),
        ('finish', {
            'summary': 'First attempt.',
            'evidence': [
                {'constraint': 1, 'path': 'index.html', 'quote': 'Increment'},
                {'constraint': 2, 'path': 'index.html', 'quote': "document.querySelector('#reset').addEventListener"},
            ],
        }),
        # Repair: fix #inc
        ('replace_in_file', {'path': 'index.html', 'old': "    document.querySelector('#reset')", 'new': "    let n = 0;\n    document.querySelector('#inc').addEventListener('click', () => { n++; document.querySelector('#count').textContent = String(n); });\n    document.querySelector('#reset')"}),
        ('finish', {
            'summary': 'Fixed #inc and #reset.',
            'evidence': [
                {'constraint': 1, 'path': 'index.html', 'quote': "document.querySelector('#inc').addEventListener"},
                {'constraint': 2, 'path': 'index.html', 'quote': "document.querySelector('#reset').addEventListener"},
            ],
        }),
    ]
    jid2 = 'broken-ui-repair'
    (store.JOBS / jid2).mkdir(parents=True, exist_ok=True)
    t2 = agent.Task(
        jid2, store.JOBS / jid2, 'Update index.html for #inc and #reset',
        sandbox.Workspace(str(ws2), ['index.html'], [], []),
        verify=['node scripts/verify_ui.mjs'], max_steps=8, max_repairs=2, baseline=False,
        constraints=CONSTRAINTS, require_proof=True, unjailed_checks=True,
    )
    st2 = t2.run()
    r2 = host_runner.attach_and_wait(jid2, data_dir=store.DATA, poll_interval_s=0.05, timeout_s=5.0)['summary']
    ok(st2 == 'verified' and t2.repairs == 1, f'expected verified after 1 repair, got state={st2} repairs={t2.repairs}')
    ok('COVERAGE: complete (2/2 contract requirements verified:' in r2, f'expected complete after repair: {r2}')

    # 3. Generic app ENOENT (missing data file required by app) must remain a genuine defect (checks_failed), NOT not_evaluated
    ws3 = tmp / 'ws_app_enoent'
    ws3.mkdir()
    (ws3 / 'app.py').write_text('def load():\n    return open("missing_data.csv").read()\n', encoding='utf-8')
    (ws3 / 'test_app.py').write_text('from app import load\nload()\n', encoding='utf-8')
    fake.script = [
        ('write_file', {'path': 'app.py', 'content': 'def load():\n    return open("missing_data.csv").read()\n'}),
        ('finish', {'summary': 'Done.', 'evidence': [{'constraint': 1, 'path': 'app.py', 'quote': 'missing_data.csv'}]}),
    ]
    jid3 = 'app-enoent-defect'
    (store.JOBS / jid3).mkdir(parents=True, exist_ok=True)
    t3 = agent.Task(
        jid3, store.JOBS / jid3, 'Fix app.py',
        sandbox.Workspace(str(ws3), ['app.py'], [], []),
        verify=[f'{PY} test_app.py'], max_steps=6, max_repairs=0, baseline=False,
        constraints=['load() returns data without FileNotFoundError.'], require_proof=True,
    )
    st3 = t3.run()
    ok(st3 == 'checks_failed', f'generic app ENOENT must be checks_failed, got {st3}')

    # 4. Regression: generic/custom verifier finding wrong artifact result and exiting with exit=2 MUST be a defect (triggers repair), NOT not_evaluated
    ws4 = tmp / 'ws_exit2_defect'
    ws4.mkdir()
    (ws4 / 'math_mod.py').write_text('def add(a, b):\n    return 0\n', encoding='utf-8')
    (ws4 / 'check_math.py').write_text(
        'import json, os, sys\n'
        'nonce = os.environ.pop("TANDEM_VERIFY_NONCE", "")\n'
        'pf = os.environ.pop("TANDEM_PROOF_FILE", "")\n'
        'import math_mod\n'
        'if math_mod.add(2, 3) != 5:\n'
        '    print("FAIL: add(2, 3) returned", math_mod.add(2, 3))\n'
        '    sys.exit(2)\n'
        'payload = json.dumps({"nonce": nonce, "proofs": [{"constraint": 1, "passed": True, "observed": "add(2,3)==5"}]})\n'
        'if pf:\n'
        '    open(pf, "w").write(payload)\n'
        'else:\n'
        '    print("TANDEM_PROOF_JSON:" + payload)\n',
        encoding='utf-8',
    )
    fake.script = [
        ('write_file', {'path': 'math_mod.py', 'content': 'def add(a, b):\n    return 0\n'}),
        ('finish', {'summary': 'Broken add.', 'evidence': [{'constraint': 1, 'path': 'math_mod.py', 'quote': 'return 0'}]}),
        ('write_file', {'path': 'math_mod.py', 'content': 'def add(a, b):\n    return a + b\n'}),
        ('finish', {'summary': 'Fixed add.', 'evidence': [{'constraint': 1, 'path': 'math_mod.py', 'quote': 'return a + b'}]}),
    ]
    jid4 = 'exit2-artifact-defect'
    (store.JOBS / jid4).mkdir(parents=True, exist_ok=True)
    t4 = agent.Task(
        jid4, store.JOBS / jid4, 'Fix add in math_mod.py',
        sandbox.Workspace(str(ws4), ['math_mod.py'], [], []),
        verify=[f'{PY} check_math.py'], max_steps=8, max_repairs=1, baseline=False,
        constraints=['add(2, 3) returns 5.'], require_proof=True,
    )
    st4 = t4.run()
    r4 = host_runner.attach_and_wait(jid4, data_dir=store.DATA, poll_interval_s=0.05, timeout_s=5.0)['summary']
    print(f'=== EXIT=2 ARTIFACT DEFECT REPAIRED (state={st4}, repairs={t4.repairs}) ===\n{r4}')
    ok(st4 == 'verified' and t4.repairs == 1, f'exit=2 defect must trigger repair and verify, got state={st4} repairs={t4.repairs}')
    ok('COVERAGE: complete (1/1 contract requirements verified:' in r4, f'expected complete after repair: {r4}')

    # 5. Opposite case: tandem:web_check exit=2 (missing browser) -> not_evaluated, 0 repairs
    ws5 = tmp / 'ws_web_missing_chrome'
    ws5.mkdir()
    (ws5 / 'index.html').write_text('<!doctype html><canvas id="c" width="100" height="100"></canvas><script>requestAnimationFrame(()=>{});</script>', encoding='utf-8')
    old_chrome = os.environ.get('TANDEM_CHROME')
    os.environ['TANDEM_CHROME'] = '/nonexistent/chrome_bin'
    try:
        fake.script = [
            ('write_file', {'path': 'index.html', 'content': '<!doctype html><canvas id="c" width="100" height="100"></canvas><script>requestAnimationFrame(()=>{});</script>'}),
            ('finish', {'summary': 'Created canvas.', 'evidence': [{'constraint': 1, 'path': 'index.html', 'quote': '<canvas'}]}),
        ]
        jid5 = 'webcheck-exit2-prereq'
        (store.JOBS / jid5).mkdir(parents=True, exist_ok=True)
        t5 = agent.Task(
            jid5, store.JOBS / jid5, 'Create index.html with animated canvas',
            sandbox.Workspace(str(ws5), ['index.html'], [], []),
            verify=[], max_steps=6, max_repairs=2, baseline=False,
            constraints=['Canvas animates.'], require_proof=True,
        )
        st5 = t5.run()
        r5 = host_runner.attach_and_wait(jid5, data_dir=store.DATA, poll_interval_s=0.05, timeout_s=5.0)['summary']
        print(f'=== TANDEM:WEB_CHECK EXIT=2 PREREQ (state={st5}, repairs={t5.repairs}) ===\n{r5}')
        ok(st5 == 'not_evaluated' and t5.repairs == 0, f'expected not_evaluated with 0 repairs, got state={st5} repairs={t5.repairs}')
        ok('not_evaluated (exit=2) cmd=tandem:web_check' in r5, f'missing web_check not_evaluated: {r5}')
    finally:
        if old_chrome is None:
            os.environ.pop('TANDEM_CHROME', None)
        else:
            os.environ['TANDEM_CHROME'] = old_chrome

    # 6. Combined job: 2 mandatory checks (1 fixable defect + 1 not_evaluated prerequisite) -> fixes defect (repairs=1), then stops not_evaluated (no further repairs)
    ws6 = tmp / 'ws_combined'
    ws6.mkdir()
    (ws6 / 'math_mod.py').write_text('def add(a, b):\n    return 0\n', encoding='utf-8')
    (ws6 / 'check_math.py').write_text((ws4 / 'check_math.py').read_text(encoding='utf-8'), encoding='utf-8')
    (ws6 / 'index.html').write_text(WEB_STUB, encoding='utf-8')
    (ws6 / 'scripts').mkdir()
    (ws6 / 'scripts' / 'verify_ui.mjs').write_text(WEB_VERIFY, encoding='utf-8')
    fake.script = [
        # Attempt 1: math_mod broken (triggers repair=1)
        ('write_file', {'path': 'math_mod.py', 'content': 'def add(a, b):\n    return 0\n'}),
        ('finish', {'summary': 'Initial.', 'evidence': [{'constraint': 1, 'path': 'math_mod.py', 'quote': 'return 0'}, {'constraint': 2, 'path': 'index.html', 'quote': 'Increment'}]}),
        # Attempt 2: math_mod fixed, verify_ui.mjs still not_evaluated in jail -> stops not_evaluated without repair=2
        ('write_file', {'path': 'math_mod.py', 'content': 'def add(a, b):\n    return a + b\n'}),
        ('finish', {'summary': 'Fixed math.', 'evidence': [{'constraint': 1, 'path': 'math_mod.py', 'quote': 'return a + b'}, {'constraint': 2, 'path': 'index.html', 'quote': 'Increment'}]}),
        ('write_file', {'path': 'math_mod.py', 'content': 'SHOULD_NOT_RUN'}),
    ]
    jid6 = 'combined-defect-and-prereq'
    (store.JOBS / jid6).mkdir(parents=True, exist_ok=True)
    t6 = agent.Task(
        jid6, store.JOBS / jid6, 'Fix math_mod.py and index.html',
        sandbox.Workspace(str(ws6), ['math_mod.py', 'index.html'], [], []),
        verify=[f'{PY} check_math.py', 'node scripts/verify_ui.mjs'], max_steps=10, max_repairs=3, baseline=False,
        constraints=['add(2, 3) returns 5.', 'Increment button updates #count.'], require_proof=True, unjailed_checks=False,
    )
    st6 = t6.run()
    r6 = host_runner.attach_and_wait(jid6, data_dir=store.DATA, poll_interval_s=0.05, timeout_s=5.0)['summary']
    print(f'=== COMBINED DEFECT + NOT_EVALUATED (state={st6}, repairs={t6.repairs}) ===\n{r6}')
    ok(st6 == 'not_evaluated' and t6.repairs == 1, f'expected not_evaluated after 1 repair, got state={st6} repairs={t6.repairs}')
    ok(len(fake.script) == 1, f'expected no further repair after defect fixed, remaining={fake.script}')
    ok('exit=0 cmd=' in r6 and 'check_math.py' in r6 and 'not_evaluated' in r6 and 'verify_ui.mjs' in r6, f'both checks must appear: {r6}')
    ok('COVERAGE: incomplete_not_evaluated' in r6 and 'COVERAGE: complete' not in r6, f'must block complete coverage: {r6}')

    # 7. Historical job without outcome field and exit=2 -> preserves exit=2 and signals uncertainty
    jid_hist = 'hist-exit2-unknown'
    (store.JOBS / jid_hist).mkdir(parents=True, exist_ok=True)
    store.write_job(jid_hist, {
        'id': jid_hist, 'state': 'checks_failed', 'changes': [['a.py', 'edit', 2, 1]],
        'checks': [{'command': 'python3 legacy_check.py', 'exit': 2, 'tail': 'exit 2'}],
        'constraints': ['c1'], 'unproven': [],
    })
    r_hist = host_runner._format_host_summary(jid_hist, 12.0, False)
    ok('exit=2 cmd=python3 legacy_check.py [historical exit=2: outcome_unknown_prereq_vs_defect]' in r_hist, f'historical uncertainty missing: {r_hist}')

    print(f'{checks} checks, 0 failures')
finally:
    shutil.rmtree(tmp, ignore_errors=True)
