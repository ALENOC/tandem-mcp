import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
};

const W = 1280;
const H = 800;
const WHITE_LIMIT = 0.05;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function serveDir(dir) {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      const clean = (req.url || '/').split('?')[0].replace(/^\/+/, '');
      const rel = clean || 'index.html';
      const full = path.resolve(dir, rel);
      if (!full.startsWith(path.resolve(dir)) || !fs.existsSync(full) || fs.statSync(full).isDirectory()) {
        res.writeHead(404);
        res.end();
        return;
      }
      res.writeHead(200, { 'Content-Type': MIME[path.extname(full).toLowerCase()] || 'application/octet-stream' });
      fs.createReadStream(full).pipe(res);
    });
    srv.listen(0, '127.0.0.1', () => resolve(srv));
  });
}

function formatException(details, baseUrl) {
  const desc = details?.exception?.description || details?.text || 'Uncaught exception';
  const firstLine = String(desc).split('\n')[0].trim();
  let file = details?.url || '';
  let line = typeof details?.lineNumber === 'number' ? details.lineNumber + 1 : null;
  let col = typeof details?.columnNumber === 'number' ? details.columnNumber + 1 : null;
  const frames = details?.stackTrace?.callFrames || [];
  if (frames.length > 0) {
    file = frames[0].url || file;
    line = typeof frames[0].lineNumber === 'number' ? frames[0].lineNumber + 1 : line;
    col = typeof frames[0].columnNumber === 'number' ? frames[0].columnNumber + 1 : col;
  }
  if (file.startsWith(baseUrl)) file = file.slice(baseUrl.length).replace(/^\/+/, '');
  const loc = file ? (line ? `${file}:${line}${col ? ':' + col : ''}` : file) : 'unknown';
  return { message: firstLine, location: loc, raw: String(desc).slice(0, 400) };
}

