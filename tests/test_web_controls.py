"""Offline tests for the generic Reset and dark-theme exposure checks of tandem:web_check."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tandem_mcp import web_check  # noqa: E402

PAGE = '''<!doctype html><html><body style="margin:0;background:#000">
<canvas id="c" width="640" height="400"></canvas>
<button id="p">Pause</button><button id="r">Reset</button>
<script>
const c = document.getElementById('c'), ctx = c.getContext('2d');
let running = true, t = 0;
document.getElementById('p').onclick = () => { running = !running; };
document.getElementById('r').onclick = () => { t = 0; RESET_EXTRA };
function frame() {
  if (running) t += 1;
  ctx.fillStyle = '#05070f'; ctx.fillRect(0, 0, 640, 400);
  ctx.fillStyle = 'FILL'; ctx.fillRect(SIZE_X, SIZE_Y, SIZE_W, SIZE_H);
  ctx.fillStyle = '#0ff'; ctx.fillRect((t * 7) % 600, 20, 20, 20);
  requestAnimationFrame(frame);
}
frame();
</script></body></html>'''


def page(reset_extra='', fill='#123', box=(200, 150, 40, 40)):
    x, y, w, h = box
    return (PAGE.replace('RESET_EXTRA', reset_extra).replace('FILL', fill)
            .replace('SIZE_X', str(x)).replace('SIZE_Y', str(y)).replace('SIZE_W', str(w)).replace('SIZE_H', str(h)))


def run(html, goal='neon animated canvas demo with Pause and Reset buttons', constraints=None):
    ws = Path(tempfile.mkdtemp(prefix='tandem_controls_'))
    (ws / 'index.html').write_text(html, encoding='utf-8')
    spec = web_check.spec_for(goal, ['index.html'], constraints)
    return web_check.run(ws, spec, timeout_s=60)


checks = 0


def ok(cond, msg):
    global checks
    assert cond, msg
    checks += 1


if web_check.find_chromium() is None:
    print('test_web_controls: SKIP (no Chromium)')
    raise SystemExit(0)

rc, out = run(page(reset_extra='running = true;'))
ok(rc == 0 and 'reset=passed' in out and 'exposure=passed' in out, f'good page should pass: {rc} {out}')

rc, out = run(page())
ok(rc == 1 and 'Reset must restore the initial running state' in out, f'frozen reset should fail: {rc} {out}')

rc, out = run(page(), constraints=['Reset clears the time and keeps the paused state.'])
ok(rc == 0 and 'reset=skipped' in out, f'contract opt-out should skip reset check: {rc} {out}')

rc, out = run(page(reset_extra='running = true;', fill='#fff', box=(120, 80, 400, 240)))
ok(rc == 1 and 'near-white' in out, f'overexposed dark page should fail: {rc} {out}')

rc, out = run(page(reset_extra='running = true;', fill='#fff', box=(120, 80, 400, 240)),
              goal='light pastel animated canvas with Pause and Reset buttons')
ok(rc == 0 and 'exposure=skipped' in out, f'light theme must not be judged on exposure: {rc} {out}')

print(f'test_web_controls: {checks} checks, 0 failures')
