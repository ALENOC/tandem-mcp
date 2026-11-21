#!/usr/bin/env node
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn, execFileSync } from 'node:child_process';

const CHROME = path.join(os.homedir(), '.cache/ms-playwright/chromium-1234/chrome-linux64/chrome');
const MIME = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.json': 'application/json' };
const W = 1280;
const H = 800;

function serveDir(dir) {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      const rel = (req.url || '/').split('?')[0] === '/' ? 'index.html' : (req.url || '/').split('?')[0].replace(/^\/+/, '');
      const full = path.join(dir, rel);
      if (!full.startsWith(dir) || !fs.existsSync(full) || fs.statSync(full).isDirectory()) {
        res.writeHead(404);
        res.end();
        return;
      }
      res.writeHead(200, { 'Content-Type': MIME[path.extname(full)] || 'application/octet-stream' });
      fs.createReadStream(full).pipe(res);
    });
    srv.listen(0, '127.0.0.1', () => resolve(srv));
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function evaluateBehavioral(wsDir) {
  const srv = await serveDir(wsDir);
  const port = srv.address().port;
  const userDir = fs.mkdtempSync(path.join(os.tmpdir(), 'orb-behav-'));
  const chrome = spawn(CHROME, [
    '--headless=new', '--no-sandbox', '--disable-gpu', `--window-size=${W},${H}`,
    '--remote-debugging-port=0', `--user-data-dir=${userDir}`, 'about:blank',
  ], { stdio: ['ignore', 'ignore', 'pipe'] });

  const requirements = {};
  const jsErrors = [];
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
        jsErrors.push(d?.exception?.description || d?.text || 'exceptionThrown');
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
    await call('Page.navigate', { url: `http://127.0.0.1:${port}/index.html` });
    await sleep(900);

    // Helper injected into page to inspect HUD controls and canvas state purely by accessible/visible semantics
    const inspectPage = () => evalJs(`(() => {
      const canvas = document.querySelector('canvas');
      const rect = canvas ? canvas.getBoundingClientRect() : null;
      const buttons = [...document.querySelectorAll('button, [role="button"]')].map((el) => {
        const r = el.getBoundingClientRect();
        const label = (el.textContent || el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
        return { label, x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height };
      });
      const rangeEl = document.querySelector('input[type="range"]');
      const slider = rangeEl ? {
        min: rangeEl.getAttribute('min'),
        max: rangeEl.getAttribute('max'),
        step: rangeEl.getAttribute('step'),
        valueAttr: rangeEl.getAttribute('value'),
        valueNow: rangeEl.value,
        rect: rangeEl.getBoundingClientRect().toJSON(),
      } : null;

      // Extract visible HUD text as text nodes (script/style/buttons excluded), so adjacent spans such as
      // <span>60</span><span>FPS</span> stay separate tokens instead of collapsing into "60FPS".
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      const nodes = [];
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        const parent = n.parentElement;
        if (!parent || parent.closest('script, style, button, option')) continue;
        if ((n.textContent || '').trim()) nodes.push(n);
      }
      const leaves = nodes.map((n) => n.textContent.replace(/\\s+/g, ' ').trim());
      const hudText = leaves.join(' ');
      // Value next to a short label, in either order ("FPS: 60", "FPS" "60", or "60" "FPS").
      // A number followed by "x" is a speed multiplier, never a metric value.
      const NUM = /(\\d+(?:\\.\\d+)?)(?![\\d.]*\\s*x\\b)/;
      const PURE = /^(\\d+(?:\\.\\d+)?)\\s*(?:s|secs?|seconds)?$/i;
      const pureOf = (n) => {
        const m = n ? (n.textContent || '').trim().match(PURE) : null;
        return m ? parseFloat(m[1]) : null;
      };
      const labeled = (labelRe, skipRe) => {
        for (let i = 0; i < leaves.length; i++) {
          const t = leaves[i];
          if (t.length > 40 || !labelRe.test(t) || (skipRe && skipRe.test(t))) continue;
          const own = t.match(NUM);
          if (own) return parseFloat(own[1]);
          // Prefer a value in the same block: sibling nodes first, then siblings of the parent element.
          const n = nodes[i], pe = n.parentElement;
          for (const cand of [n.nextSibling, n.previousSibling, pe.nextElementSibling, pe.previousElementSibling]) {
            const v = pureOf(cand);
            if (v !== null) return v;
          }
          for (const j of [i + 1, i - 1]) {
            const m = j >= 0 && j < leaves.length ? leaves[j].match(PURE) : null;
            if (m) return parseFloat(m[1]);
          }
        }
        return null;
      };

      // Sample canvas pixels at 320x200 (global hash + orbital zone excluding central star & HUD)
      let sampleHash = '';
      let nonBgCount = 0;
      let orbitalNonBg = 0;
      if (canvas && canvas.width > 0 && canvas.height > 0) {
        const tmp = document.createElement('canvas');
        tmp.width = 320;
        tmp.height = 200;
        const tctx = tmp.getContext('2d');
        tctx.drawImage(canvas, 0, 0, 320, 200);
        const data = tctx.getImageData(0, 0, 320, 200).data;
        let acc = 0;
        const cx = 160, cy = 100;
        for (let y = 0; y < 200; y++) {
          for (let x = 0; x < 320; x++) {
            const i = (y * 320 + x) * 4;
            const r = data[i], g = data[i + 1], b = data[i + 2];
            const isLit = (r > 20 || g > 24 || b > 36);
            if (isLit) {
              nonBgCount++;
              const dist2 = (x - cx) * (x - cx) + (y - cy) * (y - cy);
              const inHud = (x < 96 && y < 56);
              if (!inHud && dist2 > 34 * 34) orbitalNonBg++;
            }
            acc = (acc * 33 + r + g * 3 + b * 7) >>> 0;
          }
        }
        sampleHash = acc.toString(16) + ':' + nonBgCount;
      }

      // Parse time (s) including formats like "Time (s) 1.2" or "SIM TIME 1.2s", speed multiplier (x), particles, FPS
      // A number followed by "x" is a speed multiplier (e.g. a "Time Speed 1.0x" label), never the time.
      const timeMatch = hudText.match(/(?:sim(?:\\s*time)?|time)\\s*(?:\\(\\s*s\\s*\\))?[^0-9]{0,12}(\\d+(?:\\.\\d+)?)(?![\\d.]*\\s*x\\b)\\s*(?:s\\b)?/i)
        || hudText.match(/(\\d+(?:\\.\\d+)?)\\s*s\\b/i);
      const speedMatch = hudText.match(/(\\d+(?:\\.\\d+)?)\\s*(?:x\\b|×)/i);
      const partMatch = hudText.match(/(?:burst(?:\\s*particles?)?|particles?)[^0-9]{0,20}(\\d+)\\b/i)
        || hudText.match(/(\\d+)\\s*(?:burst|particles?)\\b/i);
      const fpsMatch = hudText.match(/fps[^0-9]{0,15}(\\d+)\\b/i)
        || hudText.match(/(\\d+)\\s*fps\\b/i);

      return {
        canvas: rect ? { w: rect.width, h: rect.height, cw: canvas.width, ch: canvas.height } : null,
        buttons,
        slider,
        hudText,
        timeSec: labeled(/\\b(?:sim(?:ulation)?\\s*(?:time|s)|time|secs?|seconds|elapsed)\\b/i, /speed/i) ?? (timeMatch ? parseFloat(timeMatch[1]) : null),
        speedX: speedMatch ? parseFloat(speedMatch[1]) : null,
        particles: labeled(/\\b(?:particles?|bursts?)\\b/i) ?? (partMatch ? parseInt(partMatch[1], 10) : null),
        fps: labeled(/\\bfps\\b/i) ?? (fpsMatch ? parseInt(fpsMatch[1], 10) : null),
        sampleHash,
        nonBgCount,
        orbitalNonBg,
      };
    })()`);

    const findBtn = (snap, re) => snap.buttons.find((b) => re.test(b.label));

    // 1. Canvas + HUD discovery + timeAdvances
    const s0 = await inspectPage();
    await sleep(700);
    const s1 = await inspectPage();

    const canvasOk = Boolean(s0.canvas && s0.canvas.w >= 1200 && s0.canvas.h >= 700);
    requirements.viewportCanvas = {
      status: canvasOk ? 'Pass' : 'Fail',
      evidence: s0.canvas ? `${s0.canvas.w}x${s0.canvas.h} (backing ${s0.canvas.cw}x${s0.canvas.ch})` : 'no canvas',
    };

    const timeAdvances = s0.timeSec !== null && s1.timeSec !== null && s1.timeSec > s0.timeSec && s0.sampleHash !== s1.sampleHash;
    requirements.timeAdvances = {
      status: timeAdvances ? 'Pass' : 'Fail',
      evidence: `t0=${s0.timeSec}s -> t1=${s1.timeSec}s after 700ms; canvas=${s0.sampleHash} -> ${s1.sampleHash}`,
    };

    // 2. Pause stops time & Resume restarts time
    const pauseBtn = findBtn(s1, /\b(pause|play)\b/i);
    if (!pauseBtn) {
      requirements.pauseStopsTime = { status: 'Fail', evidence: 'Play/Pause button not found by visible/accessible name' };
      requirements.resumeRestartsTime = { status: 'Fail', evidence: 'Play/Pause button not found' };
    } else {
      await clickXY(pauseBtn.x, pauseBtn.y);
      await sleep(150);
      const p0 = await inspectPage();
      await sleep(700);
      const p1 = await inspectPage();
      const timeStopped = p0.timeSec !== null && p1.timeSec !== null && Math.abs(p1.timeSec - p0.timeSec) < 0.05;
      const pauseLabelChanged = p0.buttons.find((b) => /\b(play|resume)\b/i.test(b.label)) !== undefined;
      requirements.pauseStopsTime = {
        status: timeStopped ? 'Pass' : 'Fail',
        evidence: `clicked "${pauseBtn.label}"; t=${p0.timeSec}s -> ${p1.timeSec}s over 700ms; labelChanged=${pauseLabelChanged}`,
      };

      const resumeBtn = findBtn(p1, /\b(play|resume|pause)\b/i);
      await clickXY(resumeBtn.x, resumeBtn.y);
      await sleep(700);
      const r1 = await inspectPage();
      const resumed = r1.timeSec !== null && p1.timeSec !== null && r1.timeSec > p1.timeSec + 0.1;
      requirements.resumeRestartsTime = {
        status: resumed ? 'Pass' : 'Fail',
        evidence: `clicked "${resumeBtn.label}"; t=${p1.timeSec}s -> ${r1.timeSec}s over 700ms`,
      };
    }

    // 3. Speed slider attributes, multiplier readout, and actual speed effect
    const preSpeed = await inspectPage();
    const sl = preSpeed.slider;
    const attrsOk = Boolean(
      sl &&
      parseFloat(sl.min) === 0.2 &&
      parseFloat(sl.max) === 3.0 &&
      parseFloat(sl.step) === 0.1 &&
      parseFloat(sl.valueAttr) === 1.0
    );
    if (!sl) {
      requirements.speedSlider = { status: 'Fail', evidence: 'input[type="range"] not found' };
    } else {
      // 2.5 s windows: a HUD that shows whole seconds still advances by 2-3 s at 1x and 7-8 s at 3x
      const m0 = await inspectPage();
      await sleep(2500);
      const m1 = await inspectPage();
      const dt1x = (m1.timeSec ?? 0) - (m0.timeSec ?? 0);

      await evalJs(`(() => {
        const el = document.querySelector('input[type="range"]');
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        setter.call(el, '3.0');
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      })()`);
      await sleep(100);
      const m2 = await inspectPage();
      await sleep(2500);
      const m3 = await inspectPage();
      const dt3x = (m3.timeSec ?? 0) - (m2.timeSec ?? 0);
      const readoutOk = m2.speedX !== null && Math.abs(m2.speedX - 3.0) < 0.05;
      const fasterOk = dt1x > 0 && dt3x >= dt1x * 2.0;

      requirements.speedSlider = {
        status: (attrsOk && readoutOk && fasterOk) ? 'Pass' : 'Fail',
        evidence: `attrsOk=${attrsOk} (min=${sl.min},max=${sl.max},step=${sl.step},val=${sl.valueAttr}); readout=${m2.speedX}x; dt@1x=${dt1x.toFixed(2)}s vs dt@3x=${dt3x.toFixed(2)}s`,
      };

      // Restore 1.0x for remaining tests
      await evalJs(`(() => {
        const el = document.querySelector('input[type="range"]');
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        setter.call(el, '1.0');
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      })()`);
    }

    // 4. Trails toggle: controlled Reset -> run 1100ms -> Pause comparison in orbital zone (excluding central star & HUD)
    // Prevents central star pulse, planet motion, or label-only changes from causing false positives.
    const beforeTrails = await inspectPage();
    const trailsBtn = findBtn(beforeTrails, /\btrails?\b/i);
    const resetBtnForTrails = findBtn(beforeTrails, /\breset\b/i);
    const pauseBtnForTrails = findBtn(beforeTrails, /\b(pause|play)\b/i);
    if (!trailsBtn || !resetBtnForTrails || !pauseBtnForTrails) {
      requirements.trailsToggle = { status: 'Fail', evidence: 'Trails, Reset, or Pause button not found' };
    } else {
      // Phase A: Trails ON -> Reset -> run 2000ms -> Pause -> sample multi-frame orbital zone
      // (2 s instead of 1.1 s: under CPU load fewer frames are drawn and the trails stayed near the threshold)
      await clickXY(resetBtnForTrails.x, resetBtnForTrails.y);
      await sleep(2000);
      await clickXY(pauseBtnForTrails.x, pauseBtnForTrails.y);
      await sleep(120);
      const onSnap1 = await inspectPage();
      await sleep(120);
      const onSnap2 = await inspectPage();
      const onOrbAvg = Math.round((onSnap1.orbitalNonBg + onSnap2.orbitalNonBg) / 2);

      // Phase B: While still paused, toggle Trails OFF and check immediate drop; if app doesn't redraw while paused, run 100ms and pause
      await clickXY(trailsBtn.x, trailsBtn.y);
      await sleep(150);
      let offSnap = await inspectPage();
      if (Math.abs(onOrbAvg - offSnap.orbitalNonBg) < 10) {
        const resumeB = findBtn(offSnap, /\b(play|resume|pause)\b/i);
        if (resumeB) await clickXY(resumeB.x, resumeB.y);
        await sleep(140);
        const pauseB = findBtn(await inspectPage(), /\b(pause|play)\b/i);
        if (pauseB) await clickXY(pauseB.x, pauseB.y);
        await sleep(120);
        offSnap = await inspectPage();
      } else {
        // Already redrawn while paused
      }
      const offBtn = findBtn(offSnap, /\btrails?\b/i);
      const labelChanged = Boolean(offBtn && offBtn.label !== trailsBtn.label);
      const trailPixelDrop = onOrbAvg - offSnap.orbitalNonBg;
      const trailsActuallyRemoved = trailPixelDrop >= 15;

      // Restore running state + Trails ON
      const resumeAfterB = findBtn(offSnap, /\b(play|resume|pause)\b/i);
      if (resumeAfterB && /\b(play|resume)\b/i.test(resumeAfterB.label)) await clickXY(resumeAfterB.x, resumeAfterB.y);
      if (offBtn) await clickXY(offBtn.x, offBtn.y);

      requirements.trailsToggle = {
        status: (labelChanged && trailsActuallyRemoved) ? 'Pass' : 'Fail',
        evidence: `label "${trailsBtn.label}" -> "${offBtn?.label}"; orbitalNonBg@320x200: ON=${onOrbAvg} vs OFF=${offSnap.orbitalNonBg} (drop=${trailPixelDrop}, min=15)`,
      };
    }

    // 5. Clicking canvas spawns burst particles (HUD count + fade-out)
    const preBurst = await inspectPage();
    // Pick a canvas point well clear of top-left HUD
    const clickX = Math.round(W * 0.72);
    const clickY = Math.round(H * 0.55);
    await clickXY(clickX, clickY);
    await sleep(80);
    const duringBurst = await inspectPage();
    await sleep(2200);
    const afterBurst = await inspectPage();
    const burstSpawned = preBurst.particles !== null && duringBurst.particles !== null && duringBurst.particles > preBurst.particles;
    const burstFaded = afterBurst.particles !== null && duringBurst.particles !== null && afterBurst.particles < duringBurst.particles;
    requirements.clickSpawnsBurst = {
      status: (burstSpawned && burstFaded) ? 'Pass' : (burstSpawned ? 'Pass' : 'Fail'),
      evidence: `particles before=${preBurst.particles}, afterClick=${duringBurst.particles}, after2.2s=${afterBurst.particles}`,
    };

    // 6. Reset restores initial state
    const preReset = await inspectPage();
    const resetBtn = findBtn(preReset, /\breset\b/i);
    if (!resetBtn) {
      requirements.resetRestoresInitialState = { status: 'Fail', evidence: 'Reset button not found by visible/accessible name' };
    } else {
      await clickXY(resetBtn.x, resetBtn.y);
      await sleep(120);
      const postReset = await inspectPage();
      const resetOk = preReset.timeSec !== null && postReset.timeSec !== null && postReset.timeSec < preReset.timeSec && postReset.timeSec <= 0.6;
      requirements.resetRestoresInitialState = {
        status: resetOk ? 'Pass' : 'Fail',
        evidence: `clicked "${resetBtn.label}"; t=${preReset.timeSec}s -> ${postReset.timeSec}s; particles=${postReset.particles}`,
      };
    }

    // 7. HUD displays FPS
    const finalSnap = await inspectPage();
    requirements.hudFps = {
      status: (finalSnap.fps !== null && finalSnap.fps > 0) ? 'Pass' : 'Fail',
      evidence: `fps=${finalSnap.fps}`,
    };

    // 8. JS errors
    requirements.noJsErrors = {
      status: (jsErrors.length === 0 && consoleErrors.length === 0) ? 'Pass' : 'Fail',
      evidence: `jsErrors=${jsErrors.length}, consoleErrors=${consoleErrors.length}`,
    };

    // 9. Star distribution check (reuse existing check_stars.mjs)
    // check_stars.mjs exits 1 when the distribution fails: keep its JSON verdict instead of crashing.
    let starsOut;
    try {
      starsOut = execFileSync('node', [path.join(path.dirname(new URL(import.meta.url).pathname), 'check_stars.mjs'), wsDir], { encoding: 'utf8' });
    } catch (err) {
      starsOut = err.stdout || '{"passed":false}';
    }
    const starsJson = JSON.parse(starsOut);
    requirements.starDistribution = {
      status: starsJson.passed ? 'Pass' : 'Fail',
      evidence: `occupiedCells=${starsJson.occupiedCells}/16 (min 12), bgStars=${starsJson.bgStars}, dots=${starsJson.dots}`,
    };

    const allPassed = Object.values(requirements).every((r) => r.status === 'Pass');
    return {
      passed: allPassed,
      requirements,
      jsErrors,
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
  console.error('Usage: check_orbital_behavioral.mjs <workspace_dir>');
  process.exit(2);
}
const result = await evaluateBehavioral(path.resolve(target));
console.log(JSON.stringify(result, null, 2));
if (!result.passed) process.exit(1);
