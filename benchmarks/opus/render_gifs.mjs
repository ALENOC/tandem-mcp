import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn, execFileSync } from 'node:child_process';

const CHROME = path.join(os.homedir(), '.cache/ms-playwright/chromium-1234/chrome-linux64/chrome');
const MIME = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.json': 'application/json' };

function serveDir(dir) {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      const urlPath = (req.url || '/').split('?')[0];
      const rel = urlPath === '/' ? 'index.html' : urlPath.replace(/^\/+/, '');
      const full = path.join(dir, rel);
      if (!full.startsWith(dir) || !fs.existsSync(full) || fs.statSync(full).isDirectory()) {
        res.writeHead(404); res.end('not found'); return;
      }
      res.writeHead(200, { 'Content-Type': MIME[path.extname(full)] || 'application/octet-stream' });
      fs.createReadStream(full).pipe(res);
    });
    srv.listen(0, '127.0.0.1', () => resolve(srv));
  });
}

async function captureGif(workspaceDir, outGif, seconds = 6) {
  const srv = await serveDir(workspaceDir);
  const port = srv.address().port;
  const userDir = fs.mkdtempSync(path.join(os.tmpdir(), 'chrome-gif-'));
  const framesDir = fs.mkdtempSync(path.join(os.tmpdir(), 'frames-gif-'));
  const chrome = spawn(CHROME, [
    '--headless=new', '--no-sandbox', '--disable-gpu', '--window-size=960,600',
    '--remote-debugging-port=0', `--user-data-dir=${userDir}`, `http://127.0.0.1:${port}/index.html`,
  ], { stdio: ['ignore', 'ignore', 'pipe'] });

  try {
    const wsUrl = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('DevTools timeout')), 30000);
      let buf = '';
      chrome.stderr.on('data', (chunk) => {
        buf += chunk.toString();
        const m = buf.match(/DevTools listening on (ws:\/\/\S+)/);
        if (m) { clearTimeout(timer); resolve(m[1]); }
      });
    });

    const dbgPort = new URL(wsUrl).port;
    const targets = await (await fetch(`http://127.0.0.1:${dbgPort}/json`)).json();
    const pageTarget = targets.find((t) => t.type === 'page');
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

    await new Promise((r) => setTimeout(r, 900));
    // Each frame keeps the real time it covers, so the GIF plays at the speed of the page. A fixed
    // playback rate would speed up a page that is slower to screenshot more than a fast one.
    const stamps = [];
    const t0 = Date.now();
    for (let i = 0; Date.now() - t0 < seconds * 1000; i++) {
      const begin = Date.now();
      const { data } = await call('Page.captureScreenshot', { format: 'jpeg', quality: 92, optimizeForSpeed: true });
      stamps.push(Date.now());
      fs.writeFileSync(path.join(framesDir, `frame_${String(i).padStart(3, '0')}.jpg`), Buffer.from(data, 'base64'));
      // at most about 9 frames per second keeps the GIF small; slower pages give fewer frames
      await new Promise((r) => setTimeout(r, Math.max(0, 110 - (Date.now() - begin))));
    }
    ws.close();

    const list = stamps.map((t, i) => {
      const next = stamps[i + 1] ?? t + (t - (stamps[i - 1] ?? t - 100));
      return `file '${path.join(framesDir, `frame_${String(i).padStart(3, '0')}.jpg`)}'\nduration ${((next - t) / 1000).toFixed(3)}`;
    });
    list.push(`file '${path.join(framesDir, `frame_${String(stamps.length - 1).padStart(3, '0')}.jpg`)}'`);
    fs.writeFileSync(path.join(framesDir, 'list.txt'), list.join('\n') + '\n');
    fs.mkdirSync(path.dirname(outGif), { recursive: true });
    execFileSync('ffmpeg', [
      '-y', '-f', 'concat', '-safe', '0', '-i', path.join(framesDir, 'list.txt'),
      '-vf', 'scale=600:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse', '-fps_mode', 'vfr',
      outGif,
    ], { stdio: 'ignore' });
    const avg = (stamps[stamps.length - 1] - stamps[0]) / Math.max(1, stamps.length - 1);
    console.log(`${stamps.length} frames over ${((stamps[stamps.length - 1] - stamps[0]) / 1000).toFixed(1)} s, ${avg.toFixed(0)} ms per frame`);
    console.log(`Rendered ${outGif} (${fs.statSync(outGif).size} bytes)`);
  } finally {
    chrome.kill('SIGKILL');
    srv.close();
    fs.rmSync(userDir, { recursive: true, force: true });
    fs.rmSync(framesDir, { recursive: true, force: true });
  }
}

// Usage: node render_gifs.mjs <workspace_dir> <out.gif> [<workspace_dir> <out.gif> ...]
const args = process.argv.slice(2);
if (args.length === 0 || args.length % 2 !== 0) {
  console.error('usage: node render_gifs.mjs <workspace_dir> <out.gif> [...]');
  process.exit(2);
}
for (let i = 0; i < args.length; i += 2) {
  await captureGif(path.resolve(args[i]), path.resolve(args[i + 1]));
}
