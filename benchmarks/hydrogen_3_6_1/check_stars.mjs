import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';

const CHROME = path.join(os.homedir(), '.cache/ms-playwright/chromium-1234/chrome-linux64/chrome');
const MIME = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.json': 'application/json' };
const W = 1280;
const H = 800;

function serveDir(dir) {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      const rel = (req.url || '/').split('?')[0] === '/' ? 'index.html' : (req.url || '/').split('?')[0].replace(/^\/+/, '');
      const full = path.join(dir, rel);
      if (!full.startsWith(dir) || !fs.existsSync(full) || fs.statSync(full).isDirectory()) { res.writeHead(404); res.end(); return; }
      res.writeHead(200, { 'Content-Type': MIME[path.extname(full)] || 'application/octet-stream' });
      fs.createReadStream(full).pipe(res);
    });
    srv.listen(0, '127.0.0.1', () => resolve(srv));
  });
}

async function checkStars(wsDir) {
  const srv = await serveDir(wsDir);
  const port = srv.address().port;
  const userDir = fs.mkdtempSync(path.join(os.tmpdir(), 'stars-'));
  const chrome = spawn(CHROME, [
    '--headless=new', '--no-sandbox', '--disable-gpu', `--window-size=${W},${H}`,
    '--remote-debugging-port=0', `--user-data-dir=${userDir}`, 'about:blank',
  ], { stdio: ['ignore', 'ignore', 'pipe'] });

  try {
    const wsUrl = await new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error('DevTools timeout')), 10000);
      let b = '';
      chrome.stderr.on('data', (c) => { b += c; const m = b.match(/DevTools listening on (ws:\/\/\S+)/); if (m) { clearTimeout(t); resolve(m[1]); } });
    });
    const targets = await (await fetch(`http://127.0.0.1:${new URL(wsUrl).port}/json`)).json();
    const ws = new WebSocket(targets.find((t) => t.type === 'page').webSocketDebuggerUrl);
    await new Promise((r) => { ws.onopen = r; });
    let seq = 1;
    const call = (method, params = {}) => new Promise((res, rej) => {
      const id = seq++;
      const h = (ev) => {
        const d = JSON.parse(ev.data);
        if (d.id === id) { ws.removeEventListener('message', h); if (d.error) rej(new Error(d.error.message)); else res(d.result); }
      };
      ws.addEventListener('message', h);
      ws.send(JSON.stringify({ id, method, params }));
    });

    await call('Page.enable');
    await call('Runtime.enable');
    await call('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });

    // Instrument Canvas2D small solid-color primitives (stars) independent of variable names/formulas.
    await call('Page.addScriptToEvaluateOnNewDocument', {
      source: `(() => {
        window.__starDots = [];
        let pending = null;
        const origArc = CanvasRenderingContext2D.prototype.arc;
        const origFill = CanvasRenderingContext2D.prototype.fill;
        const origFillRect = CanvasRenderingContext2D.prototype.fillRect;
        CanvasRenderingContext2D.prototype.arc = function(x, y, r, s, e, ccw) {
          if (r >= 0.2 && r <= 2.2 && typeof this.fillStyle === 'string') {
            pending = { x, y, r };
          } else {
            pending = null;
          }
          return origArc.apply(this, arguments);
        };
        CanvasRenderingContext2D.prototype.fill = function() {
          if (pending && typeof this.fillStyle === 'string') {
            window.__starDots.push(pending);
          }
          pending = null;
          return origFill.apply(this, arguments);
        };
        CanvasRenderingContext2D.prototype.fillRect = function(x, y, w, h) {
          if (w > 0 && w <= 3 && h > 0 && h <= 3 && typeof this.fillStyle === 'string') {
            window.__starDots.push({ x, y, r: w });
          }
          return origFillRect.apply(this, arguments);
        };
        const origRaf = window.requestAnimationFrame;
        window.requestAnimationFrame = function(cb) {
          return origRaf.call(window, function(ts) {
            window.__starDots = [];
            return cb(ts);
          });
        };
      })();`
    });

    await call('Page.navigate', { url: `http://127.0.0.1:${port}/index.html` });
    await new Promise((r) => setTimeout(r, 900));

    const stats = await call('Runtime.evaluate', {
      expression: `(() => {
        const hud = document.querySelector('.hud');
        const hb = hud ? hud.getBoundingClientRect() : { left: 0, top: 0, right: 0, bottom: 0 };
        const dots = (window.__starDots || []).filter(d => {
          if (d.x < 0 || d.x >= ${W} || d.y < 0 || d.y >= ${H}) return false;
          if (hud && d.x >= hb.left && d.x <= hb.right && d.y >= hb.top && d.y <= hb.bottom) return false;
          return true;
        });
        const cells = new Set();
        const counts = Array.from({length: 16}, () => 0);
        for (const d of dots) {
          const cx = Math.min(3, Math.floor((d.x / ${W}) * 4));
          const cy = Math.min(3, Math.floor((d.y / ${H}) * 4));
          const idx = cy * 4 + cx;
          cells.add(idx);
          counts[idx]++;
        }
        return { totalDots: dots.length, occupiedCells: cells.size, gridCounts: counts };
      })()`,
      returnByValue: true,
    });
    ws.close();
    const val = stats.result.value;
    val.passed = val.occupiedCells >= 12;
    return val;
  } finally {
    chrome.kill('SIGKILL');
    srv.close();
    fs.rmSync(userDir, { recursive: true, force: true });
  }
}

const target = process.argv[2];
if (!target) { console.error('Usage: node check_stars.mjs <workspace_dir>'); process.exit(2); }
const res = await checkStars(path.resolve(target));
console.log(JSON.stringify(res));
process.exit(res.passed ? 0 : 1);
