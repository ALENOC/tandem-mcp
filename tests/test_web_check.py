"""Offline tests for tandem_mcp.web_check integration into agent.Task & repair loop."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.test_host_runner import SlowFake  # noqa: E402
from tandem_mcp import agent, engine, sandbox, store, web_check  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix='tandem_webcheck_test_'))
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
    portal_run = ROOT / 'tests/fixtures/portal_web_check'
    ws_direct = portal_run / 'direct'
    ws_tandem = portal_run / 'tandem'
    spec = web_check.spec_for(
        '3D neon portal web demo with orbiting crystals and animation',
        ['index.html', 'scene.js', 'engine3d.js', 'app.js'],
    )
    ok(spec is not None and spec['require_animation'] is True, f'bad spec: {spec}')

    # 1. Historical direct portal runs with 0 JS errors and an animated canvas; it draws only a few frames per
    #    second (a glow with shadowBlur on every shape), which the frame rate check reports with its cause
    if ws_direct.is_dir():
        rc_d, out_d = web_check.run(ws_direct, spec, perf='warn')
        ok(rc_d == 0 and '0 JS errors' in out_d and 'animated=True' in out_d, f'direct failed: {rc_d} {out_d}')
        info_d = {}
        rc_s, out_s = web_check.run(ws_direct, spec, info=info_d)
        if (info_d.get('perf') or {}).get('fps', 60) < web_check.min_fps():
            ok(rc_s == 1 and info_d['perf_failed'] and 'frame rate:' in out_s and 'with shadowBlur turned off' in out_s,
               f'slow page must fail on its frame rate with the measured cause: {rc_s} {out_s}')

    # 2. Historical Tandem portal fails web_check with TypeError at scene.js:293:31
    if ws_tandem.is_dir():
        rc_t, out_t = web_check.run(ws_tandem, spec)
        ok(rc_t == 1 and 'this.grid.lines is not iterable' in out_t and 'scene.js:293' in out_t,
           f'tandem historical expected TypeError at scene.js:293, got: {rc_t} {out_t}')

    # 3. Missing browser returns exit 2 (not_evaluated) and prevents verified in agent.Task
    old_chrome = os.environ.get('TANDEM_CHROME')
    try:
        os.environ['TANDEM_CHROME'] = '/nonexistent/chromium-missing'
        proj_missing = tmp / 'proj_missing'
        proj_missing.mkdir()
        (proj_missing / 'index.html').write_text('<!doctype html><canvas id="c" width="200" height="200"></canvas><script>requestAnimationFrame(()=>{})</script>', encoding='utf-8')
        fake = SlowFake(delay_s=0.02)
        engine.connect(url=fake.url)
        fake.script = [
            ('replace_in_file', {'path': 'index.html', 'old': 'width="200"', 'new': 'width="300"'}),
            ('finish', {'summary': 'updated canvas width'}),
            ('finish', {'summary': 'still done'}),
        ]
        (store.JOBS / 'job-missing-chrome').mkdir(parents=True, exist_ok=True)
        t_miss = agent.Task(
            'job-missing-chrome', store.JOBS / 'job-missing-chrome',
            'Create index.html with animated canvas',
            sandbox.Workspace(str(proj_missing), ['index.html'], [], []),
            verify=['test -f index.html'], max_steps=10, max_repairs=1, baseline=False,
        )
        state_miss = t_miss.run()
        ok(state_miss in ('checks_failed', 'not_evaluated'), f'missing browser must prevent verified, got {state_miss}')
        jdata = store.read_job('job-missing-chrome') or {}
        ok(any(c['command'] == 'tandem:web_check' and c['exit'] == 2 and 'not_evaluated' in c['tail']
               for c in (jdata.get('checks') or [])), f'expected not_evaluated check, got {jdata.get("checks")}')
    finally:
        if old_chrome is None:
            os.environ.pop('TANDEM_CHROME', None)
        else:
            os.environ['TANDEM_CHROME'] = old_chrome

    # 4. Repair loop catches runtime exception in Chromium and passes once fixed
    proj_fix = tmp / 'proj_fix'
    proj_fix.mkdir()
    (proj_fix / 'index.html').write_text(
        '<!doctype html><canvas id="c" width="200" height="200"></canvas>'
        '<script>const ctx=c.getContext("2d");let x=0;'
        'function loop(){brokenObj.missingMethod();x=(x+5)%200;ctx.clearRect(0,0,200,200);ctx.fillStyle="#0ff";ctx.fillRect(x,50,20,20);requestAnimationFrame(loop);}loop();</script>',
        encoding='utf-8',
    )
    fake_fix = SlowFake(delay_s=0.02)
    engine.connect(url=fake_fix.url)
    fake_fix.script = [
        ('finish', {'summary': 'initial check'}),
        ('replace_in_file', {'path': 'index.html', 'old': 'brokenObj.missingMethod();', 'new': ''}),
        ('finish', {'summary': 'removed broken call'}),
    ]
    (store.JOBS / 'job-web-repair').mkdir(parents=True, exist_ok=True)
    t_fix = agent.Task(
        'job-web-repair', store.JOBS / 'job-web-repair',
        'Fix animated canvas in index.html so it runs with 0 JS errors',
        sandbox.Workspace(str(proj_fix), ['index.html'], [], []),
        verify=['test -f index.html'], max_steps=10, max_repairs=2, baseline=True,
    )
    state_fix = t_fix.run()
    ok(state_fix == 'verified' and t_fix.repairs == 1, f'expected verified after 1 repair, got {state_fix} repairs={t_fix.repairs}')

    # 5. Regression: allow_run=[] hides `run` tool, advertises auto-checks, and guides any fallback run() without retry loops
    proj_norun = tmp / 'proj_norun'
    proj_norun.mkdir()
    ws_norun = sandbox.Workspace(str(proj_norun), ['index.html'], allow_run=[])
    (store.JOBS / 'job-norun').mkdir(parents=True, exist_ok=True)
    fake_nr = SlowFake(delay_s=0.02)
    engine.connect(url=fake_nr.url)
    fake_nr.script = [
        ('run', {'command': 'node --check index.html'}),
        ('write_file', {
            'path': 'index.html',
            'content': '<!doctype html><canvas id="c" width="200" height="200"></canvas><script>const ctx=c.getContext("2d");let x=0;function f(){ctx.clearRect(0,0,200,200);x=(x+5)%200;ctx.fillStyle="#0ff";ctx.fillRect(x,20,20,20);requestAnimationFrame(f);}f();</script>',
        }),
        ('finish', {'summary': 'created animated index.html'}),
    ]
    t_norun = agent.Task(
        'job-norun', store.JOBS / 'job-norun',
        'Create index.html with animated canvas',
        ws_norun,
        verify=['test -f index.html'], max_steps=10, max_repairs=1, baseline=False,
    )
    opening_msgs = t_norun.opening()
    user_open = opening_msgs[1]['content']
    ok('Commands you may run via run(): NONE' in user_open, f'missing NONE guidance: {user_open}')
    ok('tandem:web_check' in user_open and 'test -f index.html' in user_open, f'missing auto-checks list: {user_open}')

    seen_tool_names = []
    orig_chat = engine.chat
    def _spy_chat(messages, **kwargs):
        if kwargs.get('tools') is not None:
            seen_tool_names.append([t['function']['name'] for t in kwargs['tools']])
        return orig_chat(messages, **kwargs)

    engine.chat = _spy_chat
    try:
        state_nr = t_norun.loop(opening_msgs)
    finally:
        engine.chat = orig_chat
    ok(state_nr == 'verified', f'expected verified, got {state_nr}')
    ok(seen_tool_names and 'run' not in seen_tool_names[0], f'run tool must be omitted when allow_run=[]: {seen_tool_names}')
    j_nr = store.read_job('job-norun') or {}
    ok(any(c['command'] == 'tandem:web_check' and c['exit'] == 0 for c in (j_nr.get('checks') or [])),
       f'expected tandem:web_check executed on finish: {j_nr.get("checks")}')
    log_nr = store.read_json(store.JOBS / 'job-norun' / 'log.json', []) or []
    run_rows = [r for r in log_nr if r.get('tool') == 'run']
    ok(len(run_rows) == 1 and 'Do NOT retry run()' in str(run_rows[0].get('result')),
       f'expected single guided refusal, got {run_rows}')

    # 6. Error snippet extraction around cited file:line
    (proj_norun / 'scene.js').write_text('const a = 1;\nconst b = 2;\nfor (const x of bad.lines) {}\nconst c = 3;\n', encoding='utf-8')
    snips = t_norun._error_context_snippets([{'tail': 'runtime exception: TypeError at scene.js:3:17'}])
    ok(len(snips) == 1 and '3| for (const x of bad.lines)' in snips[0], f'bad snippet: {snips}')

    # 8. Start-paused canvas with Play button should pass; inert Play with static canvas must still fail
    proj_paused = tmp / 'proj_paused'
    proj_paused.mkdir()
    (proj_paused / 'index.html').write_text(
        '<!doctype html><button id="play">Play</button><canvas id="c" width="200" height="200"></canvas>'
        '<script>const ctx=c.getContext("2d");let run=false,x=0;'
        'play.onclick=()=>{run=!run;};'
        'function f(){if(run){ctx.clearRect(0,0,200,200);x=(x+7)%200;ctx.fillStyle="#0ff";ctx.fillRect(x,20,20,20);}requestAnimationFrame(f);}f();</script>',
        encoding='utf-8',
    )
    rc_p, out_p = web_check.run(proj_paused, {'preferred_entry': 'index.html', 'require_animation': True}, timeout_s=20)
    ok(rc_p == 0, f'start-paused canvas with Play button should pass, got rc={rc_p}: {out_p}')

    proj_inert = tmp / 'proj_inert'
    proj_inert.mkdir()
    (proj_inert / 'index.html').write_text(
        '<!doctype html><button id="play">Play</button><canvas id="c" width="200" height="200"></canvas>'
        '<script>const ctx=c.getContext("2d");ctx.fillStyle="#0ff";ctx.fillRect(10,10,20,20);</script>',
        encoding='utf-8',
    )
    rc_i, out_i = web_check.run(proj_inert, {'preferred_entry': 'index.html', 'require_animation': True}, timeout_s=20)
    ok(rc_i == 1, f'static canvas with inert Play button must fail, got rc={rc_i}: {out_i}')

    # 9. Frame rate: a page whose frames take 45 ms each (a busy loop: the same on every machine) fails with the
    #    measured rate; in warn mode it passes and says so; a fast page passes and reports its rate
    anim = {'preferred_entry': 'index.html', 'require_animation': True}

    def page(name, work_ms, readout=''):
        d = tmp / name
        d.mkdir()
        (d / 'index.html').write_text(
            '<!doctype html><body style="margin:0;background:#000"><canvas id="c" width="300" height="150"></canvas>'
            f'<div id="hud">{readout}</div>'
            '<script>const ctx=c.getContext("2d");let x=0;'
            f'function f(){{const t=performance.now();while(performance.now()-t<{work_ms}){{}}'
            'ctx.clearRect(0,0,300,150);x=(x+3)%300;ctx.fillStyle="#0ff";ctx.fillRect(x,50,20,20);requestAnimationFrame(f);}'
            'requestAnimationFrame(f);</script></body>', encoding='utf-8')
        return d

    slow_page = page('proj_slow', 45)
    info_s = {}
    rc_s, out_s = web_check.run(slow_page, anim, timeout_s=40, info=info_s)
    fps_s = (info_s.get('perf') or {}).get('fps')
    ok(rc_s == 1 and info_s.get('perf_failed') and fps_s is not None and fps_s < 30 and 'frame rate:' in out_s
       and 'Keep the same look' in out_s, f'slow page must fail on its frame rate: {rc_s} {info_s} {out_s}')
    rc_w, out_w = web_check.run(slow_page, anim, timeout_s=40, perf='warn')
    ok(rc_w == 0 and 'not enforced any more' in out_w, f'warn mode reports the frame rate without failing: {rc_w} {out_w}')
    info_f = {}
    rc_f, out_f = web_check.run(page('proj_fast', 0, 'FPS: <span id="fps">60</span>'), anim, timeout_s=40, info=info_f)
    ok(rc_f == 0 and not info_f.get('perf_failed') and 'fps=' in out_f and (info_f['perf'].get('shown') == 60),
       f'fast page passes and its readout is read: {rc_f} {info_f} {out_f}')
    rc_r, out_r = web_check.run(page('proj_readout', 0, 'Speed 1.0x | FPS: 7'), anim, timeout_s=40)
    ok(rc_r == 1 and 'the FPS readout shows 7' in out_r, f'a readout far from the measured rate fails: {rc_r} {out_r}')
    rc_n, out_n = web_check.run(page('proj_label', 0, '<span>60 FPS</span> <span>1.0x</span>'), anim, timeout_s=40)
    ok(rc_n == 0, f'the number next to the word is the readout, not the one after it: {rc_n} {out_n}')
    os.environ['TANDEM_WEB_MIN_FPS'] = '0'
    try:
        rc_o, out_o = web_check.run(slow_page, anim, timeout_s=40)
        ok(rc_o == 0 and 'fps=' not in out_o, f'TANDEM_WEB_MIN_FPS=0 turns the frame rate check off: {rc_o} {out_o}')
    finally:
        os.environ.pop('TANDEM_WEB_MIN_FPS', None)

    # 10. In a job the frame rate goes back to the executor twice; then it is reported, not enforced, and the
    #     receipt says so in one line
    from tandem_mcp import server  # noqa: E402
    fake_p = SlowFake(delay_s=0.01)
    engine.connect(url=fake_p.url)
    fake_p.script = [('finish', {'summary': 'done'})] * 3
    (store.JOBS / 'job-slow-page').mkdir(parents=True, exist_ok=True)
    t_slow = agent.Task('job-slow-page', store.JOBS / 'job-slow-page', 'Make the canvas animation in index.html smooth',
                        sandbox.Workspace(str(page('proj_slow_job', 45)), ['index.html'], [], []),
                        verify=['test -f index.html'], max_steps=8, max_repairs=3, baseline=False)
    state_p = t_slow.run()
    ok(state_p == 'verified' and t_slow.repairs == 2 and t_slow.perf_strikes == 2,
       f'two frame rate repairs, then accepted: {state_p} repairs={t_slow.repairs} strikes={t_slow.perf_strikes}')
    receipt = server._auto_receipt('job-slow-page')
    ok('ACCEPTED' in receipt and 'Note: the page draws' in receipt, f'the receipt names the frame rate: {receipt}')

    print(f'{checks} checks, 0 failures')
finally:
    shutil.rmtree(tmp, ignore_errors=True)
