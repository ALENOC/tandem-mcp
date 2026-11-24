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

// Where the main thread spends its time while the page animates: script functions with at least 5% of the CPU
// profiler samples, as "name (file:line) share%", and the share of native work outside scripts (drawing).
async function hotSpots(call, baseUrl) {
  try {
    await call('Profiler.enable');
    await call('Profiler.setSamplingInterval', { interval: 1000 });
    await call('Profiler.start');
    await sleep(1200);
    const { profile } = await call('Profiler.stop');
    const nodes = new Map((profile.nodes || []).map((n) => [n.id, n]));
    const counts = new Map();
    for (const id of profile.samples || []) counts.set(id, (counts.get(id) || 0) + 1);
    const total = (profile.samples || []).length || 1;
    const byPlace = new Map();
    let native = 0;
    for (const [id, n] of counts) {
      const cf = nodes.get(id)?.callFrame || {};
      const name = cf.functionName || '(anonymous)';
      if (name === '(program)') { native += n; continue; }
      if (name.startsWith('(')) continue;
      let file = cf.url || '';
      if (!file) continue;
      if (file.startsWith(baseUrl)) file = file.slice(baseUrl.length);
      const key = `${name} (${file}:${(cf.lineNumber ?? -1) + 1})`;
      byPlace.set(key, (byPlace.get(key) || 0) + n);
    }
    const script = [...byPlace.entries()].filter(([, n]) => n / total >= 0.05).sort((a, b) => b[1] - a[1]).slice(0, 3)
      .map(([k, n]) => `${k} ${Math.round((100 * n) / total)}%`);
    return { script, nativeShare: Math.round((100 * native) / total) };
  } catch (err) {
    return { script: [], nativeShare: null };
  }
}

// Frames per second while the page animates, counted with requestAnimationFrame over 2 s.
async function countFrames(call) {
  const res = await call('Runtime.evaluate', {
    expression: `new Promise((resolve) => {
      let n = 0, t0 = null, last = 0, long = 0, worst = 0;
      const done = (now) => resolve({ fps: n && t0 !== null ? (n * 1000) / (now - t0) : 0, long, worst: Math.round(worst) });
      const guard = setTimeout(() => done(performance.now()), 4000);
      function frame(now) {
        if (t0 === null) { t0 = now; last = now; }
        else { n++; const d = now - last; if (d > 34) long++; if (d > worst) worst = d; last = now; }
        if (now - t0 < 2000) requestAnimationFrame(frame); else { clearTimeout(guard); done(now); }
      }
      requestAnimationFrame(frame);
    })`,
    awaitPromise: true,
    returnByValue: true,
  });
  return res.result?.value || { fps: 0, long: 0, worst: 0 };
}

// The frame rate, and the FPS the page itself shows, if it shows one.
async function measurePerf(call, minFps) {
  const r = await countFrames(call);
  // the FPS the page shows: the smallest visible element whose text holds the word and a number
  const shownRes = await call('Runtime.evaluate', {
    expression: `(() => {
      const els = Array.from(document.querySelectorAll('body *')).filter((el) => {
        const t = (el.textContent || '').trim();
        return t.length > 0 && t.length <= 40 && /fps/i.test(t) && el.getClientRects().length > 0;
      }).sort((a, b) => a.textContent.length - b.textContent.length);
      for (const el of els) {
        const t = el.textContent.replace(/\\s+/g, ' ').trim();
        const m = t.match(/(\\d+(?:\\.\\d+)?)\\s*fps\\b/i) || t.match(/\\bfps\\b\\s*[:=]?\\s*(\\d+(?:\\.\\d+)?)/i);
        if (m) return Number(m[1]);
      }
      return null;
    })()`,
    returnByValue: true,
  });
  const fps = Math.round(r.fps);
  const shown = typeof shownRes.result?.value === 'number' ? shownRes.result.value : null;
  const out = { status: 'passed', fps, minFps, longFrames: r.long, worstFrameMs: r.worst, shown };
  if (fps < minFps) {
    out.status = 'failed';
    out.slow = true;
    out.reason = `the page draws ${fps} frames per second in headless Chromium at ${W}x${H}, it needs ${minFps} or more`;
  } else if (shown !== null && fps >= 10 && (shown * 2 < fps || shown > fps * 2)) {
    out.status = 'failed';
    out.readout = true;
    out.reason = `the FPS readout shows ${shown} while the page draws ${fps} frames per second`;
  }
  return out;
}

