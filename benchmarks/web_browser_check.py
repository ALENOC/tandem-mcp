"""Shared headless Chromium CDP verification for web artifacts (B03)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

_CDP_SCRIPT = r"""
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';

const [chromeBin, wsDir, kind] = process.argv.slice(1);
const MIME = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.json': 'application/json' };
const VIEWPORT = { width: 1280, height: 720 };

function serveDir(dir) {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      const urlPath = (req.url || '/').split('?')[0];
      const rel = urlPath === '/' ? 'index.html' : urlPath.replace(/^\/+/, '');
      const full = path.resolve(dir, rel);
      if (!full.startsWith(path.resolve(dir)) || !fs.existsSync(full) || fs.statSync(full).isDirectory()) {
        res.writeHead(404); res.end('not found'); return;
      }
      res.writeHead(200, { 'Content-Type': MIME[path.extname(full)] || 'application/octet-stream' });
      fs.createReadStream(full).pipe(res);
    });
    srv.listen(0, '127.0.0.1', () => resolve(srv));
  });
}

const srv = await serveDir(wsDir);
const port = srv.address().port;
const userDir = fs.mkdtempSync(path.join(os.tmpdir(), 'tandem-chrome-'));
const chrome = spawn(chromeBin, [
  '--headless=new', '--no-sandbox', '--disable-gpu',
  `--window-size=${VIEWPORT.width},${VIEWPORT.height}`,
  '--remote-debugging-port=0', `--user-data-dir=${userDir}`,
  `http://127.0.0.1:${port}/index.html`,
], { stdio: ['ignore', 'ignore', 'pipe'] });

