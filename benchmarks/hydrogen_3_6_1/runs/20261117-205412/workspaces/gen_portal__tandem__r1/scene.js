// scene.js : data of the neon portal gate. Sets window.Scene = { build }. No import/export.
(function () {
  function box(cx, cy, cz, sx, sy, sz, color, glow) {
    var hx = sx / 2, hy = sy / 2, hz = sz / 2;
    var x0 = cx - hx, x1 = cx + hx, y0 = cy - hy, y1 = cy + hy, z0 = cz - hz, z1 = cz + hz;
    var faces = [
      [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0]],
      [[x1, y0, z1], [x0, y0, z1], [x0, y1, z1], [x1, y1, z1]],
      [[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]],
      [[x1, y0, z0], [x1, y0, z1], [x1, y1, z1], [x1, y1, z0]],
      [[x0, y0, z1], [x0, y0, z0], [x0, y1, z0], [x0, y1, z1]],
      [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0]]
    ];
    return faces.map(function (pts) { return { pts: pts, color: color, glow: glow }; });
  }

  function build() {
    var faces = [];
    faces = faces.concat(box(0, -1.45, 0, 5.6, 0.4, 3.6, [34, 46, 78], 0.08));
    faces = faces.concat(box(0, -1.05, 0, 4.2, 0.4, 2.4, [40, 54, 88], 0.10));
    faces = faces.concat(box(-1.25, 0.42, 0, 0.5, 2.55, 0.5, [28, 40, 72], 0.06));
    faces = faces.concat(box(1.25, 0.42, 0, 0.5, 2.55, 0.5, [28, 40, 72], 0.06));
    faces = faces.concat(box(0, 1.95, 0, 3.4, 0.5, 0.7, [30, 44, 80], 0.12));
    faces = faces.concat(box(0, 2.32, 0, 2.2, 0.24, 0.5, [46, 60, 95], 0.30));

    var crystals = [];
    for (var i = 0; i < 6; i++) {
      crystals.push({
        angle: i * Math.PI / 3,
        color: i % 2 === 0 ? [40, 225, 255] : [255, 70, 215],
        spin: 0.9 + 0.12 * i,
        phase: i * 1.7
      });
    }

    var stars = [];
    for (var s = 0; s < 180; s++) {
      var u = (s + 0.5) / 180;
      var v = (s + 0.5) / 180;
      var theta = 2 * Math.PI * u;
      var phi = Math.acos(2 * v - 1);
      var r = 42;
      var x = r * Math.sin(phi) * Math.cos(theta);
      var y = r * Math.cos(phi);
      var z = r * Math.sin(phi) * Math.sin(theta);
      if (y < -4) y = -4 + (s % 7) * 0.5;
      stars.push({
        p: [x, y, z],
        size: 0.5 + ((s * 37) % 12) / 10,
        rate: 0.7 + ((s * 53) % 25) / 10,
        phase: (s * 0.35) % (2 * Math.PI)
      });
    }

    var particles = [];
    for (var p = 0; p < 110; p++) {
      var a = p * 2.399963;
      var rr = 3.4 * Math.sqrt((p + 0.5) / 110);
      var px = rr * Math.cos(a);
      var pz = rr * Math.sin(a);
      particles.push({
        x: px,
        y: -1.9 + ((p * 0.05) % 1) * 5.4,
        z: pz,
        v: 0.35 + ((p * 7) % 8) / 10,
        sway: 0.3 + ((p * 11) % 5) / 10,
        hue: p % 2 === 0 ? 188 : 312,
        size: 0.02 + ((p * 13) % 4) / 100
      });
    }

    return { faces: faces, crystals: crystals, stars: stars, particles: particles };
  }

  window.Scene = { build: build };
})();
