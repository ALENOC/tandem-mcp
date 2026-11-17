(function () {
  function makeBoxFaces(cx, cy, cz, sx, sy, sz, color, glow) {
    var hx = sx / 2;
    var hy = sy / 2;
    var hz = sz / 2;
    var x0 = cx - hx, x1 = cx + hx;
    var y0 = cy - hy, y1 = cy + hy;
    var z0 = cz - hz, z1 = cz + hz;

    return [
      // Top (+y)
      { pts: [[x0, y1, z0], [x0, y1, z1], [x1, y1, z1], [x1, y1, z0]], color: color, glow: glow },
      // Bottom (-y)
      { pts: [[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1]], color: color, glow: glow },
      // Front (-z)
      { pts: [[x0, y0, z0], [x0, y1, z0], [x1, y1, z0], [x1, y0, z0]], color: color, glow: glow },
      // Back (+z)
      { pts: [[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], color: color, glow: glow },
      // Left (-x)
      { pts: [[x0, y0, z0], [x0, y0, z1], [x0, y1, z1], [x0, y1, z0]], color: color, glow: glow },
      // Right (+x)
      { pts: [[x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]], color: color, glow: glow }
    ];
  }

  function build() {
    var faces = []
      .concat(makeBoxFaces(0, -1.45, 0, 5.6, 0.4, 3.6, [24, 36, 72], 0.06))
      .concat(makeBoxFaces(0, -1.05, 0, 4.2, 0.4, 2.4, [28, 44, 84], 0.09))
      .concat(makeBoxFaces(-1.25, 0.42, 0, 0.5, 2.55, 0.5, [30, 50, 90], 0.12))
      .concat(makeBoxFaces(1.25, 0.42, 0, 0.5, 2.55, 0.5, [30, 50, 90], 0.12))
      .concat(makeBoxFaces(0, 1.95, 0, 3.4, 0.5, 0.7, [32, 52, 92], 0.14))
      .concat(makeBoxFaces(0, 2.32, 0, 2.2, 0.24, 0.5, [38, 68, 95], 0.3));

    var crystals = [];
    for (var i = 0; i < 6; i++) {
      crystals.push({
        angle: i * Math.PI / 3,
        color: i % 2 === 0 ? [40, 225, 255] : [255, 70, 215],
        spin: 0.9 + (i / 5) * 0.7,
        phase: i * 1.7
      });
    }

    var stars = [];
    var R = 42;
    for (var s = 0; s < 180; s++) {
      var y = -4 + Math.random() * (R + 4);
      var rHoriz = Math.sqrt(Math.max(0, R * R - y * y));
      var theta = Math.random() * Math.PI * 2;
      stars.push({
        p: [rHoriz * Math.cos(theta), y, rHoriz * Math.sin(theta)],
        size: 0.5 + Math.random() * 1.2,
        rate: 0.7 + Math.random() * 2.4,
        phase: Math.random() * Math.PI * 2
      });
    }

    var particles = [];
    for (var p = 0; p < 110; p++) {
      var rad = 3.4 * Math.sqrt(Math.random());
      var ang = Math.random() * Math.PI * 2;
      particles.push({
        x: rad * Math.cos(ang),
        y: -1.9 + Math.random() * 5.4,
        z: rad * Math.sin(ang),
        v: 0.35 + Math.random() * 0.75,
        sway: Math.random() * Math.PI * 2,
        hue: p % 2 === 0 ? 188 : 312,
        size: 0.02 + Math.random() * 0.035
      });
    }

    return {
      faces: faces,
      crystals: crystals,
      stars: stars,
      particles: particles
    };
  }

  window.Scene = { build: build };
})();
