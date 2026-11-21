"""Offline tests for tandem:ui_test (declarative UI acceptance tests) and the strict contract rule for pages."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tandem_mcp import server, ui_test, web_check  # noqa: E402

checks = 0


def ok(cond, msg):
    global checks
    assert cond, msg
    checks += 1


def refused(fn):
    try:
        fn()
    except ValueError as exc:
        return str(exc)
    return ''


# parsing
ok(ui_test.is_ui_test('tandem:ui_test {"steps":[{"exists":"#c"}]}'), 'prefix detected')
ok(not ui_test.is_ui_test('node --check app.js'), 'shell check is not a ui_test')
ok('JSON object' in refused(lambda: ui_test.parse('tandem:ui_test {bad')), 'malformed JSON refused')
ok('at least one step' in refused(lambda: ui_test.parse('tandem:ui_test {"steps":[]}')), 'empty scenario refused')
ok('assert something' in refused(lambda: ui_test.parse('tandem:ui_test {"steps":[{"click":"#a"}]}')),
   'action-only scenario refused')

# strict contract: a page checked only by syntax is refused, a ui_test is accepted
goal = 'Build index.html with a canvas #c animation, a Pause button #pause and a Reset button #reset'
cons = ['index.html has <canvas id="c"> filling the viewport']
msg = refused(lambda: server._validate_contract(goal, cons, ['node --check app.js'], ['index.html', 'app.js']))
ok('tandem:ui_test' in msg, f'syntax-only page contract must be refused: {msg!r}')
good = 'tandem:ui_test {"steps":[{"expect":"moving"},{"click":"#pause"},{"expect":"static"}]}'
ok(refused(lambda: server._validate_contract(goal, cons, [good], ['index.html'])) == '', 'ui_test contract accepted')
ok(refused(lambda: server._validate_contract(goal, cons, ['node check_page.js'], ['index.html'])) == '',
   'a script that runs the page is still accepted')
ok('contract refused' in refused(lambda: server._validate_contract(goal, cons, ['tandem:ui_test {"steps":[{"wait":5}]}'],
                                                                     ['index.html'])), 'bad ui_test refused in contract')

if web_check.find_chromium() is None:
    print(f'test_ui_test: {checks} checks, 0 failures (browser part skipped)')
    raise SystemExit(0)

PAGE = '''<!doctype html><html><body style="margin:0;background:#0b1020">
<canvas id="c" width="400" height="300"></canvas>
<button id="pause">Pause</button><button id="reset">Reset</button><span id="fps">60 FPS</span>
<input id="speed" type="range" min="0" max="3" step="0.1" value="1"><span id="sv">1.0x</span>
<script>
const c = document.getElementById('c'), ctx = c.getContext('2d');
let running = true, t = 0;
document.getElementById('pause').onclick = () => { running = !running; };
document.getElementById('reset').onclick = () => { t = 0; RESET };
document.getElementById('speed').oninput = (e) => { document.getElementById('sv').textContent = Number(e.target.value).toFixed(1) + 'x'; };
(function frame() {
  if (running) t++;
  ctx.fillStyle = '#0b1020'; ctx.fillRect(0, 0, 400, 300);
  ctx.fillStyle = '#00ffff'; ctx.fillRect((t * 5) % 380, 100, 20, 20);
  requestAnimationFrame(frame);
})();
</script></body></html>'''

SCENARIO = ('tandem:ui_test {"steps":[{"expect":"moving"},{"click":"#pause"},{"expect":"static"},'
            '{"click":"text:^reset$"},{"expect":"moving"},{"text":"#fps","match":"^\\\\d+ FPS"},'
            '{"input":"#speed","value":"3"},{"text":"#sv","match":"^3\\\\.0x$"},'
            '{"color":"#0b1020","min":0.3},{"color":"#ffffff","max":0.05}]}')


def run_page(html, scenario=SCENARIO):
    ws = Path(tempfile.mkdtemp(prefix='tandem_uitest_'))
    (ws / 'index.html').write_text(html, encoding='utf-8')
    return ui_test.run(scenario, ws)


rc, out = run_page(PAGE.replace('RESET', 'running = true;'))
ok(rc == 0 and 'passed 10 steps' in out, f'correct page passes: {rc} {out}')

rc, out = run_page(PAGE.replace('RESET', ''))
ok(rc == 1 and 'BAD step 5' in out and 'expected moving' in out, f'frozen Reset is reported on its step: {rc} {out}')

rc, out = run_page(PAGE.replace('RESET', 'running = true;').replace("'#0b1020'; ctx.fillRect(0, 0", "'#ffffff'; ctx.fillRect(0, 0"))
ok(rc == 1 and 'near #ffffff' in out, f'overexposed page fails the color step: {rc} {out}')

rc, out = run_page(PAGE.replace('RESET', 'running = true; undefinedFn();'))
ok(rc == 1 and 'js error' in out, f'JS error fails the test: {rc} {out}')

ws = Path(tempfile.mkdtemp(prefix='tandem_uitest_empty_'))
rc, out = ui_test.run(SCENARIO, ws)
ok(rc == 1 and 'missing entry point' in out, f'missing page fails (baseline must fail before the work): {rc} {out}')

# repair loop: the executor sees the failing step, fixes it, and the job verifies
from tests.test_host_runner import SlowFake  # noqa: E402
from tandem_mcp import agent, engine, sandbox, store  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix='tandem_uitest_loop_'))
store.DATA = tmp / 'data'
store.JOBS = store.DATA / 'jobs'
store.CACHE = store.DATA / 'cache'
store.LEDGER = store.DATA / 'ledger.jsonl'
store.LESSONS = store.DATA / 'lessons.jsonl'
store.MODELS = store.DATA / 'models.json'
store.init()
proj = tmp / 'proj'
proj.mkdir()
(proj / 'index.html').write_text(PAGE.replace('RESET', ''), encoding='utf-8')
fake = SlowFake(delay_s=0.02)
engine.connect(url=fake.url)
fake.script = [
    ('finish', {'summary': 'done'}),
    ('replace_in_file', {'path': 'index.html', 'old': 't = 0;  };', 'new': 't = 0; running = true; };'}),
    ('finish', {'summary': 'Reset now resumes'}),
]
(store.JOBS / 'job-ui').mkdir(parents=True, exist_ok=True)
task = agent.Task('job-ui', store.JOBS / 'job-ui', 'Fix Reset in index.html so it resumes the animation',
                  sandbox.Workspace(str(proj), ['index.html'], [], []),
                  verify=[SCENARIO], max_steps=10, max_repairs=2, baseline=True)
state = task.run()
ok(state == 'verified' and task.repairs == 1, f'expected verified after 1 repair, got {state} repairs={task.repairs}')
ok('index.html' not in task.ws.protected, 'the page named by the scenario stays writable')
jd = store.read_job('job-ui') or {}
ok(any(c['command'].startswith('tandem:ui_test') and c['exit'] == 0 for c in jd.get('checks') or []),
   f'ui_test recorded as passed: {jd.get("checks")}')

print(f'test_ui_test: {checks} checks, 0 failures')
