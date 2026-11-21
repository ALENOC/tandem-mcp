"""Positive, negative, and coverage-honesty controls for compact host_runner receipt."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tandem_mcp import host_runner, store, web_check  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix='tandem_compact_receipt_'))
store.DATA = tmp / 'data'
store.JOBS = store.DATA / 'jobs'
store.CACHE = store.DATA / 'cache'
store.LEDGER = store.DATA / 'ledger.jsonl'
store.LESSONS = store.DATA / 'lessons.jsonl'
store.MODELS = store.DATA / 'models.json'
store.init()

checks = 0


def ok(cond, msg):
    global checks
    assert cond, msg
    checks += 1


try:
    os.environ['TANDEM_COMPACT_RECEIPT'] = '1'

    # 1. Positive control: behavioral/unit verification explicitly covers all constraints
    j_ok = 'job-ok'
    (store.JOBS / j_ok).mkdir(parents=True, exist_ok=True)
    store.write_job(j_ok, {
        'id': j_ok,
        'goal': 'Create parser.py with unit tests',
        'state': 'verified',
        'changes': [['parser.py', 'create', 120, 0]],
        'checks': [{
            'command': 'python3 -m unittest -v test_parser.py',
            'exit': 0,
            'covers_constraints': [1, 2],
            'observed': 'all 12 parser unit tests passed',
        }],
        'constraints': ['c1', 'c2'],
        'evidence': [{'constraint': 1, 'quote': 'x'}, {'constraint': 2, 'quote': 'y'}],
        'unproven': [],
        'require_proof': True,
        'summary': 'Created parser.py and test_parser.py.',
    })
    out_ok = host_runner._format_host_summary(j_ok, 120.5, False)
    ok('FILES_MODIFIED: parser.py (+120 -0)' in out_ok, f'missing files: {out_ok}')
    ok('COVERAGE: complete (2/2 contract requirements verified: #1: c1; #2: c2)' in out_ok, f'expected complete coverage with scope: {out_ok}')
    ok('without re-reading full files' in out_ok, f'missing no-reread hint: {out_ok}')
    ok(len(out_ok) < 700, f'compact receipt too large: {len(out_ok)}')

    # 2. Regression: animated web page with INERT Step passes tandem:web_check smoke test -> NOT complete
    web_ws = tmp / 'web_inert_step'
    web_ws.mkdir()
    (web_ws / 'index.html').write_text(
        '<!doctype html><button id="play">Pause</button><button id="step">Step</button><canvas id="c" width="200" height="200"></canvas>'
        '<script>const ctx=c.getContext("2d");let x=0;'
        'step.onclick=()=>{};'
        'function f(){ctx.clearRect(0,0,200,200);x=(x+5)%200;ctx.fillStyle="#0ff";ctx.fillRect(x,20,20,20);requestAnimationFrame(f);}f();</script>',
        encoding='utf-8',
    )
    wc_rc, _wc_out = web_check.run(web_ws, {'preferred_entry': 'index.html', 'require_animation': True}, timeout_s=20)
    ok(wc_rc == 0, f'smoke test expected exit 0, got {wc_rc}')
    j_web = 'job-web-smoke'
    (store.JOBS / j_web).mkdir(parents=True, exist_ok=True)
    store.write_job(j_web, {
        'id': j_web,
        'goal': 'Create interactive canvas with Play/Pause, Step, and Reset buttons',
        'state': 'verified',
        'changes': [['index.html', 'create', 200, 0]],
        'checks': [{'command': 'tandem:web_check', 'exit': 0, 'tail': 'OK'}],
        'constraints': ['Play/Pause button', 'Step button', 'Reset button'],
        'evidence': [{'constraint': 1, 'quote': 'Pause'}, {'constraint': 2, 'quote': 'Step'}, {'constraint': 3, 'quote': 'Reset'}],
        'unproven': [],
        'require_proof': True,
    })
    out_web = host_runner._format_host_summary(j_web, 90.0, False)
    ok('COVERAGE: complete' not in out_web and 'copertura non determinabile' in out_web, f'smoke test must not claim complete: {out_web}')
    ok('tandem:web_check smoke only' in out_web, f'missing smoke observation: {out_web}')

    # 3. Repro A: Playwright script opens page (exit=0) without exercising control -> NOT complete
    j_pw = 'job-pw-noop'
    (store.JOBS / j_pw).mkdir(parents=True, exist_ok=True)
    store.write_job(j_pw, {
        'id': j_pw,
        'goal': 'Crea index.html con pulsante Reset funzionante',
        'state': 'verified',
        'changes': [['index.html', 'create', 100, 0]],
        'checks': [{'command': 'node check_playwright_open.mjs', 'exit': 0, 'tail': 'page opened ok'}],
        'constraints': ['Reset button restores initial state'],
        'evidence': [{'constraint': 1, 'quote': '<button>Reset</button>'}],
        'unproven': [],
        'require_proof': True,
    })
    out_pw = host_runner._format_host_summary(j_pw, 30.0, False)
    ok('COVERAGE: complete' not in out_pw and 'copertura non determinabile' in out_pw, f'playwright open-only must not claim complete: {out_pw}')

    # 4. Repro B: Italian prompt 'trascina il cursore per cambiare velocità' with smoke test only -> NOT complete
    j_it = 'job-it-slider'
    (store.JOBS / j_it).mkdir(parents=True, exist_ok=True)
    store.write_job(j_it, {
        'id': j_it,
        'goal': 'Crea index.html dove trascina il cursore per cambiare velocità',
        'state': 'verified',
        'changes': [['index.html', 'create', 100, 0]],
        'checks': [{'command': 'tandem:web_check', 'exit': 0, 'tail': 'OK'}],
        'constraints': ['Trascina il cursore per cambiare velocità'],
        'evidence': [{'constraint': 1, 'quote': '<input type="range">'}],
        'unproven': [],
        'require_proof': True,
    })
    out_it = host_runner._format_host_summary(j_it, 30.0, False)
    ok('COVERAGE: complete' not in out_it and 'copertura non determinabile' in out_it, f'Italian prompt must not claim complete: {out_it}')

    # 5. Partial coverage: 2 requirements, valid proof for 1 only
    j_part = 'job-partial-cov'
    (store.JOBS / j_part).mkdir(parents=True, exist_ok=True)
    store.write_job(j_part, {
        'id': j_part,
        'state': 'verified',
        'changes': [['index.html', 'create', 150, 0]],
        'checks': [{'command': 'node check_step.mjs', 'exit': 0, 'covers_constraints': [1], 'observed': 'Step verified'}],
        'constraints': ['Step works', 'Reset works'],
        'evidence': {'1': [{'quote': 'step'}], '2': [{'quote': 'reset'}]},
        'unproven': [],
        'require_proof': True,
    })
    out_part = host_runner._format_host_summary(j_part, 45.0, False)
    ok('COVERAGE: partial (1/2 requirements verified; covered=[1])' in out_part, f'expected partial 1/2: {out_part}')
    ok('MISSING_PROOF: requirements=[2]' in out_part, f'expected missing req 2: {out_part}')

    # 6. No checks executed & skipped check
    j_none = 'job-no-checks'
    (store.JOBS / j_none).mkdir(parents=True, exist_ok=True)
    store.write_job(j_none, {'id': j_none, 'state': 'verified', 'changes': [['a.py', 'create', 10, 0]], 'checks': [], 'constraints': ['c1'], 'unproven': []})
    out_none = host_runner._format_host_summary(j_none, 10.0, False)
    ok('COVERAGE: none (no passing checks executed)' in out_none, f'expected no checks: {out_none}')

    j_skip = 'job-skipped'
    (store.JOBS / j_skip).mkdir(parents=True, exist_ok=True)
    store.write_job(j_skip, {'id': j_skip, 'state': 'verified', 'changes': [['a.py', 'create', 10, 0]], 'checks': [{'command': 'pytest', 'skipped': True}], 'constraints': ['c1'], 'unproven': []})
    out_skip = host_runner._format_host_summary(j_skip, 10.0, False)
    ok('skipped cmd=pytest' in out_skip and 'COVERAGE: none' in out_skip, f'expected skipped surfaced: {out_skip}')

    # 7. Negative controls: failed check (with misleading worker summary 'Verified ...') & unproven constraint
    j_fail = 'job-fail'
    (store.JOBS / j_fail).mkdir(parents=True, exist_ok=True)
    store.write_job(j_fail, {
        'id': j_fail, 'state': 'checks_failed', 'changes': [['index.html', 'create', 120, 0]],
        'checks': [
            {'command': 'tandem:web_check', 'exit': 0, 'observed': 'startup ok'},
            {'command': 'node verify.mjs', 'exit': 1, 'tail': 'Step passed=false'},
        ],
        'constraints': ['Step works', 'Pause works'], 'evidence': {'1': [{'quote': 'x'}], '2': [{'quote': 'y'}]},
        'unproven': [], 'require_proof': True,
        'summary': 'Verified p2 index.html.',
    })
    out_fail = host_runner._format_host_summary(j_fail, 95.0, False)
    ok('COVERAGE: failed_or_incomplete' in out_fail and 'Step passed=false' in out_fail, f'failed check not surfaced: {out_fail}')
    ok('SUMMARY: Verified' not in out_fail and 'WORKER_CLAIM (not server verdict): Verified p2 index.html.' in out_fail, f'worker claim presented as server summary: {out_fail}')
    ok(out_fail.index('VERDICT:') < out_fail.index('WORKER_CLAIM'), f'VERDICT must precede WORKER_CLAIM: {out_fail}')
    ok('tandem:web_check smoke only' in out_fail and 'FAILED_OR_UNVERIFIED_REQUIREMENTS: [1, 2]' in out_fail, f'missing observed or failed reqs: {out_fail}')

    j_unp = 'job-unproven'
    (store.JOBS / j_unp).mkdir(parents=True, exist_ok=True)
    store.write_job(j_unp, {
        'id': j_unp, 'state': 'needs_review', 'changes': [['app.py', 'edit', 10, 2]],
        'checks': [{'command': 'python3 -m unittest', 'exit': 0}], 'constraints': ['c1', 'c2'], 'unproven': [2], 'require_proof': True,
    })
    out_unp = host_runner._format_host_summary(j_unp, 40.0, False)
    ok('COVERAGE: failed_or_incomplete' in out_unp and 'unproven_constraints=[2]' in out_unp, f'unproven not surfaced: {out_unp}')

    print(f'{checks} checks, 0 failures')
finally:
    shutil.rmtree(tmp, ignore_errors=True)
