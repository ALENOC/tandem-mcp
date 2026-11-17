// node check_engine.js : loads scene.js and engine3d.js with a stub canvas and renders three frames
const noop = new Proxy(function () {}, { get: () => noop, apply: () => noop });
const ctx = new Proxy({}, { get: (t, k) => (k in t ? t[k] : () => noop), set: (t, k, v) => { t[k] = v; return true; } });
const canvas = { width: 1080, height: 690, clientWidth: 1080, clientHeight: 690, style: {}, getContext: () => ctx,
  addEventListener() {}, setPointerCapture() {}, getBoundingClientRect: () => ({ left: 0, top: 0, width: 1080, height: 690 }) };
ctx.canvas = canvas;
let raf = null;
global.window = global;
Object.assign(global, { innerWidth: 1080, innerHeight: 690, devicePixelRatio: 1, addEventListener() {},
  requestAnimationFrame: (f) => { raf = f; return 1; }, document: { getElementById: () => canvas, addEventListener() {} } });
require('./scene.js');
require('./engine3d.js');
function fail(msg) { console.error('FAIL: ' + msg); process.exit(1); }
const scene = window.Scene.build();
const want = { faces: 36, crystals: 6, stars: 180, particles: 110 };
for (const k in want) if (!Array.isArray(scene[k]) || scene[k].length !== want[k]) fail('Scene.build().' + k + ' must hold ' + want[k] + ' items');
window.Engine3D.init(canvas);
for (let i = 1; i <= 3; i++) {
  if (!raf) fail('the loop must call requestAnimationFrame again on every frame');
  const frame = raf; raf = null; frame(i * 16.7);
}
const stats = window.Engine3D.getStats();
if (stats.polys !== 84 || stats.parts !== 110) fail('getStats() gave ' + JSON.stringify(stats) + ', expected polys 84 and parts 110');
if (window.Engine3D.togglePause() !== true || window.Engine3D.togglePause() !== false) fail('togglePause() must return the new paused state');
console.log('engine ok');
