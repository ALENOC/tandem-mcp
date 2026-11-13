// node check_page.js : runs the inline script of index.html on a stub DOM and canvas, then drives the HUD
const fs = require('fs');
const html = fs.readFileSync(__dirname + '/index.html', 'utf8');
const code = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi)].map((m) => m[1]).join('\n;\n');
function fail(msg) { console.error('FAIL: ' + msg); process.exit(1); }
if (!code.trim()) fail('index.html has no inline script');
const calls = {}, listeners = {}, later = [];
const gradient = { addColorStop() {} };
const ctx = new Proxy({}, { set: (t, k, v) => { t[k] = v; return true; },
  get: (t, k) => (k in t ? t[k] : () => { calls[k] = (calls[k] || 0) + 1; return /Gradient/.test(k) ? gradient : undefined; }) });
function element(id) {
  return { id, style: {}, value: '1.0', textContent: '', width: 0, height: 0, getContext: () => ctx, setPointerCapture() {},
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 1080, height: 690 }),
    addEventListener(type, fn) { (listeners[id + ':' + type] = listeners[id + ':' + type] || []).push(fn); } };
}
const els = {};
for (const m of html.matchAll(/\bid="([^"]+)"/g)) els[m[1]] = element(m[1]);
for (const id of ['btnPlay', 'btnTrails', 'btnReset', 'speed', 'speedVal', 'fps', 'simTime', 'bursts']) if (!els[id]) fail('missing element id="' + id + '"');
let raf = null, now = 1000;
const onReady = (type, fn) => { if (type === 'load' || type === 'DOMContentLoaded') later.push(fn); };
global.window = global;
Object.assign(global, { innerWidth: 1080, innerHeight: 690, devicePixelRatio: 2, addEventListener: onReady,
  requestAnimationFrame: (f) => { raf = f; return 1; },
  document: { getElementById: (id) => els[id] || null, querySelector: (s) => els[s.replace(/^#/, '')] || null, querySelectorAll: () => [],
    addEventListener: onReady, body: element('body'), createElement: () => element('new') } });
new Function(code)();
later.forEach((fn) => fn());
const canvas = Object.values(els).find((e) => e.width > 0);
if (!canvas || canvas.width !== 2160) fail('the canvas width must be innerWidth * devicePixelRatio = 2160, got ' + (canvas && canvas.width));
function frames(n) { for (let i = 0; i < n; i++) { if (!raf) fail('requestAnimationFrame must be called again on every frame'); const f = raf; raf = null; now += 16.7; f(now); } }
function fire(id, type, ev) { const fns = listeners[id + ':' + type]; if (!fns) fail('no ' + type + ' listener on #' + id); fns.forEach((fn) => fn(ev || {})); }
frames(30);
for (const k of ['createRadialGradient', 'arc', 'fill', 'stroke']) if (!calls[k]) fail('ctx.' + k + '() is never called');
if ((calls.arc || 0) + (calls.fillRect || 0) < 30 * 150) fail('fewer than 150 stars are drawn per frame');
if (!(parseFloat(els.simTime.textContent) > 0)) fail('#simTime does not show the running simulation time');
fire(canvas.id, 'click', { clientX: 400, clientY: 300, offsetX: 400, offsetY: 300 });
frames(2);
if (!(parseInt(els.bursts.textContent, 10) >= 20)) fail('#bursts must show the burst particles after a click, got "' + els.bursts.textContent + '"');
frames(400);
if (parseInt(els.bursts.textContent, 10) !== 0) fail('burst particles must fade out and be removed, #bursts still shows ' + els.bursts.textContent);
els.speed.value = '2.0'; fire('speed', 'input', { target: els.speed });
if (els.speedVal.textContent.trim() !== '2.0x') fail('#speedVal must read "2.0x" after the slider moves to 2.0, got "' + els.speedVal.textContent + '"');
fire('btnPlay', 'click'); frames(2);
const frozen = els.simTime.textContent; frames(20);
if (els.simTime.textContent !== frozen) fail('simulation time must stop while paused');
fire('btnPlay', 'click'); fire('btnReset', 'click'); frames(2);
if (!(parseFloat(els.simTime.textContent) < 0.5)) fail('Reset must bring the simulation time back to 0, got ' + els.simTime.textContent);
fire('btnTrails', 'click'); frames(5);
console.log('page ok');
