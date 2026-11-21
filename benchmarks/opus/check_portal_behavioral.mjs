#!/usr/bin/env node
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn, execFileSync } from 'node:child_process';

const CHROME = process.env.TANDEM_CHROME || process.env.CHROME || path.join(os.homedir(), '.cache/ms-playwright/chromium-1234/chrome-linux64/chrome');
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

function serveDir(dir) {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      const rel = (req.url || '/').split('?')[0] === '/' ? 'index.html' : (req.url || '/').split('?')[0].replace(/^\/+/, '');
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

async function evaluatePortalBehavioral(wsDir) {
  if (!fs.existsSync(path.join(wsDir, 'index.html'))) {
    return {
      functional_passed: false,
      visual_passed: false,
      startup: { status: 'failed', evidence: 'index.html missing' },
      canvasMotion: { status: 'failed', evidence: 'index.html missing' },
      interactions: { status: 'failed', evidence: 'index.html missing' },
      visual: { status: 'failed', evidence: 'index.html missing' },
      runtimeErrors: [],
      consoleErrors: [],
    };
  }
  if (!CHROME || !fs.existsSync(CHROME)) {
    return {
      functional_passed: false,
      visual_passed: false,
      startup: { status: 'not_evaluated', reason: `Chromium not found: ${CHROME}` },
      canvasMotion: { status: 'not_evaluated', reason: 'Chromium unavailable' },
      interactions: { status: 'not_evaluated', reason: 'Chromium unavailable' },
      visual: { status: 'not_evaluated', reason: 'Chromium unavailable' },
      runtimeErrors: [],
      consoleErrors: [],
    };
  }

  const srv = await serveDir(wsDir);
  const port = srv.address().port;
  const baseUrl = `http://127.0.0.1:${port}/`;
  const userDir = fs.mkdtempSync(path.join(os.tmpdir(), 'portal-behav-'));
  const chrome = spawn(CHROME, [
    '--headless=new', '--no-sandbox', '--disable-gpu', `--window-size=${W},${H}`,
    '--remote-debugging-port=0', `--user-data-dir=${userDir}`, 'about:blank',
  ], { stdio: ['ignore', 'ignore', 'pipe'] });

  const runtimeErrors = [];
  const consoleErrors = [];

  try {
    const wsUrl = await new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error('DevTools timeout')), 10000);
      let b = '';
      chrome.stderr.on('data', (c) => {
        b += c;
        const m = b.match(/DevTools listening on (ws:\/\/\S+)/);
        if (m) { clearTimeout(t); resolve(m[1]); }
      });
    });
    const targets = await (await fetch(`http://127.0.0.1:${new URL(wsUrl).port}/json`)).json();
    const ws = new WebSocket(targets.find((t) => t.type === 'page').webSocketDebuggerUrl);
    await new Promise((r) => { ws.onopen = r; });

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
        const d = msg.params?.exceptionDetails;
        const frames = d?.stackTrace?.callFrames || [];
        let loc = d?.url || '';
        let line = typeof d?.lineNumber === 'number' ? d.lineNumber + 1 : null;
        if (frames.length > 0) {
          loc = frames[0].url || loc;
          line = typeof frames[0].lineNumber === 'number' ? frames[0].lineNumber + 1 : line;
        }
        if (loc.startsWith(baseUrl)) loc = loc.slice(baseUrl.length).replace(/^\/+/, '');
        const msgTxt = String(d?.exception?.description || d?.text || 'exception').split('\n')[0];
        runtimeErrors.push(`${msgTxt} (${loc}${line ? ':' + line : ''})`);
      } else if (msg.method === 'Runtime.consoleAPICalled' && msg.params?.type === 'error') {
        consoleErrors.push((msg.params.args || []).map((a) => a.value ?? a.description ?? '').join(' '));
      }
    });

    const evalJs = async (expression) => {
      const res = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
      if (res.exceptionDetails) throw new Error(res.exceptionDetails.exception?.description || res.exceptionDetails.text);
      return res.result?.value;
    };

    const clickXY = async (x, y) => {
      await call('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y, button: 'none' });
      await call('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
      await call('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
    };

    await call('Page.enable');
    await call('Runtime.enable');
    await call('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });
    await call('Page.navigate', { url: `${baseUrl}index.html` });
    await sleep(1100);

    const inspect = () => evalJs(`(() => {
      const c = document.querySelector('canvas');
      const r = c ? c.getBoundingClientRect() : null;
      let hash = '', nonZero = 0, fullSample = null, floorSample = null;
      if (c && c.width > 0 && c.height > 0) {
        const tmp = document.createElement('canvas');
        tmp.width = 160; tmp.height = 100;
        const ctx = tmp.getContext('2d');
        ctx.drawImage(c, 0, 0, 160, 100);
        const d = ctx.getImageData(0, 0, 160, 100).data;
        let acc = 0;
        const full = [];
        const floor = [];
        for (let y = 0; y < 100; y++) {
          for (let x = 0; x < 160; x++) {
            const i = (y * 160 + x) * 4;
            const lum = (d[i] + d[i + 1] + d[i + 2]);
            if (lum > 0) nonZero++;
            acc = (acc * 33 + d[i] + d[i + 1] * 3 + d[i + 2] * 7) >>> 0;
            if ((x & 1) === 0 && (y & 1) === 0) full.push(d[i], d[i + 1], d[i + 2]);
            if (y >= 74 && (x & 1) === 0) floor.push(d[i], d[i + 1], d[i + 2]);
          }
        }
        hash = acc.toString(16);
        fullSample = full;
        floorSample = floor;
      }
      const buttons = [...document.querySelectorAll('button, [role="button"]')].map((el) => {
        const br = el.getBoundingClientRect();
        return {
          label: (el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim(),
          x: br.left + br.width / 2,
          y: br.top + br.height / 2,
        };
      });
      const range = document.querySelector('input[type="range"]');
      const slider = range ? { min: range.min, max: range.max, step: range.step, value: range.value } : null;
      const clone = document.body.cloneNode(true);
      clone.querySelectorAll('script, style').forEach((n) => n.remove());
      const hudText = (clone.innerText || '').replace(/\\s+/g, ' ').trim();
      return {
        canvas: r ? { w: r.width, h: r.height, cw: c.width, ch: c.height, hash, nonZero, fullSample, floorSample } : null,
        buttons,
        slider,
        hudText,
      };
    })()`);

    const meanDiff = (a, b) => {
      if (!a || !b || a.length !== b.length || !a.length) return 0;
      let sum = 0;
      for (let i = 0; i < a.length; i++) sum += Math.abs(a[i] - b[i]);
      return sum / a.length;
    };

    const setSpeed = async (valStr) => {
      await evalJs(`(() => {
        const el = document.querySelector('input[type="range"]');
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        setter.call(el, ${JSON.stringify(String(valStr))});
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      })()`);
    };

    const s0 = await inspect();
    await sleep(450);
    const s1 = await inspect();
    const runningDiff = meanDiff(s0.canvas?.fullSample, s1.canvas?.fullSample);

    const startupOk = runtimeErrors.length === 0 && consoleErrors.length === 0;
    const startup = {
      status: startupOk ? 'passed' : 'failed',
      evidence: startupOk ? '0 runtime/console errors' : `errors=${runtimeErrors.concat(consoleErrors).join('; ')}`,
    };

    const motionOk = Boolean(s0.canvas && s0.canvas.cw > 0 && s0.canvas.ch > 0 && s0.canvas.hash !== s1.canvas.hash && runningDiff > 0.1);
    const canvasMotion = {
      status: motionOk ? 'passed' : 'failed',
      evidence: s0.canvas ? `size=${s0.canvas.cw}x${s0.canvas.ch}, diff=${runningDiff.toFixed(3)}, hash=${s0.canvas.hash}->${s1.canvas.hash}` : 'no canvas',
    };

    // Interactions by visible/accessible control names
    const findBtn = (snap, re) => snap.buttons.find((b) => re.test(b.label));
    const hudHasMetrics = /fps/i.test(s1.hudText) && /polys/i.test(s1.hudText) && /parts/i.test(s1.hudText);
    const pauseBtn = findBtn(s1, /\b(pause|play|resume)\b/i);
    const orbitBtn = findBtn(s1, /\borbit\b/i);
    const resetBtn = findBtn(s1, /\breset\b/i);
    const initialSpeed = s1.slider ? parseFloat(s1.slider.value) : null;
    const initialOrbitLabel = orbitBtn ? orbitBtn.label : null;
    const initialPauseLabel = pauseBtn ? pauseBtn.label : null;

    // 1. Pause must stop canvas progression; Resume must restart it
    let pauseOk = false, pauseEv = 'missing button';
    if (pauseBtn && motionOk) {
      await clickXY(pauseBtn.x, pauseBtn.y);
      await sleep(180);
      const p0 = await inspect();
      await sleep(450);
      const p1 = await inspect();
      const pauseDiff = meanDiff(p0.canvas?.fullSample, p1.canvas?.fullSample);
      const stopped = pauseDiff <= Math.max(0.05, runningDiff * 0.12);

      const resumeBtn = findBtn(p1, /\b(play|resume|pause)\b/i);
      if (resumeBtn) await clickXY(resumeBtn.x, resumeBtn.y);
      await sleep(180);
      const r0 = await inspect();
      await sleep(450);
      const r1 = await inspect();
      const resumeDiff = meanDiff(r0.canvas?.fullSample, r1.canvas?.fullSample);
      const restarted = resumeDiff > Math.max(0.15, pauseDiff * 2.5);
      pauseOk = stopped && restarted;
      pauseEv = `runDiff=${runningDiff.toFixed(2)}, pauseDiff=${pauseDiff.toFixed(2)}, resumeDiff=${resumeDiff.toFixed(2)}`;
    }

    const FULL_ORBIT_RATIO = Number(process.env.FULL_ORBIT_RATIO || 0.5);
    // 2. Orbit must change camera motion (isolated via perimeter cyber-grid floor band y >= 74%)
    let orbitOk = false, orbitEv = 'missing button';
    if (orbitBtn && motionOk) {
      const oOn0 = await inspect();
      await sleep(450);
      const oOn1 = await inspect();
      const floorDiffOn = meanDiff(oOn0.canvas?.floorSample, oOn1.canvas?.floorSample);
      const fullDiffOn = meanDiff(oOn0.canvas?.fullSample, oOn1.canvas?.fullSample);

      await clickXY(orbitBtn.x, orbitBtn.y);
      await sleep(180);
      const oOff0 = await inspect();
      await sleep(450);
      const oOff1 = await inspect();
      const floorDiffOff = meanDiff(oOff0.canvas?.floorSample, oOff1.canvas?.floorSample);
      const fullDiffOff = meanDiff(oOff0.canvas?.fullSample, oOff1.canvas?.fullSample);
      const ob1 = findBtn(oOff1, /\borbit\b/i);
      const labelChanged = Boolean(ob1 && ob1.label !== orbitBtn.label);
      // Primary signal: the floor band. When the camera sits low the floor is seen edge-on and that band
      // barely changes, so fall back to the whole frame: with the camera stopped only the crystals,
      // particles and rings still move, and the frame difference must drop clearly.
      const floorStopped = floorDiffOn > 0.15 && floorDiffOff <= floorDiffOn * 0.30;
      const fullStopped = fullDiffOn > 0.5 && fullDiffOff <= fullDiffOn * FULL_ORBIT_RATIO;
      const cameraStopped = floorStopped || fullStopped;
      orbitOk = labelChanged && cameraStopped;
      orbitEv = `label="${orbitBtn.label}"->"${ob1?.label}", floorDiffOn=${floorDiffOn.toFixed(3)}, floorDiffOff=${floorDiffOff.toFixed(3)}, fullDiffOn=${fullDiffOn.toFixed(3)}, fullDiffOff=${fullDiffOff.toFixed(3)}`;
      if (ob1 && labelChanged) await clickXY(ob1.x, ob1.y);
      await sleep(150);
    }

    // 3. Speed slider must change observed simulation velocity (low vs high speed frame-to-frame diff)
    let speedOk = false, speedEv = 'missing slider';
    if (s1.slider && motionOk) {
      const lowVal = parseFloat(s1.slider.min) || 0.2;
      const highVal = parseFloat(s1.slider.max) || 3.0;
      await setSpeed(lowVal);
      await sleep(180);
      const l0 = await inspect();
      await sleep(240);
      const l1 = await inspect();
      const diffLow = meanDiff(l0.canvas?.fullSample, l1.canvas?.fullSample);

      await setSpeed(highVal);
      await sleep(180);
      const h0 = await inspect();
      await sleep(240);
      const h1 = await inspect();
      const diffHigh = meanDiff(h0.canvas?.fullSample, h1.canvas?.fullSample);
      speedOk = diffHigh > diffLow * 1.25 && diffHigh > 0.2;
      speedEv = `diff@${lowVal}x=${diffLow.toFixed(3)} vs diff@${highVal}x=${diffHigh.toFixed(3)}`;
    }

    // 4. Reset: first dirty speed, orbit, and pause state; then click Reset and verify explicit prompt requirement
    //    (simulation resets and runs cleanly without errors) separately from extra control-reset criterion.
    let resetOk = false, resetControlsOk = false, resetEv = 'missing button';
    if (resetBtn) {
      if (s1.slider) await setSpeed(parseFloat(s1.slider.max) || 2.5);
      const preDirty = await inspect();
      const obDirty = findBtn(preDirty, /\borbit\b/i);
      if (obDirty && obDirty.label === initialOrbitLabel) await clickXY(obDirty.x, obDirty.y);
      const pbDirty = findBtn(await inspect(), /\b(pause|play|resume)\b/i);
      if (pbDirty && pbDirty.label === initialPauseLabel) await clickXY(pbDirty.x, pbDirty.y);
      await sleep(180);

      await clickXY(resetBtn.x, resetBtn.y);
      await sleep(200);
      const postReset0 = await inspect();
      await sleep(400);
      const postReset1 = await inspect();

      const speedRestored = !s1.slider || (postReset0.slider && Math.abs(parseFloat(postReset0.slider.value) - initialSpeed) < 0.05);
      const orbitRestored = !initialOrbitLabel || (findBtn(postReset0, /\borbit\b/i)?.label === initialOrbitLabel);
      const pauseRestored = !initialPauseLabel || (findBtn(postReset0, /\b(pause|play|resume)\b/i)?.label === initialPauseLabel);
      const animActiveAfterReset = meanDiff(postReset0.canvas?.fullSample, postReset1.canvas?.fullSample) > 0.1;
      resetOk = pauseRestored && animActiveAfterReset && runtimeErrors.length === 0;
      resetControlsOk = speedRestored && orbitRestored && pauseRestored && animActiveAfterReset;
      resetEv = `pauseRestored=${pauseRestored}, animAfterReset=${animActiveAfterReset}, extraControlsReset=${resetControlsOk} (speed=${speedRestored}, orbit=${orbitRestored})`;
    }

    const interactionsOk = hudHasMetrics && pauseOk && orbitOk && speedOk && resetOk && runtimeErrors.length === 0;
    const interactions = {
      status: interactionsOk ? 'passed' : 'failed',
      resetControlsOk,
      evidence: `hudMetrics=${hudHasMetrics}; pause=[${pauseEv}]; orbit=[${orbitEv}]; speed=[${speedEv}]; reset=[${resetEv}]`,
    };

    // Visual chromatic check (reuse check_portal_visual.mjs)
    let visual;
    try {
      const visScript = path.join(path.dirname(new URL(import.meta.url).pathname), 'check_portal_visual.mjs');
      let visRaw = '';
      try {
        visRaw = execFileSync('node', [visScript, wsDir], { encoding: 'utf8', timeout: 25000 });
      } catch (e) {
        visRaw = e.stdout ? String(e.stdout) : '';
      }
      const vj = JSON.parse(visRaw.trim().splitlines ? visRaw.trim() : visRaw.trim().split('\n').pop());
      visual = {
        status: vj.passed ? 'passed' : 'failed',
        ...vj,
      };
    } catch (e) {
      visual = { status: 'not_evaluated', reason: String(e.message || e) };
    }

    const functionalPassed = startup.status === 'passed' && canvasMotion.status === 'passed' && interactions.status === 'passed';
    const visualPassed = visual.status === 'passed';

    return {
      functional_passed: functionalPassed,
      visual_passed: visualPassed,
      startup,
      canvasMotion,
      interactions,
      visual,
      runtimeErrors,
      consoleErrors,
    };
  } catch (err) {
    return {
      functional_passed: false,
      visual_passed: false,
      startup: { status: 'not_evaluated', reason: String(err?.message || err) },
      canvasMotion: { status: 'not_evaluated', reason: 'probe error' },
      interactions: { status: 'not_evaluated', reason: 'probe error' },
      visual: { status: 'not_evaluated', reason: 'probe error' },
      runtimeErrors,
      consoleErrors,
    };
  } finally {
    chrome.kill('SIGKILL');
    srv.close();
    fs.rmSync(userDir, { recursive: true, force: true });
  }
}

const target = process.argv[2];
if (!target) {
  console.error('Usage: check_portal_behavioral.mjs <workspace_dir>');
  process.exit(2);
}
const res = await evaluatePortalBehavioral(path.resolve(target));
console.log(JSON.stringify(res, null, 2));
process.exit(res.functional_passed ? 0 : 1);
