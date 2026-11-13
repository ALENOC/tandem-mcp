(function () {
  var TAU = Math.PI * 2;

  function boxFaces(cx, cy, cz, sx, sy, sz, color, glow) {
    var hx = sx / 2, hy = sy / 2, hz = sz / 2;
    var x0 = cx - hx, x1 = cx + hx;
    var y0 = cy - hy, y1 = cy + hy;
    var z0 = cz - hz, z1 = cz + hz;
    var faces = [
      { pts: [[x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]], color: color, glow: glow },
      { pts: [[x0, y0, z1], [x0, y1, z1], [x0, y1, z0], [x0, y0, z0]], color: color, glow: glow },
      { pts: [[x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1]], color: color, glow: glow },
      { pts: [[x0, y0, z1], [x1, y0, z1], [x1, y0, z0], [x0, y0, z0]], color: color, glow: glow },
      { pts: [[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], color: color, glow: glow },
      { pts: [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0]], color: color, glow: glow }
    ];
    return faces;
  }

  function build() {
    var faces = [];
    var boxDefs = [
      { c: [0, -1.45, 0], s: [5.6, 0.4, 3.6], color: [34, 42, 78], glow: 0.08 },
      { c: [0, -1.05, 0], s: [4.2, 0.4, 2.4], color: [30, 38, 72], glow: 0.1 },
      { c: [-1.25, 0.42, 0], s: [0.5, 2.55, 0.5], color: [28, 36, 70], glow: 0.12 },
      { c: [1.25, 0.42, 0], s: [0.5, 2.55, 0.5], color: [28, 36, 70], glow: 0.12 },
      { c: [0, 1.95, 0], s: [3.4, 0.5, 0.7], color: [32, 40, 80], glow: 0.14 },
      { c: [0, 2.32, 0], s: [2.2, 0.24, 0.5], color: [40, 48, 90], glow: 0.3 }
    ];
    for (var b = 0; b < boxDefs.length; b++) {
      var d = boxDefs[b];
      var f = boxFaces(d.c[0], d.c[1], d.c[2], d.s[0], d.s[1], d.s[2], d.color, d.glow);
      for (var i = 0; i < f.length; i++) faces.push(f[i]);
    }

    var crystals = [];
    var cyan = [40, 225, 255];
    var magenta = [255, 70, 215];
    for (var i = 0; i < 6; i++) {
      crystals.push({
        angle: i * Math.PI / 3,
        color: i % 2 === 0 ? cyan : magenta,
        spin: 0.9 + (i % 3) * 0.35,
        phase: i * 1.7
      });
    }

    var stars = [];
    var R = 42;
    for (var i = 0; i < 180; i++) {
      var u = (i + 0.5) / 180;
      var v = (i * 0.6180339887498949) % 1;
      var theta = 2 * Math.PI * v;
      var phi = Math.acos(1 - 2 * u);
      var x = R * Math.sin(phi) * Math.cos(theta);
      var y = R * Math.cos(phi);
      var z = R * Math.sin(phi) * Math.sin(theta);
      if (y < -4) y = -4 + (i % 7) * 0.5;
      stars.push({
        p: [x, y, z],
        size: 0.5 + (i % 13) * 0.1,
        rate: 0.7 + (i % 25) * 0.096,
        phase: (i % 63) * (TAU / 63)
      });
    }

    var particles = [];
    for (var i = 0; i < 110; i++) {
      var ang = i * 2.399963229728653;
      var rad = 3.4 * Math.sqrt((i + 0.5) / 110);
      var x = rad * Math.cos(ang);
      var z = rad * Math.sin(ang);
      particles.push({
        x: x,
        y: -1.9 + (i % 41) * (5.4 / 40),
        z: z,
        v: 0.35 + (i % 18) * (0.75 / 17),
        sway: 0.4 + (i % 5) * 0.2,
        hue: i % 2 === 0 ? 188 : 312,
        size: 0.02 + (i % 12) * 0.0035
      });
    }

    return { faces: faces, crystals: crystals, stars: stars, particles: particles };
  }

  window.Scene = { build: build };
})();
