// scene.js : data for the neon portal gate. Plain browser script, no import/export.
// Sets window.Scene = { build }. Y axis is up.

(function () {
  var TWO_PI = Math.PI * 2;

  // Deterministic PRNG so every build() call yields identical data.
  function mulberry32(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) | 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function clamp(v, lo, hi) {
    return v < lo ? lo : (v > hi ? hi : v);
  }

  // The six axis-aligned boxes of the gate. Colors are dark obsidian blue
  // (every channel between 20 and 95) with a glow between 0.05 and 0.15.
  var BOXES = [
    { c: [0, -1.45, 0], s: [5.6, 0.4, 3.6], color: [34, 44, 78], glow: 0.08 },
    { c: [0, -1.05, 0], s: [4.2, 0.4, 2.4], color: [30, 40, 72], glow: 0.07 },
    { c: [-1.25, 0.42, 0], s: [0.5, 2.55, 0.5], color: [28, 38, 70], glow: 0.06 },
    { c: [1.25, 0.42, 0], s: [0.5, 2.55, 0.5], color: [28, 38, 70], glow: 0.06 },
    { c: [0, 1.95, 0], s: [3.4, 0.5, 0.7], color: [32, 42, 80], glow: 0.09 },
    { c: [0, 2.32, 0], s: [2.2, 0.24, 0.5], color: [40, 52, 92], glow: 0.3 }
  ];

  // The six faces of one axis-aligned box, each as four [x, y, z] corners in loop order.
  function boxFaces(cx, cy, cz, sx, sy, sz, color, glow) {
    var x0 = cx - sx / 2, x1 = cx + sx / 2;
    var y0 = cy - sy / 2, y1 = cy + sy / 2;
    var z0 = cz - sz / 2, z1 = cz + sz / 2;
    var quads = [
      [[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]],
      [[x0, y0, z0], [x0, y1, z0], [x1, y1, z0], [x1, y0, z0]],
      [[x0, y0, z0], [x0, y0, z1], [x0, y1, z1], [x0, y1, z0]],
      [[x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]],
      [[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1]],
      [[x0, y1, z0], [x0, y1, z1], [x1, y1, z1], [x1, y1, z0]]
    ];
    var faces = [];
    for (var i = 0; i < quads.length; i++) {
      faces.push({ pts: quads[i], color: color, glow: glow });
    }
    return faces;
  }

  function buildFaces() {
    var faces = [];
    for (var i = 0; i < BOXES.length; i++) {
      var b = BOXES[i];
      var f = boxFaces(b.c[0], b.c[1], b.c[2], b.s[0], b.s[1], b.s[2], b.color, b.glow);
      for (var j = 0; j < f.length; j++) faces.push(f[j]);
    }
    return faces;
  }

  function buildCrystals() {
    var cyan = [40, 225, 255];
    var magenta = [255, 70, 215];
    var crystals = [];
    for (var i = 0; i < 6; i++) {
      crystals.push({
        angle: i * Math.PI / 3,
        color: i % 2 === 0 ? cyan : magenta,
        spin: 0.9 + (i % 3) * 0.35,
        phase: i * 1.7
      });
    }
    return crystals;
  }

  function buildStars() {
    var rnd = mulberry32(0x51ed);
    var stars = [];
    for (var i = 0; i < 180; i++) {
      var u = rnd() * 2 - 1;
      var th = rnd() * TWO_PI;
      var r = Math.sqrt(Math.max(0, 1 - u * u));
      var x = 42 * r * Math.cos(th);
      var y = 42 * u;
      var z = 42 * r * Math.sin(th);
      if (y < -4) y = -4;
      stars.push({
        p: [x, y, z],
        size: 0.5 + rnd() * 1.2,
        rate: 0.7 + rnd() * 2.4,
        phase: rnd() * TWO_PI
      });
    }
    return stars;
  }

  function buildParticles() {
    var rnd = mulberry32(0x0bad);
    var particles = [];
    for (var i = 0; i < 110; i++) {
      var ang = rnd() * TWO_PI;
      var rad = Math.sqrt(rnd()) * 3.4;
      particles.push({
        x: rad * Math.cos(ang),
        y: -1.9 + rnd() * 5.4,
        z: rad * Math.sin(ang),
        v: 0.35 + rnd() * 0.75,
        sway: rnd() * TWO_PI,
        hue: rnd() < 0.5 ? 188 : 312,
        size: 0.02 + rnd() * 0.035
      });
    }
    return particles;
  }

  function build() {
    return {
      faces: buildFaces(),
      crystals: buildCrystals(),
      stars: buildStars(),
      particles: buildParticles()
    };
  }

  window.Scene = { build: build };
})();
