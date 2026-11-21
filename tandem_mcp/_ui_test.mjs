// Declarative UI acceptance test for tandem:ui_test. Runs a JSON scenario against a page in headless Chromium.
// Usage: node _ui_test.mjs <wsDir> <chromePath> <specJson>
// Prints one JSON line: {status: passed|failed|not_evaluated, steps: [...], errors: [...]}
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png',
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function serveDir(dir) {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      const rel = (req.url || '/').split('?')[0].replace(/^\/+/, '') || 'index.html';
      const full = path.resolve(dir, rel);
      if (!full.startsWith(path.resolve(dir)) || !fs.existsSync(full) || fs.statSync(full).isDirectory()) {
        res.writeHead(404); res.end(); return;
      }
      res.writeHead(200, { 'Content-Type': MIME[path.extname(full).toLowerCase()] || 'application/octet-stream' });
      fs.createReadStream(full).pipe(res);
    });
    srv.listen(0, '127.0.0.1', () => resolve(srv));
  });
}

function hexToRgb(hex) {
  const h = String(hex).replace('#', '');
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  const n = parseInt(full, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

async function run(wsDir, chromePath, spec) {
  const entry = String(spec.entry || 'index.html').replace(/^\/+/, '');
  if (!fs.existsSync(path.join(wsDir, entry))) {
    return { status: 'failed', steps: [], errors: [`missing entry point ${entry}`] };
  }
  if (!chromePath || !fs.existsSync(chromePath)) {
    return { status: 'not_evaluated', reason: `Chromium binary not found (${chromePath || 'unset'})` };
  }
  const [W, H] = Array.isArray(spec.viewport) ? spec.viewport : [1280, 800];
  const srv = await serveDir(wsDir);
  const baseUrl = `http://127.0.0.1:${srv.address().port}/`;
  const userDir = fs.mkdtempSync(path.join(os.tmpdir(), 'tandem-ui-'));
  const chrome = spawn(chromePath, [
    '--headless=new', '--no-sandbox', '--disable-gpu', `--window-size=${W},${H}`,
    '--remote-debugging-port=0', `--user-data-dir=${userDir}`, 'about:blank',
  ], { stdio: ['ignore', 'ignore', 'pipe'] });
  const errors = [];
  const steps = [];
  try {
    const wsUrl = await new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error('DevTools startup timeout')), 10000);
      let b = '';
      chrome.stderr.on('data', (c) => {
        b += c;
        const m = b.match(/DevTools listening on (ws:\/\/\S+)/);
        if (m) { clearTimeout(t); resolve(m[1]); }
      });
      chrome.on('exit', (code) => { clearTimeout(t); reject(new Error(`Chromium exited (${code})`)); });
    });
    const targets = await (await fetch(`http://127.0.0.1:${new URL(wsUrl).port}/json`)).json();
    const ws = new WebSocket(targets.find((t) => t.type === 'page').webSocketDebuggerUrl);
    await new Promise((r, rej) => { ws.onopen = r; ws.onerror = rej; });
    let seq = 1;
    const call = (method, params = {}) => new Promise((res, rej) => {
      const id = seq++;
      const h = (ev) => {
        const d = JSON.parse(ev.data);
        if (d.id === id) { ws.removeEventListener('message', h); d.error ? rej(new Error(d.error.message)) : res(d.result); }
      };
      ws.addEventListener('message', h);
      ws.send(JSON.stringify({ id, method, params }));
    });
    ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.method === 'Runtime.exceptionThrown') {
        const d = msg.params?.exceptionDetails;
        errors.push(String(d?.exception?.description || d?.text || 'exception').split('\n')[0].slice(0, 200));
      } else if (msg.method === 'Runtime.consoleAPICalled' && msg.params?.type === 'error') {
        errors.push('console.error: ' + (msg.params.args || []).map((a) => a.value ?? a.description ?? '').join(' ').slice(0, 200));
      }
    });
    const evaluate = async (expression) => {
      const r = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
      if (r.exceptionDetails) throw new Error(String(r.exceptionDetails.exception?.description || r.exceptionDetails.text).split('\n')[0]);
      return r.result?.value;
    };
    await call('Page.enable');
    await call('Runtime.enable');
    await call('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });
    await call('Page.navigate', { url: baseUrl + entry });
    await sleep(Number(spec.wait_ms ?? 1000));

    // Element lookup: CSS selector, or "text:<regex>" for a visible control by its label.
    const findExpr = (target) => `(() => {
      const t = ${JSON.stringify(String(target))};
      if (t.startsWith('text:')) {
        const re = new RegExp(t.slice(5), 'i');
        const all = Array.from(document.querySelectorAll('button, [role="button"], input, a, label, select'));
        return all.find((el) => {
          const r = el.getBoundingClientRect();
          const txt = (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || '').trim();
          return r.width > 0 && r.height > 0 && re.test(txt);
        }) || null;
      }
      return document.querySelector(t);
    })()`;
    const frameHash = async () => evaluate(`(() => {
      const c = document.querySelector('canvas');
      if (!c || !c.width || !c.height) return null;
      const tmp = document.createElement('canvas'); tmp.width = 160; tmp.height = 100;
      const ctx = tmp.getContext('2d'); ctx.drawImage(c, 0, 0, 160, 100);
      const d = ctx.getImageData(0, 0, 160, 100).data; let h = 0;
      for (let i = 0; i < d.length; i += 4) h = (h * 33 + d[i] + d[i + 1] * 3 + d[i + 2] * 7) >>> 0;
      return h;
    })()`);
    const screenshotHash = async () => {
      const shot = await call('Page.captureScreenshot', { format: 'png' });
      let h = 0;
      for (let i = 0; i < shot.data.length; i += 7) h = (h * 33 + shot.data.charCodeAt(i)) >>> 0;
      return h;
    };
    // What the user sees, downsampled to 160 px wide RGB, optionally cut to a region given as fractions.
    const grab = async (region) => {
      const shot = await call('Page.captureScreenshot', { format: 'png' });
      const [x0, y0, x1, y1] = Array.isArray(region) ? region : [0, 0, 1, 1];
      return evaluate(`new Promise((resolve) => {
        const img = new Image();
        img.onload = () => {
          const w = 160, h = Math.max(1, Math.round(160 * img.height / img.width));
          const c = document.createElement('canvas'); c.width = w; c.height = h;
          const ctx = c.getContext('2d'); ctx.drawImage(img, 0, 0, w, h);
          const sx = Math.floor(${x0} * w), sy = Math.floor(${y0} * h);
          const sw = Math.max(1, Math.floor((${x1} - ${x0}) * w)), sh = Math.max(1, Math.floor((${y1} - ${y0}) * h));
          const d = ctx.getImageData(sx, sy, sw, sh).data; const out = [];
          for (let i = 0; i < d.length; i += 4) out.push(d[i], d[i + 1], d[i + 2]);
          resolve(out);
        };
        img.src = 'data:image/png;base64,${shot.data}';
      })`);
    };
    const diffShare = (a, b, tol) => {
      if (!a || !b || a.length !== b.length) return 1;
      let diff = 0;
      for (let i = 0; i < a.length; i += 3) {
        if (Math.abs(a[i] - b[i]) + Math.abs(a[i + 1] - b[i + 1]) + Math.abs(a[i + 2] - b[i + 2]) > tol) diff++;
      }
      return diff / (a.length / 3);
    };
    const motion = async (region) => {
      if (Array.isArray(region)) {
        const a = await grab(region); await sleep(400);
        const b = await grab(region); await sleep(400);
        const c = await grab(region);
        return diffShare(a, b, 12) > 0.002 || diffShare(b, c, 12) > 0.002;
      }
      const useCanvas = (await frameHash()) !== null;
      const sample = useCanvas ? frameHash : screenshotHash;
      const a = await sample(); await sleep(400);
      const b = await sample(); await sleep(400);
      const c = await sample();
      return a !== b || b !== c;
    };
    const snapshots = {};
    // Fraction of pixels close to a color, measured on what the user sees (a screenshot).
    const colorFraction = async (hex, tol, region) => {
      const shot = await call('Page.captureScreenshot', { format: 'png' });
      const [r0, g0, b0] = hexToRgb(hex);
      const [x0, y0, x1, y1] = Array.isArray(region) ? region : [0, 0, 1, 1];
      return evaluate(`new Promise((resolve) => {
        const img = new Image();
        img.onload = () => {
          const w = 200, h = Math.max(1, Math.round(200 * img.height / img.width));
          const c = document.createElement('canvas'); c.width = w; c.height = h;
          const ctx = c.getContext('2d'); ctx.drawImage(img, 0, 0, w, h);
          const sx = Math.floor(${x0} * w), sy = Math.floor(${y0} * h);
          const sw = Math.max(1, Math.floor((${x1} - ${x0}) * w)), sh = Math.max(1, Math.floor((${y1} - ${y0}) * h));
          const d = ctx.getImageData(sx, sy, sw, sh).data; let hit = 0, n = 0;
          for (let i = 0; i < d.length; i += 4) {
            n++;
            const dr = d[i] - ${r0}, dg = d[i + 1] - ${g0}, db = d[i + 2] - ${b0};
            if (Math.sqrt(dr * dr + dg * dg + db * db) <= ${Number(tol)}) hit++;
          }
          resolve(n ? hit / n : 0);
        };
        img.src = 'data:image/png;base64,${shot.data}';
      })`);
    };

    for (const [i, step] of (spec.steps || []).entries()) {
      const rec = { i: i + 1, step, ok: false, detail: '' };
      try {
        if ('wait' in step) {
          await sleep(Number(step.wait)); rec.ok = true;
        } else if ('click' in step) {
          const found = await evaluate(`(() => { const el = ${findExpr(step.click)}; if (!el) return false; el.click(); return true; })()`);
          rec.ok = found === true; rec.detail = rec.ok ? 'clicked' : `no element for ${step.click}`;
          await sleep(Number(step.after_ms ?? 50));
        } else if ('input' in step) {
          const found = await evaluate(`(() => { const el = ${findExpr(step.input)}; if (!el) return false;
            el.value = ${JSON.stringify(String(step.value))};
            el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true }));
            return true; })()`);
          rec.ok = found === true; rec.detail = rec.ok ? `set ${step.value}` : `no element for ${step.input}`;
          await sleep(Number(step.after_ms ?? 50));
        } else if ('key' in step) {
          await call('Input.dispatchKeyEvent', { type: 'keyDown', key: step.key, code: step.code || step.key });
          await call('Input.dispatchKeyEvent', { type: 'keyUp', key: step.key, code: step.code || step.key });
          rec.ok = true; await sleep(Number(step.after_ms ?? 50));
        } else if ('snapshot' in step) {
          snapshots[String(step.snapshot)] = await grab(step.region); rec.ok = true; rec.detail = `saved ${step.snapshot}`;
        } else if ('differs' in step) {
          const base = snapshots[String(step.differs)];
          if (!base) {
            rec.detail = `no snapshot named ${step.differs}`;
          } else {
            const share = diffShare(base, await grab(step.region), Number(step.tol ?? 30));
            const min = Number(step.min ?? 0.01);
            const max = step.max === undefined ? 1 : Number(step.max);
            rec.ok = share >= min && share <= max;
            rec.detail = `${(share * 100).toFixed(1)}% of pixels differ from ${step.differs}` +
              ` (min ${(min * 100).toFixed(1)}%${step.max === undefined ? '' : `, max ${(max * 100).toFixed(1)}%`})`;
          }
        } else if ('expect' in step) {
          const moving = await motion(step.region);
          const want = step.expect === 'moving';
          rec.ok = moving === want; rec.detail = `view is ${moving ? 'moving' : 'static'}, expected ${step.expect}`;
        } else if ('exists' in step) {
          rec.ok = await evaluate(`(() => !!(${findExpr(step.exists)}))()`); rec.detail = rec.ok ? 'found' : `no element for ${step.exists}`;
        } else if ('text' in step) {
          const txt = await evaluate(`(() => { const el = ${findExpr(step.text)}; return el ? (el.innerText || el.textContent || el.value || '').trim() : null; })()`);
          rec.ok = txt !== null && new RegExp(step.match ?? '.', 'i').test(txt);
          rec.detail = txt === null ? `no element for ${step.text}` : `text ${JSON.stringify(txt.slice(0, 80))} vs /${step.match}/`;
        } else if ('js' in step) {
          const v = await evaluate(String(step.js));
          rec.ok = Boolean(v); rec.detail = `${step.label || step.js} -> ${JSON.stringify(v)}`.slice(0, 200);
        } else if ('color' in step) {
          const frac = await colorFraction(step.color, step.tol ?? 48, step.region);
          const okMin = step.min === undefined || frac >= Number(step.min);
          const okMax = step.max === undefined || frac <= Number(step.max);
          rec.ok = okMin && okMax;
          rec.detail = `${(frac * 100).toFixed(1)}% of pixels near ${step.color}` +
            (step.min !== undefined ? ` (min ${step.min * 100}%)` : '') + (step.max !== undefined ? ` (max ${step.max * 100}%)` : '');
        } else {
          rec.detail = `unknown step ${JSON.stringify(step)}`;
        }
      } catch (err) {
        rec.detail = `error: ${String(err?.message || err).slice(0, 200)}`;
      }
      steps.push(rec);
    }
    ws.close();
    const allowErrors = spec.allow_errors === true;
    const passed = steps.every((s) => s.ok) && (allowErrors || errors.length === 0);
    return { status: passed ? 'passed' : 'failed', steps, errors };
  } catch (err) {
    return { status: 'not_evaluated', reason: String(err?.message || err) };
  } finally {
    chrome.kill('SIGKILL');
    srv.close();
    fs.rmSync(userDir, { recursive: true, force: true });
  }
}

const [, , wsDir, chromePath, specJson] = process.argv;
let spec;
try {
  spec = JSON.parse(specJson || '');
} catch (err) {
  console.log(JSON.stringify({ status: 'failed', steps: [], errors: [`invalid ui_test JSON: ${err.message}`] }));
  process.exit(1);
}
const out = await run(path.resolve(wsDir), chromePath || '', spec);
console.log(JSON.stringify(out));
process.exit(out.status === 'passed' ? 0 : out.status === 'not_evaluated' ? 2 : 1);
