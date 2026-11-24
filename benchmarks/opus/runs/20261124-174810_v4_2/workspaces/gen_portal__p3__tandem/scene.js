// scene.js - scene content: portal structure, crystals, grid, stars, particles
(function (global) {
  "use strict";
  var E = global.Engine3D;
  var v3 = E.vec3;

  // ---- box builder: 6 outward-facing quad faces ----
  function makeBox(cx, cy, cz, hx, hy, hz, base, edge) {
    var x0 = cx - hx, x1 = cx + hx;
    var y0 = cy - hy, y1 = cy + hy;
    var z0 = cz - hz, z1 = cz + hz;
    var c0 = v3(x0, y0, z0), c1 = v3(x1, y0, z0), c2 = v3(x1, y1, z0), c3 = v3(x0, y1, z0);
    var c4 = v3(x0, y0, z1), c5 = v3(x1, y0, z1), c6 = v3(x1, y1, z1), c7 = v3(x0, y1, z1);
    var faces = [
      [c4, c5, c6, c7], // +z
      [c1, c0, c3, c2], // -z
      [c5, c1, c2, c6], // +x
      [c4, c7, c3, c0], // -x
      [c3, c2, c6, c7], // +y
      [c0, c4, c5, c1]  // -y
    ];
    return {
      base: base,
      edge: edge,
      faces: faces
    };
  }

  // ---- the portal structure: exactly 6 boxes = 36 quad faces ----
  function buildStructure() {
    var boxes = [];
    // 1. lower wide platform box
    boxes.push(makeBox(0, 0.5, 0, 6, 0.5, 4, { r: 40, g: 20, b: 90 }, "#7a3cff"));
    // 2. upper smaller platform box
    boxes.push(makeBox(0, 1.6, 0, 3.4, 0.5, 2.4, { r: 55, g: 28, b: 110 }, "#9a5cff"));
    // 3. left pillar
    boxes.push(makeBox(-3, 4.5, 0, 0.5, 3, 0.5, { r: 30, g: 18, b: 70 }, "#00f0ff"));
    // 4. right pillar
    boxes.push(makeBox(3, 4.5, 0, 0.5, 3, 0.5, { r: 30, g: 18, b: 70 }, "#00f0ff"));
    // 5. lintel across pillar tops
    boxes.push(makeBox(0, 7.6, 0, 3.6, 0.5, 0.5, { r: 45, g: 25, b: 95 }, "#ff2bd6"));
    // 6. crown cap on the lintel
    boxes.push(makeBox(0, 8.3, 0, 2.2, 0.4, 0.4, { r: 60, g: 30, b: 120 }, "#ff2bd6"));
    return boxes;
  }

  // ---- octahedral crystal: 8 triangles ----
  function makeCrystal(cx, cy, cz, s, color) {
    var top = v3(cx, cy + s, cz);
    var bot = v3(cx, cy - s, cz);
    var a = v3(cx + s, cy, cz);
    var b = v3(cx - s, cy, cz);
    var c = v3(cx, cy, cz + s);
    var d = v3(cx, cy, cz - s);
    var tris = [
      [top, a, c], [top, c, b], [top, b, d], [top, d, a],
      [bot, c, a], [bot, b, c], [bot, d, b], [bot, a, d]
    ];
    return {
      center: v3(cx, cy, cz),
      s: s,
      color: color,
      tris: tris
    };
  }

  // ---- build the whole scene ----
  function build() {
    var structure = buildStructure();

    // 6 orbiting octahedral crystals (cyan / magenta)
    var crystals = [];
    var cols = ["#00f0ff", "#ff2bd6"];
    for (var i = 0; i < 6; i++) {
      crystals.push({
        angle: (i / 6) * Math.PI * 2,
        radius: 5.2,
        height: 4.5,
        spin: 0 + i,
        color: cols[i % 2],
        size: 0.55
      });
    }

    // 180 twinkling stars
    var stars = [];
    for (var s = 0; s < 180; s++) {
      stars.push({
        x: Math.random(),
        y: Math.random(),
        r: 0.5 + Math.random() * 1.4,
        phase: Math.random() * Math.PI * 2,
        speed: 1 + Math.random() * 2
      });
    }

    // 110 rising particles
    var particles = [];
    for (var p = 0; p < 110; p++) {
      particles.push({
        x: (Math.random() - 0.5) * 6,
        y: Math.random() * 8,
        z: (Math.random() - 0.5) * 4,
        vy: 0.4 + Math.random() * 0.8,
        max: 8 + Math.random() * 2,
        hue: Math.random() < 0.5 ? "#00f0ff" : "#ff2bd6"
      });
    }

    return {
      structure: structure,
      crystals: crystals,
      stars: stars,
      particles: particles,
      portal: { x: 0, y: 4.5, z: 0 }
    };
  }

  global.Scene = {
    build: build,
    makeBox: makeBox,
    makeCrystal: makeCrystal
  };
})(window);
