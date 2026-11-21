#!/usr/bin/env node
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
};

const W = 1280;
const H = 800;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function findChrome() {
  for (const k of ['TANDEM_CHROME', 'CHROME']) {
    const v = (process.env[k] || '').trim();
    if (v && fs.existsSync(v)) return v;
  }
  const base = path.join(os.homedir(), '.cache', 'ms-playwright');
  if (fs.existsSync(base)) {
    const dirs = fs.readdirSync(base).filter((d) => d.startsWith('chromium-')).sort().reverse();
    for (const d of dirs) {
      for (const sub of ['chrome-linux64/chrome', 'chrome-linux/chrome']) {
        const p = path.join(base, d, sub);
        if (fs.existsSync(p)) return p;
      }
    }
  }
  for (const p of ['/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome']) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

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
  if (file.startsWith(baseUrl)) file = file.slice(baseUrl.length).replace(/^\/+/, '');
  return `${firstLine} (${file || 'inline'})`;
}

export async function evaluateGolBehavioral(wsDir) {
  const indexPath = path.join(wsDir, 'index.html');
  if (!fs.existsSync(indexPath)) {
    return { correct: false, status: 'failed', reason: 'index.html missing', checks: {} };
  }
  const htmlRaw = fs.readFileSync(indexPath, 'utf-8');
  const extMatch = htmlRaw.match(/<(?:script|link|img)[^>]+(?:src|href)\s*=\s*["']https?:\/\//i);
  if (extMatch) {
    return { correct: false, status: 'failed', reason: `external dependency found: ${extMatch[0].slice(0, 80)}`, checks: { noExternalDeps: { passed: false } } };
  }

  const chromePath = findChrome();
  if (!chromePath) {
    return { correct: false, status: 'not_evaluated', reason: 'Chromium binary not found', checks: {} };
  }

  const srv = await serveDir(wsDir);
  const port = srv.address().port;
  const baseUrl = `http://127.0.0.1:${port}/`;
  const userDir = fs.mkdtempSync(path.join(os.tmpdir(), 'gol-behav-'));
  const chrome = spawn(chromePath, [
    '--headless=new', '--no-sandbox', '--disable-gpu', `--window-size=${W},${H}`,
    '--remote-debugging-port=0', `--user-data-dir=${userDir}`, 'about:blank',
  ], { stdio: ['ignore', 'ignore', 'pipe'] });

  const runtimeErrors = [];
  const consoleErrors = [];
  const checks = {};

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

    const evalJs = async (expression) => {
      const res = await call('Runtime.evaluate', { expression, returnByValue: true });
      if (res.exceptionDetails) {
        throw new Error(res.exceptionDetails.text || 'eval error');
      }
      return res.result?.value;
    };

    const clickXY = async (x, y) => {
      await call('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
      await call('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
    };

    const dragXY = async (x1, y1, x2, y2, steps = 8) => {
      await call('Input.dispatchMouseEvent', { type: 'mousePressed', x: x1, y: y1, button: 'left', clickCount: 1 });
      for (let i = 1; i <= steps; i++) {
        const xi = x1 + ((x2 - x1) * i) / steps;
        const yi = y1 + ((y2 - y1) * i) / steps;
        await call('Input.dispatchMouseEvent', { type: 'mouseMoved', x: xi, y: yi, button: 'left' });
        await sleep(12);
      }
      await call('Input.dispatchMouseEvent', { type: 'mouseReleased', x: x2, y: y2, button: 'left', clickCount: 1 });
    };

    await call('Page.enable');
    await call('Runtime.enable');
    await call('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });
    await call('Page.navigate', { url: `${baseUrl}index.html` });
    await sleep(700);

    // 1. Inspect DOM, canvas, HUD, glassmorphism, controls (no DOM IDs assumed)
    const snap = async () => evalJs(`(() => {
      const c = document.querySelector('canvas');
      const cr = c ? c.getBoundingClientRect() : null;
      let canvasInfo = { exists: false };
      if (c) {
        const tmp = document.createElement('canvas');
        tmp.width = 240; tmp.height = 150;
        const tctx = tmp.getContext('2d');
        let hash = 0, bright = 0, bgMatch = 0;
        if (c.width > 0 && c.height > 0) {
          tctx.drawImage(c, 0, 0, 240, 150);
          const d = tctx.getImageData(0, 0, 240, 150).data;
          for (let i = 0; i < d.length; i += 4) {
            const r = d[i], g = d[i + 1], b = d[i + 2];
            hash = (hash * 33 + r + g * 3 + b * 7) >>> 0;
            if (Math.abs(r - 8) <= 6 && Math.abs(g - 12) <= 6 && Math.abs(b - 24) <= 6) bgMatch++;
            if (r > 35 || g > 35 || b > 50) bright++;
          }
        }
        canvasInfo = {
          exists: true,
          w: cr.width, h: cr.height, cw: c.width, ch: c.height,
          hash: hash.toString(16), bright, bgMatch,
          bgCss: getComputedStyle(c).backgroundColor,
        };
      }
      const bodyBg = getComputedStyle(document.body).backgroundColor;
      const htmlBg = getComputedStyle(document.documentElement).backgroundColor;

      // Glassmorphism check
      let hasGlass = false;
      for (const el of document.querySelectorAll('*')) {
        const st = getComputedStyle(el);
        const bf = st.backdropFilter || st.webkitBackdropFilter || '';
        if (bf.includes('blur(') && (st.backgroundColor.includes('rgba(') || st.backgroundColor.includes('hsla(') || st.backgroundColor.includes('/'))) {
          hasGlass = true;
          break;
        }
      }

      // Parse HUD metrics from visible text without relying on IDs
      const bodyText = (document.body.innerText || '').replace(/\\s+/g, ' ');
      const extractNum = (pats) => {
        for (const p of pats) {
          const m = bodyText.match(p);
          if (m) return Number(m[1].replace(/,/g, ''));
        }
        return null;
      };
      const fpsVal = extractNum([/fps\\s*[:\\-]?\\s*(\\d+(?:\\.\\d+)?)/i, /(\\d+(?:\\.\\d+)?)\\s*fps\\b/i]);
      const genVal = extractNum([/genera[tz]ion[ei]?\\s*[:\\-#]?\\s*(\\d+(?:,\\d+)*)/i, /gen\\s*[:\\-#]?\\s*(\\d+(?:,\\d+)*)/i]);
      const liveVal = extractNum([
        /(?:live\\s*cells?|celle\\s*vive|alive|cells?)\\s*[:\\-#]?\\s*(\\d+(?:,\\d+)*)/i,
        /(\\d+(?:,\\d+)*)\\s*(?:live\\s*cells?|celle\\s*vive)/i,
      ]);

      // Buttons by visible text / aria-label
      const btns = Array.from(document.querySelectorAll('button, [role="button"]')).map((b) => {
        const r = b.getBoundingClientRect();
        return {
          text: (b.innerText || b.textContent || b.getAttribute('aria-label') || '').trim(),
          x: r.left + r.width / 2,
          y: r.top + r.height / 2,
          visible: r.width > 0 && r.height > 0,
        };
      }).filter((b) => b.visible);

      const sliderEl = document.querySelector('input[type="range"]');
      const slider = sliderEl ? {
        min: Number(sliderEl.min || 0),
        max: Number(sliderEl.max || 100),
        val: Number(sliderEl.value),
      } : null;

      return { canvas: canvasInfo, bodyBg, htmlBg, hasGlass, bodyText: bodyText.slice(0, 500), fpsVal, genVal, liveVal, btns, slider };
    })()`);

    const s0 = await snap();
    const isBg080c18 = (bg) => /rgba?\(\s*8\s*,\s*12\s*,\s*24/.test(bg || '');
    const bgOk = isBg080c18(s0.bodyBg) || isBg080c18(s0.htmlBg) || isBg080c18(s0.canvas.bgCss) || (s0.canvas.bgMatch > 10000);
    checks.layoutAndTheme = {
      passed: s0.canvas.exists && s0.canvas.w >= 1200 && s0.canvas.h >= 700 && bgOk,
      canvas: { w: s0.canvas.w, h: s0.canvas.h, cw: s0.canvas.cw, ch: s0.canvas.ch },
      bgOk,
    };

    // Resize test
    await call('Emulation.setDeviceMetricsOverride', { width: 960, height: 640, deviceScaleFactor: 1, mobile: false });
    await sleep(200);
    const sRes = await snap();
    await call('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });
    await sleep(200);
    checks.resize = {
      passed: sRes.canvas.exists && sRes.canvas.w <= 970 && sRes.canvas.h <= 650 && sRes.canvas.w !== s0.canvas.w,
      beforeW: s0.canvas.w, afterW: sRes.canvas.w,
    };

    checks.glassmorphismHud = {
      passed: s0.hasGlass && s0.fpsVal !== null && s0.genVal !== null && s0.liveVal !== null,
      hasGlass: s0.hasGlass, fpsVal: s0.fpsVal, genVal: s0.genVal, liveVal: s0.liveVal,
    };

    // Locate controls by label text
    const findBtn = (re) => s0.btns.find((b) => re.test(b.text));
    const btnPlayPause = findBtn(/^(play|pause|resume|avvia|pausa)$/i) || findBtn(/\b(play|pause|resume)\b/i);
    const btnStep = findBtn(/\bstep\b/i);
    const btnRandomize = findBtn(/\brandom(?:ize)?\b/i);
    const btnClear = findBtn(/\bclear\b/i);

    checks.controlsPresent = {
      passed: Boolean(btnPlayPause && btnStep && btnRandomize && btnClear && s0.slider && s0.slider.min <= 1 && s0.slider.max >= 30),
      playPause: btnPlayPause?.text || null,
      step: btnStep?.text || null,
      randomize: btnRandomize?.text || null,
      clear: btnClear?.text || null,
      slider: s0.slider,
    };

    // Helper to ensure paused
    const ensurePaused = async () => {
      const cur = await snap();
      const pb = cur.btns.find((b) => /\b(pause|pausa)\b/i.test(b.text) && !/\bplay\b/i.test(b.text));
      if (pb) {
        await clickXY(pb.x, pb.y);
        await sleep(120);
      } else {
        // Might be labeled "Play / Pause" or "Pause" while running: check if gen/hash advances
        const a = await snap();
        await sleep(300);
        const b = await snap();
        if (a.genVal !== b.genVal || a.canvas.hash !== b.canvas.hash) {
          const pp = b.btns.find((x) => /\b(play|pause|resume)\b/i.test(x.text));
          if (pp) { await clickXY(pp.x, pp.y); await sleep(120); }
        }
      }
    };

    // Find a safe canvas point not covered by HUD/controls
    const canvasPoint = await evalJs(`(() => {
      const c = document.querySelector('canvas');
      if (!c) return null;
      const r = c.getBoundingClientRect();
      const candidates = [
        [r.left + r.width * 0.5, r.top + r.height * 0.5],
        [r.left + r.width * 0.35, r.top + r.height * 0.65],
        [r.left + r.width * 0.65, r.top + r.height * 0.65],
        [r.left + r.width * 0.5, r.top + r.height * 0.75],
      ];
      for (const [x, y] of candidates) {
        if (document.elementFromPoint(x, y) === c) return { x: Math.round(x), y: Math.round(y) };
      }
      return null;
    })()`);

    // 2. Test Clear
    await ensurePaused();
    if (btnRandomize) { await clickXY(btnRandomize.x, btnRandomize.y); await sleep(100); }
    const preClear = await snap();
    if (btnClear) { await clickXY(btnClear.x, btnClear.y); await sleep(120); }
    const afterClear = await snap();
    checks.clear = {
      passed: Boolean(btnClear) && afterClear.liveVal === 0 && afterClear.canvas.bright < Math.max(5, preClear.canvas.bright),
      preBright: preClear.canvas.bright,
      afterBright: afterClear.canvas.bright,
      afterLive: afterClear.liveVal,
    };

    // 3. Test Draw (click + drag) and Clear restores empty
    let drawPassed = false;
    let drawDetail = {};
    if (canvasPoint && btnClear) {
      await clickXY(canvasPoint.x, canvasPoint.y);
      await sleep(100);
      const afterClick = await snap();
      await dragXY(canvasPoint.x + 60, canvasPoint.y + 60, canvasPoint.x + 150, canvasPoint.y + 60, 8);
      await sleep(100);
      const afterDrag = await snap();
      drawPassed = (afterClick.liveVal || 0) >= 1
        && afterClick.canvas.hash !== afterClear.canvas.hash
        && (afterDrag.liveVal || 0) > (afterClick.liveVal || 0)
        && afterDrag.canvas.hash !== afterClick.canvas.hash;
      drawDetail = {
        clickLive: afterClick.liveVal,
        dragLive: afterDrag.liveVal,
        hashChangedOnClick: afterClick.canvas.hash !== afterClear.canvas.hash,
        hashChangedOnDrag: afterDrag.canvas.hash !== afterClick.canvas.hash,
      };
      // Also verify Clear erases drawn cells
      await clickXY(btnClear.x, btnClear.y);
      await sleep(100);
      const clearedDrawn = await snap();
      if (clearedDrawn.liveVal !== 0 || clearedDrawn.canvas.hash !== afterClear.canvas.hash) {
        checks.clear.passed = false;
        checks.clear.failedAfterDraw = true;
      }
    }
    checks.draw = { passed: drawPassed, ...drawDetail };

    // 4. Test Step with known pattern (3-cell horizontal blinker)
    let stepPassed = false;
    let stepDetail = {};
    if (canvasPoint && btnClear && btnStep) {
      await ensurePaused();
      let pitch = null;
      for (const d of [6, 8, 10, 12, 14, 16, 18, 20, 24, 28]) {
        await clickXY(btnClear.x, btnClear.y);
        await sleep(60);
        await clickXY(canvasPoint.x, canvasPoint.y);
        await sleep(60);
        await clickXY(canvasPoint.x + d, canvasPoint.y);
        await sleep(60);
        const sProbe = await snap();
        if (sProbe.liveVal === 2) {
          await clickXY(canvasPoint.x + 2 * d, canvasPoint.y);
          await sleep(60);
          const s3 = await snap();
          if (s3.liveVal === 3) {
            // Check if Step 1 keeps 3 live cells (adjacent blinker) vs 0 (non-adjacent)
            const g0 = s3.genVal;
            const h0 = s3.canvas.hash;
            await clickXY(btnStep.x, btnStep.y);
            await sleep(80);
            const st1 = await snap();
            if (st1.liveVal === 3 && st1.genVal === g0 + 1 && st1.canvas.hash !== h0) {
              await clickXY(btnStep.x, btnStep.y);
              await sleep(80);
              const st2 = await snap();
              stepPassed = st2.liveVal === 3 && st2.genVal === g0 + 2 && st2.canvas.hash === h0;
              pitch = d;
              stepDetail = { pitch, g0, g1: st1.genVal, g2: st2.genVal, live1: st1.liveVal, live2: st2.liveVal, period2: st2.canvas.hash === h0 };
              break;
            }
          }
        }
      }
      if (!stepPassed && Object.keys(stepDetail).length === 0) {
        // Fallback check: at least see if Step changed anything on a blinker probe
        stepDetail = { note: 'Could not verify 3-cell blinker oscillation via Step' };
      }
    }
    checks.step = { passed: stepPassed, ...stepDetail };

    // 5. Test Play & Pause
    let playPassed = false;
    let pausePassed = false;
    let playDetail = {};
    let pauseDetail = {};
    if (btnRandomize && btnPlayPause) {
      await ensurePaused();
      await clickXY(btnRandomize.x, btnRandomize.y);
      await sleep(100);
      const sRand = await snap();
      checks.randomize = {
        passed: (sRand.liveVal || 0) > 10 && sRand.canvas.bright > afterClear.canvas.bright,
        liveVal: sRand.liveVal,
        bright: sRand.canvas.bright,
      };

      // Confirm paused state holds before Play
      await sleep(300);
      const sPausedBefore = await snap();

      // Click Play
      const curPlayBtn = sPausedBefore.btns.find((b) => /\b(play|pause|resume)\b/i.test(b.text));
      await clickXY(curPlayBtn.x, curPlayBtn.y);
      await sleep(850);
      const sPlaying = await snap();
      playPassed = (sPlaying.genVal || 0) > (sPausedBefore.genVal || 0) && sPlaying.canvas.hash !== sPausedBefore.canvas.hash;
      playDetail = { genBefore: sPausedBefore.genVal, genAfter: sPlaying.genVal, hashChanged: sPlaying.canvas.hash !== sPausedBefore.canvas.hash };

      // Click Pause
      const curPauseBtn = sPlaying.btns.find((b) => /\b(play|pause|resume)\b/i.test(b.text));
      await clickXY(curPauseBtn.x, curPauseBtn.y);
      await sleep(150);
      const p1 = await snap();
      await sleep(500);
      const p2 = await snap();
      pausePassed = p1.genVal === p2.genVal && p1.canvas.hash === p2.canvas.hash;
      pauseDetail = { gen1: p1.genVal, gen2: p2.genVal, hashSame: p1.canvas.hash === p2.canvas.hash };
    } else {
      checks.randomize = { passed: false, reason: 'missing Randomize button' };
    }
    checks.play = { passed: playPassed, ...playDetail };
    checks.pause = { passed: pausePassed, ...pauseDetail };

    // 6. Test Speed Slider (1..30)
    let speedPassed = false;
    let speedDetail = {};
    if (s0.slider && btnRandomize && btnPlayPause) {
      const setSlider = async (val) => evalJs(`(() => {
        const el = document.querySelector('input[type="range"]');
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, '${val}');
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return Number(el.value);
      })()`);

      await ensurePaused();
      await clickXY(btnRandomize.x, btnRandomize.y);
      await sleep(80);
      const curB = (await snap()).btns.find((b) => /\b(play|pause|resume)\b/i.test(b.text));
      await clickXY(curB.x, curB.y); // start playing

      await setSlider(2);
      await sleep(200);
      const low1 = await snap();
      await sleep(850);
      const low2 = await snap();
      const dLow = (low2.genVal ?? 0) - (low1.genVal ?? 0);

      await setSlider(28);
      await sleep(200);
      const high1 = await snap();
      await sleep(850);
      const high2 = await snap();
      const dHigh = (high2.genVal ?? 0) - (high1.genVal ?? 0);

      speedPassed = dHigh > dLow && dHigh >= dLow + 3;
      speedDetail = { dLow, dHigh };
    }
    checks.speedSlider = { passed: speedPassed, ...speedDetail };

    checks.noJsErrors = {
      passed: runtimeErrors.length === 0 && consoleErrors.length === 0,
      runtimeErrors,
      consoleErrors,
    };

    const allPassed = Object.values(checks).every((c) => c.passed === true);
    const failedNames = Object.entries(checks).filter(([, v]) => !v.passed).map(([k]) => k);
    return {
      correct: allPassed,
      status: allPassed ? 'passed' : 'failed',
      reason: allPassed ? 'all GoL behavioral checks passed' : `failed: ${failedNames.join(', ')}`,
      checks,
    };
  } catch (err) {
    return { correct: false, status: 'not_evaluated', reason: String(err?.message || err), checks };
  } finally {
    chrome.kill('SIGKILL');
    srv.close();
    fs.rmSync(userDir, { recursive: true, force: true });
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const target = process.argv[2];
  if (!target) {
    console.error('Usage: check_gol_behavioral.mjs <wsDir>');
    process.exit(2);
  }
  const res = await evaluateGolBehavioral(path.resolve(target));
  console.log(JSON.stringify(res, null, 2));
  process.exit(res.correct ? 0 : res.status === 'not_evaluated' ? 2 : 1);
}