async function runProbe(wsDir, entryRel, chromePath, requireAnim, darkTheme, resetWanted = true) {
  if (!chromePath || !fs.existsSync(chromePath)) {
    return { status: 'not_evaluated', reason: `Chromium binary not found (${chromePath || 'unset'})` };
  }
  const srv = await serveDir(wsDir);
  const port = srv.address().port;
  const baseUrl = `http://127.0.0.1:${port}/`;
  const userDir = fs.mkdtempSync(path.join(os.tmpdir(), 'tandem-web-'));
  const chrome = spawn(chromePath, [
    '--headless=new', '--no-sandbox', '--disable-gpu', `--window-size=${W},${H}`,
    '--remote-debugging-port=0', `--user-data-dir=${userDir}`, 'about:blank',
  ], { stdio: ['ignore', 'ignore', 'pipe'] });

  const runtimeErrors = [];
  const consoleErrors = [];

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
    const pageTarget = targets.find((t) => t.type === 'page');
    if (!pageTarget) throw new Error('No page target');
    const ws = new WebSocket(pageTarget.webSocketDebuggerUrl);
    await new Promise((r, rej) => { ws.onopen = r; ws.onerror = rej; });

    let seq = 1;
    const call = (method, params = {}) => new Promise((res, rej) => {
      const id = seq++;
      const h = (ev) => {
        const d = JSON.parse(ev.data);
        if (d.id === id) {
          ws.removeEventListener('message', h);
          if (d.error) rej(new Error(d.error.message));
          else res(d.result);
        }
      };
      ws.addEventListener('message', h);
      ws.send(JSON.stringify({ id, method, params }));
    });

    ws.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.method === 'Runtime.exceptionThrown') {
        runtimeErrors.push(formatException(msg.params?.exceptionDetails, baseUrl));
      } else if (msg.method === 'Runtime.consoleAPICalled' && msg.params?.type === 'error') {
        const txt = (msg.params.args || []).map((a) => a.value ?? a.description ?? '').join(' ');
        consoleErrors.push(txt.slice(0, 300));
      }
    });

    await call('Page.enable');
    await call('Runtime.enable');
    await call('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });
    await call('Page.navigate', { url: `${baseUrl}${entryRel.replace(/^\/+/, '')}` });

    // Wait for startup and initial animation frames
    await sleep(1100);

    const sampleCanvas = async () => {
      const res = await call('Runtime.evaluate', {
        expression: `(() => {
          const c = document.querySelector('canvas');
          if (!c) return { hasCanvas: false };
          const r = c.getBoundingClientRect();
          const tmp = document.createElement('canvas');
          tmp.width = 160; tmp.height = 100;
          const ctx = tmp.getContext('2d');
          let nonZero = 0, hash = 0;
          if (c.width > 0 && c.height > 0) {
            ctx.drawImage(c, 0, 0, 160, 100);
            const d = ctx.getImageData(0, 0, 160, 100).data;
            for (let i = 0; i < d.length; i += 4) {
              if (d[i] || d[i + 1] || d[i + 2]) nonZero++;
              hash = (hash * 33 + d[i] + d[i + 1] * 3 + d[i + 2] * 7) >>> 0;
            }
          }
          return { hasCanvas: true, w: r.width, h: r.height, cw: c.width, ch: c.height, nonZero, hash: hash.toString(16) };
        })()`,
        returnByValue: true,
      });
      return res.result?.value || { hasCanvas: false };
    };

    const s1 = await sampleCanvas();
    await sleep(450);
    const s2 = await sampleCanvas();
    await sleep(450);
    const s3 = await sampleCanvas();

    const hasCanvas = Boolean(s1.hasCanvas);
    const canvasSized = hasCanvas && s1.cw > 0 && s1.ch > 0 && s1.w > 0 && s1.h > 0;
    let animated = hasCanvas && (s1.hash !== s2.hash || s2.hash !== s3.hash || s1.hash !== s3.hash);
    let startedViaPlayButton = false;

    if (requireAnim && canvasSized && !animated) {
      const clickedPlay = await call('Runtime.evaluate', {
        expression: `(() => {
          const btns = Array.from(document.querySelectorAll('button, [role="button"], input[type="button"]'));
          const cand = btns.find((el) => {
            const r = el.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) return false;
            const txt = (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || '').trim();
            return /^[^a-z0-9]*(?:play|start|resume|avvia)(?:\\s*\\/\\s*pause)?$/i.test(txt);
          });
          if (!cand) return false;
          cand.click();
          return true;
        })()`,
        returnByValue: true,
      });
      if (clickedPlay.result?.value) {
        await sleep(250);
        const s4 = await sampleCanvas();
        await sleep(450);
        const s5 = await sampleCanvas();
        if (s4.hash !== s5.hash || s1.hash !== s5.hash) {
          animated = true;
          startedViaPlayButton = true;
        }
      }
    }

    // Generic control check: Reset must bring back the initial running state, even after Pause.
    // Only judged when the page animated on its own at load and Pause really stopped the canvas.
    let resetCheck = { status: 'skipped' };
    if (resetWanted && requireAnim && canvasSized && animated && !startedViaPlayButton) {
      const clickBtn = async (reSrc) => (await call('Runtime.evaluate', {
        expression: `(() => {
          const re = new RegExp(${JSON.stringify(reSrc)}, 'i');
          const btns = Array.from(document.querySelectorAll('button, [role="button"], input[type="button"]'));
          const el = btns.find((b) => {
            const r = b.getBoundingClientRect();
            const t = (b.innerText || b.textContent || b.value || b.getAttribute('aria-label') || '').trim();
            return r.width > 0 && r.height > 0 && re.test(t);
          });
          if (!el) return false;
          el.click();
          return true;
        })()`,
        returnByValue: true,
      })).result?.value === true;
      const moving = async () => {
        const a = await sampleCanvas();
        await sleep(400);
        const b = await sampleCanvas();
        await sleep(400);
        const c = await sampleCanvas();
        return a.hash !== b.hash || b.hash !== c.hash;
      };
      if (await clickBtn('^(?:\\W*\\s*)?(?:pause|stop|pausa)\\b')) {
        await sleep(300);
        if (await moving()) {
          resetCheck = { status: 'skipped', reason: 'canvas keeps moving while paused' };
        } else if (await clickBtn('^(?:\\W*\\s*)?(?:reset|restart|ricomincia)\\b')) {
          await sleep(400);
          const resumed = await moving();
          resetCheck = resumed
            ? { status: 'passed' }
            : { status: 'failed', reason: 'after Pause then Reset the canvas stayed frozen; Reset must restore the initial running state' };
        } else {
          resetCheck = { status: 'skipped', reason: 'no Reset button' };
        }
      } else {
        resetCheck = { status: 'skipped', reason: 'no Pause button' };
      }
    }

    // Dark or neon theme requested: a large near-white area means overexposed surfaces.
    let exposure = { status: 'skipped' };
    if (darkTheme && canvasSized) {
      const res = await call('Runtime.evaluate', {
        expression: `(() => {
          const c = document.querySelector('canvas');
          const tmp = document.createElement('canvas');
          tmp.width = 160; tmp.height = 100;
          const ctx = tmp.getContext('2d');
          ctx.drawImage(c, 0, 0, 160, 100);
          const d = ctx.getImageData(32, 15, 96, 72).data;
          let white = 0, n = 0;
          for (let i = 0; i < d.length; i += 4) {
            n++;
            if (d[i] >= 185 && d[i + 1] >= 185 && d[i + 2] >= 185) white++;
          }
          return n ? white / n : 0;
        })()`,
        returnByValue: true,
      });
      const frac = Number(res.result?.value || 0);
      exposure = frac > WHITE_LIMIT
        ? { status: 'failed', whiteFraction: Number(frac.toFixed(4)), reason: `${(frac * 100).toFixed(1)}% of the central canvas is near-white (limit ${WHITE_LIMIT * 100}%) on a dark/neon theme: surfaces are overexposed` }
        : { status: 'passed', whiteFraction: Number(frac.toFixed(4)) };
    }

    const errorsOk = runtimeErrors.length === 0 && consoleErrors.length === 0;
    const animOk = !requireAnim || (canvasSized && animated);
    const passed = errorsOk && animOk && resetCheck.status !== 'failed' && exposure.status !== 'failed';

    return {
      status: passed ? 'passed' : 'failed',
      entry: entryRel,
      requireAnimation: requireAnim,
      hasCanvas,
      canvasSized,
      animated,
      startedViaPlayButton,
      resetCheck,
      exposure,
      canvasObserved: hasCanvas ? { w: s1.w, h: s1.h, cw: s1.cw, ch: s1.ch, nonZeroPixels: s1.nonZero, hashes: [s1.hash, s2.hash, s3.hash] } : null,
      runtimeErrors,
      consoleErrors,
    };
  } catch (err) {
    return { status: 'not_evaluated', reason: String(err?.message || err) };
  } finally {
    chrome.kill('SIGKILL');
    srv.close();
    fs.rmSync(userDir, { recursive: true, force: true });
  }
}

const [, , wsDir, entryRel, chromePath, reqAnim, darkArg, resetArg] = process.argv;
if (!wsDir || !entryRel) {
  console.error('Usage: _web_probe.mjs <wsDir> <entryRel> <chromePath> <requireAnim:0|1>');
  process.exit(2);
}
const out = await runProbe(path.resolve(wsDir), entryRel, chromePath || '', reqAnim === '1', darkArg === '1', resetArg !== '0');
console.log(JSON.stringify(out));
if (out.status === 'passed') process.exit(0);
if (out.status === 'not_evaluated') process.exit(2);
process.exit(1);