const consoleErrors = [];
const exceptions = [];
try {
  const wsUrl = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('DevTools timeout')), 12000);
    let buf = '';
    chrome.stderr.on('data', (chunk) => {
      buf += chunk.toString();
      const m = buf.match(/DevTools listening on (ws:\/\/\S+)/);
      if (m) { clearTimeout(timer); resolve(m[1]); }
    });
    chrome.on('exit', (code) => { clearTimeout(timer); reject(new Error(`Chrome exited early (${code})`)); });
  });

  const dbgPort = new URL(wsUrl).port;
  const targets = await (await fetch(`http://127.0.0.1:${dbgPort}/json`)).json();
  const pageTarget = targets.find((t) => t.type === 'page');
  if (!pageTarget) throw new Error('No page target');
  const ws = new WebSocket(pageTarget.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

  let seq = 1;
  const call = (method, params = {}) => new Promise((res, rej) => {
    const id = seq++;
    const onMsg = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id === id) {
        ws.removeEventListener('message', onMsg);
        if (msg.error) rej(new Error(msg.error.message));
        else res(msg.result);
      }
    };
    ws.addEventListener('message', onMsg);
    ws.send(JSON.stringify({ id, method, params }));
  });

  ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
      consoleErrors.push(msg.params.args.map((a) => a.value || a.description).join(' '));
    }
    if (msg.method === 'Runtime.exceptionThrown') {
      exceptions.push(msg.params.exceptionDetails?.text || 'Exception');
    }
  });

  await call('Runtime.enable');
  await call('Emulation.setDeviceMetricsOverride', { width: VIEWPORT.width, height: VIEWPORT.height, deviceScaleFactor: 1, mobile: false });
  await new Promise((r) => setTimeout(r, 350));

  const evalJs = async (expression) => {
    const r = await call('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    return r.result?.value;
  };
  const snap = async () => Buffer.from((await call('Page.captureScreenshot', { format: 'png' })).data, 'base64');
  const snapCanvas = async () => await evalJs(`new Promise((resolve) => {
    const c = document.querySelector('canvas');
    if (!c || c.width <= 0 || c.height <= 0) { resolve(''); return; }
    requestAnimationFrame(() => {
      try { resolve(c.toDataURL('image/png')); }
      catch { resolve(''); }
    });
  })`);

  const canvas1 = await snapCanvas();
  const t1 = await evalJs(`(() => {
    const c = document.querySelector('canvas');
    let nonUniform = null;
    if (c && c.width > 0 && c.height > 0) {
      try {
        const ctx = c.getContext('2d');
        if (ctx) {
          const d = ctx.getImageData(0, 0, c.width, c.height).data;
          const r0 = d[0], g0 = d[1], b0 = d[2], a0 = d[3];
          const step = Math.max(16, Math.floor(d.length / 4000) * 4);
          nonUniform = false;
          for (let i = 0; i < d.length; i += step) {
            if (d[i] !== r0 || d[i+1] !== g0 || d[i+2] !== b0 || d[i+3] !== a0) { nonUniform = true; break; }
          }
        }
      } catch {}
    }
    return {
      hasCanvas: !!c,
      w: c ? c.width : 0,
      h: c ? c.height : 0,
      nonUniform,
      simTime: document.getElementById('simTime')?.textContent || ''
    };
  })()`);

  await new Promise((r) => setTimeout(r, 450));
  const canvas2 = await snapCanvas();
  const t2 = await evalJs(`({ simTime: document.getElementById('simTime')?.textContent || '' })`);
  const pixelsChanged = Boolean(canvas1 && canvas2 && canvas1 !== canvas2);

  let controls = {};
  if (kind === 'orbital') {
    const timeAdvanced = t1.simTime !== t2.simTime && t2.simTime !== '';
    const playBefore = await evalJs(`document.getElementById('btnPlay')?.textContent || ''`);
    await evalJs(`document.getElementById('btnPlay')?.click()`);
    const p1 = await evalJs(`document.getElementById('simTime')?.textContent || ''`);
    const pCanvas1 = await snapCanvas();
    await new Promise((r) => setTimeout(r, 250));
    const p2 = await evalJs(`document.getElementById('simTime')?.textContent || ''`);
    const pCanvas2 = await snapCanvas();
    const playAfter = await evalJs(`document.getElementById('btnPlay')?.textContent || ''`);
    const pauseOk = p1 !== '' && p1 === p2 && ((pCanvas1 && pCanvas1 === pCanvas2) || playBefore !== playAfter);

    await evalJs(`document.getElementById('btnPlay')?.click()`);
    await new Promise((r) => setTimeout(r, 250));
    const p3 = await evalJs(`document.getElementById('simTime')?.textContent || ''`);
    const resumeOk = p3 !== p2;

    const speedBefore = await evalJs(`document.getElementById('speedVal')?.textContent || ''`);
    await evalJs(`(() => { const s = document.getElementById('speed'); if (s) { s.value = '2.5'; s.dispatchEvent(new Event('input', {bubbles:true})); } })()`);
    const speedAfter = await evalJs(`document.getElementById('speedVal')?.textContent || ''`);
    const speedOk = speedAfter !== speedBefore && speedAfter.includes('2.5');

    const trailsBefore = await evalJs(`document.getElementById('btnTrails')?.textContent || ''`);
    await evalJs(`document.getElementById('btnTrails')?.click()`);
    const trailsAfter = await evalJs(`document.getElementById('btnTrails')?.textContent || ''`);
    const trailsOk = trailsBefore !== '' && trailsAfter !== trailsBefore;

    const burstsBefore = parseInt(await evalJs(`document.getElementById('bursts')?.textContent || '0'`), 10) || 0;
    await evalJs(`(() => { const c = document.querySelector('canvas'); if (c) { const r = c.getBoundingClientRect(); c.dispatchEvent(new MouseEvent('click', {bubbles:true, clientX: r.left + r.width/2, clientY: r.top + r.height/2})); } })()`);
    await new Promise((r) => setTimeout(r, 120));
    const burstsAfter = parseInt(await evalJs(`document.getElementById('bursts')?.textContent || '0'`), 10) || 0;
    const burstsOk = burstsAfter > burstsBefore;

    await evalJs(`document.getElementById('btnReset')?.click()`);
    await new Promise((r) => setTimeout(r, 100));
    const timeAfterReset = parseFloat(await evalJs(`document.getElementById('simTime')?.textContent || '999'`));
    const resetOk = Number.isFinite(timeAfterReset) && timeAfterReset < 0.6;

    controls = { timeAdvanced, pauseOk, resumeOk, speedOk, trailsOk, burstsOk, resetOk };
  } else {
    const hud = await evalJs(`({
      polys: document.getElementById('polys')?.textContent || '',
      parts: document.getElementById('parts')?.textContent || '',
      pauseBefore: document.getElementById('btnPause')?.textContent || '',
      orbitBefore: document.getElementById('btnOrbit')?.textContent || '',
      speedBefore: document.getElementById('spdVal')?.textContent || ''
    })`);
    await evalJs(`document.getElementById('btnPause')?.click()`);
    const pCanvas1 = await snapCanvas();
    await new Promise((r) => setTimeout(r, 250));
    const pCanvas2 = await snapCanvas();
    const pauseAfter = await evalJs(`document.getElementById('btnPause')?.textContent || ''`);
    const pauseOk = (Boolean(pCanvas1) && pCanvas1 === pCanvas2) || (hud.pauseBefore !== '' && pauseAfter !== hud.pauseBefore);

    await evalJs(`document.getElementById('btnPause')?.click()`);
    const rCanvas1 = await snapCanvas();
    await new Promise((r) => setTimeout(r, 250));
    const rCanvas2 = await snapCanvas();
    const resumeOk = Boolean(rCanvas1 && rCanvas2 && rCanvas1 !== rCanvas2);

    await evalJs(`document.getElementById('btnOrbit')?.click()`);
    const orbitAfter = await evalJs(`document.getElementById('btnOrbit')?.textContent || ''`);
    const orbitOk = hud.orbitBefore !== '' && orbitAfter !== hud.orbitBefore;

    await evalJs(`(() => { const s = document.getElementById('speed'); if (s) { s.value = '2.0'; s.dispatchEvent(new Event('input', {bubbles:true})); } })()`);
    const speedAfter = await evalJs(`document.getElementById('spdVal')?.textContent || ''`);
    const speedOk = speedAfter !== hud.speedBefore && speedAfter.includes('2.0');

    // Pause before testing reset so camera mutation and reset are isolated from animation frames.
    await evalJs(`document.getElementById('btnPause')?.click()`);
    await new Promise((r) => setTimeout(r, 60));
    const canvasBeforeMutate = await snapCanvas();
    await evalJs(`(() => {
      const c = document.querySelector('canvas');
      if (!c) return;
      const r = c.getBoundingClientRect();
      const x0 = r.left + r.width / 2, y0 = r.top + r.height / 2;
      c.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, clientX: x0, clientY: y0, pointerId: 1}));
      c.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, clientX: x0, clientY: y0}));
      window.dispatchEvent(new PointerEvent('pointermove', {bubbles: true, clientX: x0 + 180, clientY: y0 - 80, pointerId: 1}));
      c.dispatchEvent(new PointerEvent('pointermove', {bubbles: true, clientX: x0 + 180, clientY: y0 - 80, pointerId: 1}));
      window.dispatchEvent(new MouseEvent('mousemove', {bubbles: true, clientX: x0 + 180, clientY: y0 - 80}));
      window.dispatchEvent(new PointerEvent('pointerup', {bubbles: true, clientX: x0 + 180, clientY: y0 - 80, pointerId: 1}));
      c.dispatchEvent(new PointerEvent('pointerup', {bubbles: true, clientX: x0 + 180, clientY: y0 - 80, pointerId: 1}));
      window.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, clientX: x0 + 180, clientY: y0 - 80}));
      c.dispatchEvent(new WheelEvent('wheel', {bubbles: true, deltaY: 600}));
    })()`);
    await new Promise((r) => setTimeout(r, 80));
    const canvasMutated = await snapCanvas();
    const cameraMutated = Boolean(canvasBeforeMutate && canvasMutated && canvasMutated !== canvasBeforeMutate);

    await evalJs(`document.getElementById('btnReset')?.click()`);
    await new Promise((r) => setTimeout(r, 80));
    const canvasAfterReset = await snapCanvas();
    await evalJs(`document.getElementById('btnReset')?.click()`);
    await new Promise((r) => setTimeout(r, 80));
    const canvasAfterReset2 = await snapCanvas();
    const resetOk = Boolean(
      cameraMutated &&
      canvasAfterReset &&
      canvasAfterReset !== canvasMutated &&
      canvasAfterReset === canvasAfterReset2
    );

    controls = {
      hasHud: Boolean(hud.polys && hud.parts),
      pauseOk,
      resumeOk,
      orbitOk,
      speedOk,
      resetOk,
    };
  }

  ws.close();
  console.log(JSON.stringify({
    hasCanvas: t1.hasCanvas,
    w: t1.w,
    h: t1.h,
    nonUniform: t1.nonUniform,
    pixelsChanged,
    consoleErrors,
    exceptions,
    controls,
  }));
} finally {
  chrome.kill('SIGKILL');
  srv.close();
  fs.rmSync(userDir, { recursive: true, force: true });
}
"""


def find_chromium() -> str | None:
    """Locate a Chromium/Chrome binary via env, PATH, or Playwright cache."""
    if os.environ.get('TANDEM_DISABLE_BROWSER', '').strip() == '1':
        return None
    override = os.environ.get('TANDEM_CHROMIUM_BIN', '').strip()
    if override:
        return override if Path(override).is_file() else None
    for cmd in ('chromium', 'chromium-browser', 'google-chrome', 'chrome'):
        found = shutil.which(cmd)
        if found:
            return found
    cache = Path.home() / '.cache' / 'ms-playwright'
    if cache.is_dir():
        patterns = (
            'chromium*/chrome-linux*/chrome',
            'chromium_headless_shell*/chrome-headless-shell-linux*/chrome-headless-shell',
        )
        for pat in patterns:
            matches = sorted(cache.glob(pat), reverse=True)
            for m in matches:
                if m.is_file() and os.access(m, os.X_OK):
                    return str(m)
    return None


def run_browser_check(ws_dir: Path, kind: str, timeout: int = 45) -> dict[str, Any]:
    """Run real headless Chromium checks on a web artifact.

    Returns a dict with status in {'passed', 'failed', 'not_evaluated'}.
    """
    index_path = ws_dir / 'index.html'
    if not index_path.is_file():
        return {
            'status': 'failed',
            'browser_available': True,
            'browser_passed': False,
            'error': 'index.html missing',
        }

    chrome = find_chromium()
    if not chrome:
        return {
            'status': 'not_evaluated',
            'browser_available': False,
            'browser_passed': None,
            'error': 'chromium binary not found',
        }

    node = shutil.which('node')
    if not node:
        return {
            'status': 'not_evaluated',
            'browser_available': False,
            'browser_passed': None,
            'error': 'node binary not found',
        }

    try:
        proc = subprocess.run(
            [node, '--input-type=module', '-e', _CDP_SCRIPT, chrome, str(ws_dir.resolve()), kind],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            'status': 'failed',
            'browser_available': True,
            'browser_passed': False,
            'error': f'browser check timed out after {timeout}s',
        }

    if proc.returncode != 0:
        return {
            'status': 'failed',
            'browser_available': True,
            'browser_passed': False,
            'error': (proc.stderr or proc.stdout).strip()[:400],
        }

    try:
        parsed = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as exc:
        return {
            'status': 'failed',
            'browser_available': True,
            'browser_passed': False,
            'error': f'invalid browser output: {exc}',
        }

    errs = list(parsed.get('consoleErrors') or []) + list(parsed.get('exceptions') or [])
    controls = parsed.get('controls') or {}
    non_uniform_ok = parsed.get('nonUniform') is not False
    ok = (
        bool(parsed.get('hasCanvas'))
        and parsed.get('w', 0) > 0
        and parsed.get('h', 0) > 0
        and non_uniform_ok
        and bool(parsed.get('pixelsChanged'))
        and len(errs) == 0
        and bool(controls)
        and all(bool(v) for v in controls.values())
    )
    return {
        'status': 'passed' if ok else 'failed',
        'browser_available': True,
        'browser_passed': ok,
        'console_errors': parsed.get('consoleErrors', []),
        'exceptions': parsed.get('exceptions', []),
        'pixels_changed': parsed.get('pixelsChanged'),
        'non_uniform': parsed.get('nonUniform'),
        'canvas': {'w': parsed.get('w', 0), 'h': parsed.get('h', 0)},
        'controls': controls,
    }
