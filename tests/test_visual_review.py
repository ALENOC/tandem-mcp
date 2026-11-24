"""Offline tests for visual reference images, live screenshot capture, local VLM review, and MCP ImageContent receipts."""
import asyncio
import base64
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

tmp = Path(tempfile.mkdtemp(prefix='tandem_visual_test_'))
os.environ['TANDEM_HOME'] = str(tmp / 'data')
os.environ['TANDEM_PROFILE'] = 'autonomous'
os.environ['TANDEM_MAX_REPAIRS'] = '4'
os.environ['TANDEM_JOB_SECONDS'] = '120'

from fake_server import Fake  # noqa: E402
from mcp.types import ImageContent, TextContent  # noqa: E402
from tandem_mcp import agent, engine, sandbox, server, store, visual_review, web_check  # noqa: E402

store.init()

# Minimal valid 1x1 PNG (67 bytes)
TINY_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
)
# Minimal JPEG header+EOI for non-browser unit checks
TINY_JPG = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9'

checks = 0


def ok(cond, msg):
    global checks
    assert cond, msg
    checks += 1


try:
    # 1. AUTONOMOUS_GUIDE stays under 1100 chars and includes screenshot review rule
    ok(len(server.AUTONOMOUS_GUIDE) < 1100 and 'ACCEPTED is final' in server.AUTONOMOUS_GUIDE
       and 'reference_image' in server.AUTONOMOUS_GUIDE and 'screenshot' in server.AUTONOMOUS_GUIDE,
       f'bad AUTONOMOUS_GUIDE len={len(server.AUTONOMOUS_GUIDE)}')

    # 2. reference_image validation and copy into job folder (including idempotent resume)
    ref_src = tmp / 'mockup.png'
    ref_src.write_bytes(TINY_PNG)
    job_dir = tmp / 'job_ref'
    stored = visual_review.prepare_reference(str(ref_src), job_dir)
    ok(Path(stored).is_file() and Path(stored).parent == job_dir.resolve() and Path(stored).read_bytes() == TINY_PNG,
       f'reference copied into job dir: {stored}')
    # Calling prepare_reference on the already-copied file (resume) must not raise SameFileError
    stored2 = visual_review.prepare_reference(stored, job_dir)
    ok(stored2 == stored, f'idempotent reference copy: {stored2}')

    for bad_name, bad_content in [('bad.txt', b'hello'), ('empty.png', b'')]:
        p = tmp / bad_name
        p.write_bytes(bad_content)
        raised = False
        try:
            visual_review.prepare_reference(str(p), job_dir)
        except ValueError:
            raised = True
        ok(raised, f'invalid reference {bad_name} must raise ValueError')

    raised_missing = False
    try:
        visual_review.prepare_reference(str(tmp / 'nope.png'), job_dir)
    except ValueError:
        raised_missing = True
    ok(raised_missing, 'missing reference_image must raise ValueError')

    # 3. select_vision_model respects TANDEM_VISUAL_REVIEW, TANDEM_MODEL_VISION, and server VLM metadata
    orig_models = engine.models
    try:
        engine.models = lambda refresh=False: [
            {'id': 'coder-27b', 'loaded': True, 'type': 'llm', 'vision': False, 'context': 65536},
            {'id': 'qwen-vl-7b', 'loaded': True, 'type': 'vlm', 'vision': True, 'context': 32768},
        ]
        os.environ.pop('TANDEM_MODEL_VISION', None)
        os.environ['TANDEM_VISUAL_REVIEW'] = 'auto'
        ok(visual_review.select_vision_model('coder-27b') == 'qwen-vl-7b', 'auto picks loaded VLM on server')

        os.environ['TANDEM_MODEL_VISION'] = 'custom-vlm'
        ok(visual_review.select_vision_model('coder-27b') == 'custom-vlm', 'TANDEM_MODEL_VISION overrides discovery')

        os.environ['TANDEM_VISUAL_REVIEW'] = 'off'
        ok(visual_review.select_vision_model('coder-27b') is None, 'off disables vision model selection')

        os.environ.pop('TANDEM_MODEL_VISION', None)
        os.environ['TANDEM_VISUAL_REVIEW'] = 'auto'
        engine.models = lambda refresh=False: [
            {'id': 'coder-27b', 'loaded': True, 'type': 'llm', 'vision': False, 'context': 65536},
        ]
        ok(visual_review.select_vision_model('coder-27b') is None, 'text-only server skips VLM in auto mode (0 calls)')

        os.environ['TANDEM_VISUAL_REVIEW'] = 'on'
        ok(visual_review.select_vision_model('coder-27b') == 'coder-27b', 'forced on falls back to executor model')
    finally:
        engine.models = orig_models
        os.environ.pop('TANDEM_MODEL_VISION', None)
        os.environ.pop('TANDEM_VISUAL_REVIEW', None)

    # 4. Graceful degradation when server rejects image_url input
    fake_reject = Fake(tools=True, schema=True)
    engine.connect(url=fake_reject.url)
    fake_reject.policy = lambda body: {'status': 400, 'error': {'message': 'model does not support vision / image_url'}}
    shot_file = tmp / 'shot.jpg'
    shot_file.write_bytes(TINY_JPG)
    res_rej = visual_review.review(shot_file, 'Build neon portal', model='fake-model')
    ok(res_rej['status'] == 'skipped' and 'does not support' in res_rej['reason'], f'vision reject degrades: {res_rej}')
    caps_after = store.model_caps(engine._caps_key('fake-model')) or {}
    ok(caps_after.get('vision') is False, f'vision=False remembered in caps: {caps_after}')
    fake_reject.close()

    # 5. Live screenshot capture via web_check.run (runs if Chromium is available)
    if web_check.find_chromium() and shutil.which('node'):
        proj_shot = tmp / 'proj_shot'
        proj_shot.mkdir()
        (proj_shot / 'index.html').write_text(
            '<!doctype html><body style="margin:0;background:#090d1a"><canvas id="c" width="600" height="400"></canvas>'
            '<script>const ctx=c.getContext("2d");let x=0;function f(){ctx.fillStyle="#090d1a";ctx.fillRect(0,0,600,400);'
            'x=(x+4)%560;ctx.fillStyle="#00ffff";ctx.fillRect(x,150,40,40);requestAnimationFrame(f);}f();</script></body>',
            encoding='utf-8',
        )
        shot_out = tmp / 'captured.jpg'
        info = {}
        rc, out = web_check.run(proj_shot, {'preferred_entry': 'index.html', 'require_animation': True},
                                timeout_s=30, perf='warn', info=info, screenshot_path=shot_out)
        ok(rc == 0 and shot_out.is_file() and shot_out.read_bytes()[:2] == b'\xff\xd8',
           f'web_check captured JPEG screenshot: rc={rc} info={info} out={out}')
        ok(info.get('screenshot') == str(shot_out.resolve()), f'info reports screenshot path: {info}')

    # 6. Full end-to-end visual review repair loop (reference image + live screenshot + stateless VLM + MCP ImageContent)
    fake = Fake(tools=True, schema=True)
    engine.connect(url=fake.url)

    proj = tmp / 'proj_portal'
    proj.mkdir()
    (proj / 'index.html').write_text('<!doctype html><canvas id="c"></canvas>\n', encoding='utf-8')

    vlm_calls = []
    coding_calls = []

    def policy(body):
        msgs = body['messages']
        # Identify stateless visual_review call by multimodal list content
        last_content = msgs[-1].get('content')
        if isinstance(last_content, list):
            vlm_calls.append(body)
            if len(vlm_calls) == 1:
                return {'content': json.dumps({
                    'passed': False,
                    'summary': 'Grid draws only horizontal lines and portal blocks lack neon edges.',
                    'issues': ['Missing Z-axis grid lines', 'No cyan wireframe stroke on portal pillars'],
                    'fixes': ['Draw both X and Z grid lines in drawGrid()', 'Add ctx.strokeStyle="#00ffff" outline on pillars'],
                })}
            return {'content': json.dumps({
                'passed': True,
                'summary': 'Neon wireframe edges and full X/Z grid match reference.',
                'issues': [],
                'fixes': [],
            })}
        coding_calls.append(body)
        if len(coding_calls) == 1:
            return ('write_file', {
                'path': 'index.html',
                'content': '<!doctype html><canvas id="c"></canvas><script>/* v1 horizontal grid only */</script>\n',
            })
        if len(coding_calls) == 2:
            return ('finish', {'summary': 'built portal v1', 'evidence': [{'constraint': 1, 'path': 'index.html', 'quote': '<canvas id="c">'}]})
        if len(coding_calls) == 3:
            return ('replace_in_file', {
                'path': 'index.html',
                'old': '/* v1 horizontal grid only */',
                'new': '/* v2 full X+Z grid and #00ffff neon wireframe edges */',
            })
        return ('finish', {'summary': 'added neon edges and full grid',
                           'evidence': [{'constraint': 1, 'path': 'index.html', 'quote': '<canvas id="c">'}]})

    fake.policy = policy

    # Stub web_check.run and ui_test.run so the loop test runs deterministically even without Chromium
    from tandem_mcp import ui_test  # noqa: E402
    orig_wc_run = web_check.run
    orig_ui_run = ui_test.run
    def stub_wc_run(ws_root, spec, timeout_s=45.0, perf='fail', info=None, screenshot_path=None):
        html = (Path(ws_root) / 'index.html').read_text(encoding='utf-8')
        if 'v1' not in html and 'v2' not in html:
            return 1, 'FAIL: canvas pixels remained static'
        if screenshot_path:
            Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
            Path(screenshot_path).write_bytes(TINY_JPG)
            if info is not None:
                info['screenshot'] = str(Path(screenshot_path).resolve())
        if info is not None:
            info['perf'] = {'status': 'passed', 'fps': 60}
            info['perf_failed'] = False
        return 0, 'OK: browser verified index.html with 0 JS errors (canvas animated=True, fps=60).'

    def stub_ui_run(command, ws_root, timeout_s=120.0):
        html = (Path(ws_root) / 'index.html').read_text(encoding='utf-8')
        if 'v1' in html or 'v2' in html:
            return 0, 'OK 1/1 steps passed'
        return 1, 'BAD step 1: portal not rendered yet'

    web_check.run = stub_wc_run
    ui_test.run = stub_ui_run
    os.environ['TANDEM_MODEL_VISION'] = 'local-vlm'
    os.environ['TANDEM_VISUAL_REVIEW'] = 'auto'
    os.environ['TANDEM_RECEIPT_SCREENSHOT'] = '1'
    try:
        ui_cmd = 'tandem:ui_test {"steps":[{"exists":"#c"}]}'
        res = asyncio.run(server.auto_delegate_tool(
            goal='Build an animated neon 3D portal in index.html matching the reference',
            workspace=str(proj),
            write_globs=['index.html'],
            verify_commands=[ui_cmd],
            constraints=['index.html contains <canvas id="c">'],
            reference_image=str(ref_src),
        ))
        ok(isinstance(res, list) and len(res) == 2, f'MCP receipt attaches screenshot: {type(res)} {res}')
        ok(isinstance(res[0], TextContent) and isinstance(res[1], ImageContent), f'content types: {res}')
        ok('ACCEPTED' in res[0].text and 'Visual review: passed locally.' in res[0].text and 'Screenshot attached.' in res[0].text,
           f'receipt text: {res[0].text}')
        ok(getattr(res[1], 'mime_type', getattr(res[1], 'mimeType', '')) == 'image/jpeg'
           and base64.b64decode(res[1].data) == TINY_JPG, 'attached JPEG bytes match')

        # Verify stateless VLM received BOTH reference image and live screenshot (2 image_url parts)
        ok(len(vlm_calls) == 2, f'expected 2 VLM review calls (fail then pass), got {len(vlm_calls)}')
        for call_body in vlm_calls:
            parts = call_body['messages'][-1]['content']
            img_parts = [p for p in parts if isinstance(p, dict) and p.get('type') == 'image_url']
            ok(len(img_parts) == 2 and img_parts[0]['image_url']['url'].startswith('data:image/png;base64,')
               and img_parts[1]['image_url']['url'].startswith('data:image/jpeg;base64,'),
               f'VLM must see [reference PNG, screenshot JPEG]: {len(img_parts)}')

        # Verify main coding conversation stayed text-only (no image_url bloat in coding history -> KV cache intact)
        for cbody in coding_calls:
            for m in cbody['messages']:
                ok(not isinstance(m.get('content'), list), 'coding conversation must stay text-only for KV prefix cache')
        ok('Missing Z-axis grid lines' in str(coding_calls[2]['messages'][-1]['content']),
           'coding executor received concrete visual critique in repair turn')
        ok('v2 full X+Z grid' in (proj / 'index.html').read_text(encoding='utf-8'), 'visual fix applied on disk')

        # 7. TANDEM_RECEIPT_SCREENSHOT=0 suppresses ImageContent and returns plain str
        job_id = res[0].text.split()[1].rstrip(':')
        os.environ['TANDEM_RECEIPT_SCREENSHOT'] = '0'
        plain = asyncio.run(server.auto_job_status_tool(job_id))
        ok(isinstance(plain, str) and 'ACCEPTED' in plain and 'Screenshot attached.' not in plain,
           f'TANDEM_RECEIPT_SCREENSHOT=0 must return str: {type(plain)} {plain}')

        # 8. Max visual repairs cap prevents infinite visual loops
        os.environ['TANDEM_MAX_VISUAL_REPAIRS'] = '1'
        os.environ['TANDEM_RECEIPT_SCREENSHOT'] = '1'
        proj_cap = tmp / 'proj_cap'
        proj_cap.mkdir()
        (proj_cap / 'index.html').write_text('<!doctype html><canvas id="c"></canvas>\n', encoding='utf-8')
        vlm_always_fail = [0]
        coding_cap = [0]
        def fail_policy(body):
            if isinstance(body['messages'][-1].get('content'), list):
                vlm_always_fail[0] += 1
                return {'content': json.dumps({
                    'passed': False,
                    'summary': 'Still lacks glow',
                    'issues': ['Glow too faint'],
                    'fixes': ['Increase glow alpha'],
                })}
            coding_cap[0] += 1
            if coding_cap[0] == 1:
                return ('write_file', {'path': 'index.html', 'content': '<!doctype html><canvas id="c"></canvas><script>/* v1 */</script>\n'})
            return ('finish', {'summary': 'done', 'evidence': [{'constraint': 1, 'path': 'index.html', 'quote': '<canvas id="c">'}]})
        fake.policy = fail_policy
        res_cap = asyncio.run(server.auto_delegate_tool(
            goal='Build an animated neon 3D portal in index.html',
            workspace=str(proj_cap),
            write_globs=['index.html'],
            verify_commands=[ui_cmd],
            constraints=['index.html contains <canvas id="c">'],
        ))
        ok(isinstance(res_cap, list) and 'ACCEPTED' in res_cap[0].text and 'Visual review note: Still lacks glow' in res_cap[0].text,
           f'capped visual repairs still accept with note: {res_cap}')
        ok(vlm_always_fail[0] == 1, f'TANDEM_MAX_VISUAL_REPAIRS=1 runs at most 1 VLM repair, got {vlm_always_fail[0]}')
    finally:
        web_check.run = orig_wc_run
        ui_test.run = orig_ui_run
        os.environ.pop('TANDEM_MODEL_VISION', None)
        os.environ.pop('TANDEM_VISUAL_REVIEW', None)
        os.environ.pop('TANDEM_RECEIPT_SCREENSHOT', None)
        os.environ.pop('TANDEM_MAX_VISUAL_REPAIRS', None)
        fake.close()

    print(f'test_visual_review: {checks} checks, 0 failures')
finally:
    shutil.rmtree(tmp, ignore_errors=True)