// Canvas features that are slow on many shapes, each turned off before the page loads to see what the frame rate
// would be without it: the cause of a slow page, measured rather than guessed.
const COSTLY = {
  shadowBlur: `Object.defineProperty(CanvasRenderingContext2D.prototype, 'shadowBlur', { configurable: true, get() { return 0; }, set(v) {} });`,
  filter: `Object.defineProperty(CanvasRenderingContext2D.prototype, 'filter', { configurable: true, get() { return 'none'; }, set(v) {} });`,
};

async function runProbe(wsDir, entryRel, chromePath, requireAnim, darkTheme, resetWanted = true, minFps = 0, perfFail = true, screenshotPath = '') {
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
      const t = setTimeout(() => reject(new Error('DevTools startup timeout')), 30000);
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

    // A page that animates must keep up: measured while it runs, before any control is touched.
    let perf = { status: 'skipped' };
    if (minFps > 0 && requireAnim && canvasSized && animated) {
      perf = await measurePerf(call, minFps);
    }

    // Capture the live initial view at 1280x800 before controls are clicked, for local/cloud visual review.
    let savedScreenshot = '';
    if (screenshotPath) {
      try {
        const shot = await call('Page.captureScreenshot', { format: 'jpeg', quality: 82 });
        if (shot && shot.data) {
          fs.mkdirSync(path.dirname(screenshotPath), { recursive: true });
          fs.writeFileSync(screenshotPath, Buffer.from(shot.data, 'base64'));
          savedScreenshot = screenshotPath;
        }
      } catch (_) {}
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

    // Why a page is slow: where the time goes, then each costly canvas feature turned off in a fresh load.
    if (perf.slow) {
      const where = await hotSpots(call, baseUrl);
      const hints = [...where.script];
      if (!where.script.length && where.nativeShare !== null && where.nativeShare >= 60) {
        hints.push(`${where.nativeShare}% of the time is drawing on the canvas, not script`);
      }
      const errorsSoFar = [runtimeErrors.length, consoleErrors.length];
      for (const [feature, js] of Object.entries(COSTLY)) {
        const added = await call('Page.addScriptToEvaluateOnNewDocument', { source: js });
        await call('Page.navigate', { url: `${baseUrl}${entryRel.replace(/^\/+/, '')}` });
        await sleep(1100);
        if (startedViaPlayButton) {
          await call('Runtime.evaluate', {
            expression: `(() => { const b = Array.from(document.querySelectorAll('button, [role="button"], input[type="button"]')).find((el) => /^[^a-z0-9]*(?:play|start|resume|avvia)(?:\\s*\\/\\s*pause)?$/i.test((el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || '').trim())); if (b) b.click(); })()`,
            returnByValue: true,
          });
          await sleep(250);
        }
        const without = Math.round((await countFrames(call)).fps);
        await call('Page.removeScriptToEvaluateOnNewDocument', { identifier: added.identifier });
        if (without >= minFps || without >= 1.5 * perf.fps + 5) {
          hints.push(`with ${feature} turned off it draws ${without} frames per second`);
        }
      }
      runtimeErrors.length = errorsSoFar[0];   // the trial loads are not the page as it ships
      consoleErrors.length = errorsSoFar[1];
      perf.hot = hints;
    }
    if (perf.status === 'failed' && !perfFail) perf.status = 'warned';

    const errorsOk = runtimeErrors.length === 0 && consoleErrors.length === 0;
    const animOk = !requireAnim || (canvasSized && animated);
    const passed = errorsOk && animOk && resetCheck.status !== 'failed' && exposure.status !== 'failed' && perf.status !== 'failed';

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
      perf,
      screenshot: savedScreenshot || null,
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

const [, , wsDir, entryRel, chromePath, reqAnim, darkArg, resetArg, minFpsArg, perfArg, screenshotArg] = process.argv;
if (!wsDir || !entryRel) {
  console.error('Usage: _web_probe.mjs <wsDir> <entryRel> <chromePath> <requireAnim:0|1> [dark:0|1] [reset:0|1] [minFps] [perfFail:0|1] [screenshotPath]');
  process.exit(2);
}
const out = await runProbe(path.resolve(wsDir), entryRel, chromePath || '', reqAnim === '1', darkArg === '1', resetArg !== '0',
  Number(minFpsArg) > 0 ? Number(minFpsArg) : 0, perfArg !== '0', screenshotArg || '');
console.log(JSON.stringify(out));
if (out.status === 'passed') process.exit(0);
if (out.status === 'not_evaluated') process.exit(2);
process.exit(1);
