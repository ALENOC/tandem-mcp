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

function dist(a, b) {
  if (!a || !b || a.cx === null || b.cx === null) return Infinity;
  return Math.hypot(a.cx - b.cx, a.cy - b.cy);
}

export async function evaluatePendulumV2(wsDir) {
  const indexPath = path.join(wsDir, 'index.html');
  if (!fs.existsSync(indexPath)) {
    return { correct: false, status: 'failed', reason: 'index.html missing', checks: {} };
  }
  const htmlRaw = fs.readFileSync(indexPath, 'utf-8');
  const extMatch = htmlRaw.match(/<(?:script|link|img)[^>]+(?:src|href)\s*=\s*["']https?:\/\//i);
  if (extMatch) {
    return { correct: false, status: 'failed', reason: `external dependency found: ${extMatch[0].slice(0, 80)}`, checks: {} };
  }

  const chromePath = findChrome();
  if (!chromePath) {
    return { correct: false, status: 'not_evaluated', reason: 'Chromium binary not found', checks: {} };
  }

  const srv = await serveDir(wsDir);
  const port = srv.address().port;
  const baseUrl = `http://127.0.0.1:${port}/`;
  const userDir = fs.mkdtempSync(path.join(os.tmpdir(), 'pendulum-v2-'));
  const chrome = spawn(chromePath, [
    '--headless=new', '--no-sandbox', '--disable-gpu', `--window-size=${W},${H}`,
    '--remote-debugging-port=0', `--user-data-dir=${userDir}`, 'about:blank',
  ], { stdio: ['ignore', 'ignore', 'pipe'] });

  const runtimeErrors = [];
  const consoleErrors = [];
  const checks = {};

  try {
    const wsUrl = await new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error('DevTools timeout')), 10000);
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
        runtimeErrors.push(String(msg.params?.exceptionDetails?.text || 'Uncaught exception'));
      } else if (msg.method === 'Runtime.consoleAPICalled' && msg.params?.type === 'error') {
        consoleErrors.push((msg.params.args || []).map((a) => a.value ?? a.description ?? '').join(' ').slice(0, 200));
      }
    });

    const evalJs = async (expression) => {
      const res = await call('Runtime.evaluate', { expression, returnByValue: true });
      if (res.exceptionDetails) throw new Error(res.exceptionDetails.text || 'eval error');
      return res.result?.value;
    };

    const clickXY = async (x, y) => {
      await call('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
      await call('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
    };

    await call('Page.enable');
    await call('Runtime.enable');
    await call('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });
    await call('Page.navigate', { url: `${baseUrl}index.html` });
    await sleep(600);

    // Measure canvas and isolate brightest moving mass pixels outside HUD overlays
    const snap = async () => evalJs(`(() => {
      const c = document.querySelector('canvas');
      const cr = c ? c.getBoundingClientRect() : null;
      const hudRects = [];
      for (const el of document.querySelectorAll('body *')) {
        if (el === c || el.contains(c)) continue;
        const r = el.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0 || r.width > 1200) continue;
        const st = getComputedStyle(el);
        const hasOverlay = st.position === 'fixed' || st.position === 'absolute' || (st.backdropFilter || '').includes('blur(') || el.tagName === 'BUTTON' || el.tagName === 'INPUT';
        if (hasOverlay) hudRects.push({ l: r.left, t: r.top, r: r.right, b: r.bottom });
      }
      const inHud = (px, py) => {
        for (const hr of hudRects) {
          if (px >= hr.l - 4 && px <= hr.r + 4 && py >= hr.t - 4 && py <= hr.b + 4) return true;
        }
        return false;
      };

      let canvasInfo = { exists: false };
      let mass = { cx: null, cy: null, count: 0, maxLum: 0 };
      if (c && c.width > 0 && c.height > 0) {
        const sw = 240, sh = 150;
        const tmp = document.createElement('canvas');
        tmp.width = sw; tmp.height = sh;
        const tctx = tmp.getContext('2d');
        tctx.drawImage(c, 0, 0, sw, sh);
        const d = tctx.getImageData(0, 0, sw, sh).data;
        let hash = 0, bright = 0, bgMatch = 0, maxLum = 0;
        const pts = [];
        for (let py = 0; py < sh; py++) {
          const wy = cr.top + (py + 0.5) * (cr.height / sh);
          for (let px = 0; px < sw; px++) {
            const wx = cr.left + (px + 0.5) * (cr.width / sw);
            if (inHud(wx, wy)) continue;
            const idx = (py * sw + px) * 4;
            const r = d[idx], g = d[idx + 1], b = d[idx + 2];
            hash = (hash * 33 + r + g * 3 + b * 7) >>> 0;
            if (Math.abs(r - 9) <= 6 && Math.abs(g - 13) <= 6 && Math.abs(b - 22) <= 6) bgMatch++;
            if (r > 30 || g > 30 || b > 45) bright++;
            const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
            if (lum > maxLum) maxLum = lum;
            pts.push([px / sw, py / sh, lum]);
          }
        }
        const thresh = Math.max(70, maxLum * 0.55);
        let sx = 0, sy = 0, wsum = 0, cnt = 0;
        for (const [nx, ny, lum] of pts) {
          if (lum >= thresh) {
            const w = lum - thresh + 1;
            sx += nx * w; sy += ny * w; wsum += w; cnt++;
          }
        }
        if (wsum > 0) mass = { cx: sx / wsum, cy: sy / wsum, count: cnt, maxLum: Math.round(maxLum) };
        canvasInfo = { exists: true, w: cr.width, h: cr.height, hash: hash.toString(16), bright, bgMatch, bgCss: getComputedStyle(c).backgroundColor };
      }

      const bodyBg = getComputedStyle(document.body).backgroundColor;
      let hasGlass = false;
      for (const el of document.querySelectorAll('*')) {
        const st = getComputedStyle(el);
        const bf = st.backdropFilter || st.webkitBackdropFilter || '';
        if (bf.includes('blur(') && (st.backgroundColor.includes('rgba(') || st.backgroundColor.includes('hsla(') || st.backgroundColor.includes('/'))) {
          hasGlass = true; break;
        }
      }
      const bodyText = (document.body.innerText || '').replace(/\\s+/g, ' ');
      const extractNum = (pats) => {
        for (const p of pats) { const m = bodyText.match(p); if (m) return Number(m[1].replace(/,/g, '')); }
        return null;
      };
      const fpsVal = extractNum([/fps\\s*[:\\-]?\\s*(\\d+(?:\\.\\d+)?)/i, /(\\d+(?:\\.\\d+)?)\\s*fps\\b/i]);
      const speedVal = extractNum([/(?:speed|velocit[àa])\\s*[:\\-]?\\s*(\\d+(?:\\.\\d+)?)/i]);
      const btns = Array.from(document.querySelectorAll('button, [role="button"]')).map((b) => {
        const r = b.getBoundingClientRect();
        return { text: (b.innerText || b.textContent || b.getAttribute('aria-label') || '').trim(), x: r.left + r.width / 2, y: r.top + r.height / 2, visible: r.width > 0 && r.height > 0 };
      }).filter((b) => b.visible);
      const sliderEl = document.querySelector('input[type="range"]');
      const slider = sliderEl ? { min: Number(sliderEl.min || 0), max: Number(sliderEl.max || 100), val: Number(sliderEl.value) } : null;
      return { canvas: canvasInfo, mass, bodyBg, hasGlass, fpsVal, speedVal, btns, slider };
    })()`);

    const s0 = await snap();
    await sleep(350);
    const s0b = await snap();

    const isBg090d16 = (bg) => /rgba?\(\s*9\s*,\s*13\s*,\s*22/.test(bg || '');
    const bgOk = isBg090d16(s0.bodyBg) || isBg090d16(s0.canvas.bgCss) || s0.canvas.bgMatch > 10000;
    checks.layoutAndTheme = {
      passed: s0.canvas.exists && s0.canvas.w >= 1200 && s0.canvas.h >= 700 && bgOk && s0.canvas.bright > 10,
      w: s0.canvas.w, h: s0.canvas.h, bgOk,
    };
    checks.glassmorphismHud = {
      passed: s0.hasGlass && s0.fpsVal !== null && s0.speedVal !== null,
      hasGlass: s0.hasGlass, fpsVal: s0.fpsVal, speedVal: s0.speedVal,
    };

    const btnPlayPause = s0.btns.find((b) => /\b(play|pause|resume|avvia)\b/i.test(b.text));
    const btnStep = s0.btns.find((b) => /\bstep\b/i.test(b.text));
    const btnReset = s0.btns.find((b) => /\breset\b/i.test(b.text));

    checks.controlsPresent = {
      passed: Boolean(btnPlayPause && btnStep && btnReset && s0.slider && s0.slider.min <= 0.5 && s0.slider.max >= 3.0),
      playPause: btnPlayPause?.text || null, step: btnStep?.text || null, reset: btnReset?.text || null, slider: s0.slider,
    };
    checks.startsPaused = {
      passed: Boolean(btnPlayPause && /\b(play|start|avvia)\b/i.test(btnPlayPause.text)) && s0.canvas.hash === s0b.canvas.hash,
      buttonText: btnPlayPause?.text || null, hashStatic: s0.canvas.hash === s0b.canvas.hash,
    };

    // 1. Click on canvas to set a recognizable off-center angle
    const canvasPt = await evalJs(`(() => {
      const c = document.querySelector('canvas');
      if (!c) return null;
      const r = c.getBoundingClientRect();
      for (const [fx, fy] of [[0.72, 0.35], [0.28, 0.35], [0.70, 0.65]]) {
        const x = Math.round(r.left + r.width * fx), y = Math.round(r.top + r.height * fy);
        if (document.elementFromPoint(x, y) === c) return { x, y };
      }
      return null;
    })()`);

    let pUser = null;
    if (canvasPt) {
      await clickXY(canvasPt.x, canvasPt.y);
      await sleep(120);
      const sUser = await snap();
      pUser = sUser.mass;
      checks.clickCanvas = {
        passed: sUser.canvas.hash !== s0b.canvas.hash && dist(pUser, s0.mass) > 0.01,
        distFromOrig: Number(dist(pUser, s0.mass).toFixed(4)),
      };
    } else {
      checks.clickCanvas = { passed: false, reason: 'no safe canvas point' };
    }

    // 2. Step from non-equilibrium user angle -> verify physical advancement
    let stepPassed = false;
    if (btnStep) {
      const preStep = await snap();
      await clickXY(btnStep.x, btnStep.y);
      await sleep(120);
      const postStep = await snap();
      const dStep = dist(postStep.mass, preStep.mass);
      stepPassed = postStep.canvas.hash !== preStep.canvas.hash && dStep > 0.0005;
      checks.step = { passed: stepPassed, hashChanged: postStep.canvas.hash !== preStep.canvas.hash, massDelta: Number(dStep.toFixed(5)) };
    } else {
      checks.step = { passed: false };
    }

    // 3. Play -> evolve to distinguishable position -> Pause -> verify frozen
    let sEvolved1 = null;
    if (btnPlayPause) {
      const pBtn = (await snap()).btns.find((b) => /\b(play|pause|resume|avvia)\b/i.test(b.text));
      const beforePlay = await snap();
      await clickXY(pBtn.x, pBtn.y);
      await sleep(500);
      const midPlay = await snap();
      await sleep(450);
      const afterPlay = await snap();
      const playMoved = beforePlay.canvas.hash !== midPlay.canvas.hash && midPlay.canvas.hash !== afterPlay.canvas.hash;
      checks.play = { passed: playMoved };

      const pauseBtn = afterPlay.btns.find((b) => /\b(play|pause|resume|pausa)\b/i.test(b.text));
      await clickXY(pauseBtn.x, pauseBtn.y);
      await sleep(180);
      sEvolved1 = await snap();
      await sleep(450);
      const sEvolved2 = await snap();
      const dPause = dist(sEvolved1.mass, sEvolved2.mass);
      checks.pause = {
        passed: sEvolved1.canvas.hash === sEvolved2.canvas.hash && dPause < 0.002,
        hashSame: sEvolved1.canvas.hash === sEvolved2.canvas.hash,
        massDrift: Number(dPause.toFixed(5)),
      };
    } else {
      checks.play = { passed: false };
      checks.pause = { passed: false };
    }

    // 4. Reset semantics: distinguish reset_to_original vs reset_to_user_angle vs inert vs arbitrary
    if (btnReset && sEvolved1) {
      await clickXY(btnReset.x, btnReset.y);
      await sleep(180);
      const sReset = await snap();
      const dOrig = dist(sReset.mass, s0.mass);
      const dUser = dist(sReset.mass, pUser);
      const dEvolved = dist(sReset.mass, sEvolved1.mass);

      let semantics = 'defect_arbitrary';
      let resetPassed = false;
      if (dEvolved <= 0.005 && sReset.canvas.hash === sEvolved1.canvas.hash) {
        semantics = 'defect_inert';
      } else if (dOrig <= 0.03) {
        semantics = 'valid_reset_to_original';
        resetPassed = true;
      } else if (dUser <= 0.03) {
        semantics = 'valid_reset_to_user_angle';
        resetPassed = true;
      }
      checks.reset = {
        passed: resetPassed,
        semantics,
        distToOrig: Number(dOrig.toFixed(4)),
        distToUser: Number(dUser.toFixed(4)),
        distFromEvolved: Number(dEvolved.toFixed(4)),
      };
    } else {
      checks.reset = { passed: false, semantics: 'missing_button' };
    }

    // 5. Speed slider
    let speedPassed = false;
    if (s0.slider) {
      await evalJs(`(() => {
        const el = document.querySelector('input[type="range"]');
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, '2.5');
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      })()`);
      await sleep(120);
      const sSp = await snap();
      speedPassed = sSp.speedVal !== null && Math.abs(sSp.speedVal - 2.5) < 0.15;
    }
    checks.speedSlider = { passed: speedPassed };
    checks.noJsErrors = { passed: runtimeErrors.length === 0 && consoleErrors.length === 0, runtimeErrors, consoleErrors };

    const allPassed = Object.values(checks).every((c) => c.passed === true);
    const failedNames = Object.entries(checks).filter(([, v]) => !v.passed).map(([k]) => k);
    return { correct: allPassed, status: allPassed ? 'passed' : 'failed', reason: allPassed ? 'all Pendulum v2 checks passed' : `failed: ${failedNames.join(', ')}`, checks };
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
  if (!target) { console.error('Usage: check_pendulum_v2.mjs <wsDir>'); process.exit(2); }
  const res = await evaluatePendulumV2(path.resolve(target));
  console.log(JSON.stringify(res, null, 2));
  process.exit(res.correct ? 0 : res.status === 'not_evaluated' ? 2 : 1);
}
