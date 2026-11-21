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

async function checkPortalVisual(wsDir) {
  const srv = await serveDir(wsDir);
  const port = srv.address().port;
  const userDir = fs.mkdtempSync(path.join(os.tmpdir(), 'portal-vis-'));
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
    await call('Page.navigate', { url: `http://127.0.0.1:${port}/index.html` });
    await new Promise((r) => setTimeout(r, 900));

    // Sample at a deterministic instant: reset + pause, wait 2 frames
    await call('Runtime.evaluate', {
      expression: `(() => {
        if (window.Engine3D && typeof window.Engine3D.reset === 'function') window.Engine3D.reset();
        const bReset = document.getElementById('btnReset');
        if (bReset) bReset.click();
        const bPause = document.getElementById('btnPause');
        if (bPause && /pause/i.test(bPause.textContent)) bPause.click();
      })()`,
    });
    await new Promise((r) => setTimeout(r, 120));

    const metrics = await call('Runtime.evaluate', {
      expression: `(() => {
        const c = document.getElementById('c') || document.querySelector('canvas');
        if (!c) return { error: 'no canvas' };
        const ctx = c.getContext('2d');
        const cw = c.width, ch = c.height;
        // Sample center 60% of canvas where portal & crystals live
        const x0 = Math.floor(cw * 0.2), y0 = Math.floor(ch * 0.15);
        const sw = Math.floor(cw * 0.6), sh = Math.floor(ch * 0.72);
        const data = ctx.getImageData(x0, y0, sw, sh).data;
        let darkBlueFaces = 0;
        let saturatedCyan = 0;
        let saturatedMagenta = 0;
        let overexposedWhite = 0;
        for (let i = 0; i < data.length; i += 4) {
          const r = data[i], g = data[i + 1], b = data[i + 2];
          if (b >= 35 && b <= 155 && (b - r) >= 15 && r <= 95 && g <= 125) {
            darkBlueFaces++;
          }
          if (b >= 165 && g >= 130 && r <= 110 && (b - r) >= 70) {
            saturatedCyan++;
          }
          if (r >= 150 && b >= 130 && g <= 120 && (r - g) >= 55) {
            saturatedMagenta++;
          }
          if (r >= 185 && g >= 185 && b >= 185) {
            overexposedWhite++;
          }
        }
        return { darkBlueFaces, saturatedCyan, saturatedMagenta, overexposedWhite };
      })()`,
      returnByValue: true,
    });
    ws.close();
    const v = metrics.result.value;
    if (v.error) return { passed: false, ...v };
    const passed = (
      v.darkBlueFaces >= 4000
      && (v.saturatedCyan >= 300 || v.saturatedMagenta >= 300)
      && v.overexposedWhite <= 4500
    );
    return { passed, ...v };
  } finally {
    chrome.kill('SIGKILL');
    srv.close();
    fs.rmSync(userDir, { recursive: true, force: true });
  }
}

const target = process.argv[2];
if (!target) { console.error('Usage: node check_portal_visual.mjs <workspace_dir>'); process.exit(2); }
const res = await checkPortalVisual(path.resolve(target));
console.log(JSON.stringify(res));
process.exit(res.passed ? 0 : 1);
