/* scene.js - geometry + state for the NEON PORTAL 3D scene */
(function (global) {
  "use strict";
  var E = global.Engine3D;

  // ---- Box: 6 outward-facing quad faces ----
  function box(cx, cy, cz, hx, hy, hz, base) {
    var x0 = cx - hx, x1 = cx + hx, y0 = cy - hy, y1 = cy + hy, z0 = cz - hz, z1 = cz + hz;
    var a = [x0, y0, z0], b = [x1, y0, z0], c = [x1, y1, z0], d = [x0, y1, z0];
    var e = [x0, y0, z1], f = [x1, y0, z1], g = [x1, y1, z1], h = [x0, y1, z1];
    return [
      [a, d, c, b], // -z
      [e, f, g, h], // +z
      [a, e, h, d], // -x
      [b, c, g, f], // +x
      [a, b, f, e], // -y
      [d, c, g, h]  // +y
    ];
  }

  // ---- Octahedron: 8 triangular faces ----
  function octa(cx, cy, cz, r, base) {
    var t = [cx, cy + r, cz], b = [cx, cy - r, cz];
    var p1 = [cx + r, cy, cz], p2 = [cx, cy, cz + r], p3 = [cx - r, cy, cz], p4 = [cx, cy, cz - r];
    return [
      [t, p1, p2], [t, p2, p3], [t, p3, p4], [t, p4, p1],
      [b, p2, p1], [b, p3, p2], [b, p4, p3], [b, p1, p4]
    ];
  }

  // ---- Ring: a flat neon band of quads in the XZ plane, centered at origin ----
  function ring(inner, outer, seg, base) {
    var faces = [];
    for (var i = 0; i < seg; i++) {
      var a0 = (i / seg) * Math.PI * 2;
      var a1 = ((i + 1) / seg) * Math.PI * 2;
      var c0 = Math.cos(a0), s0 = Math.sin(a0), c1 = Math.cos(a1), s1 = Math.sin(a1);
      var A = [inner * c0, 0, inner * s0], B = [inner * c1, 0, inner * s1];
      var C = [outer * c1, 0, outer * s1], D = [outer * c0, 0, outer * s0];
      faces.push([A, B, C, D]);
    }
    return faces;
  }

  // Rotate a face's vertices around the Y axis by angle a.
  function rotY(face, a) {
    var c = Math.cos(a), s = Math.sin(a);
    return face.map(function (p) {
      return [p[0] * c + p[2] * s, p[1], -p[0] * s + p[2] * c];
    });
  }

  // Rotate a face's vertices around the X axis by angle a.
  function rotX(face, a) {
    var c = Math.cos(a), s = Math.sin(a);
    return face.map(function (p) {
      return [p[0], p[1] * c - p[2] * s, p[1] * s + p[2] * c];
    });
  }

  // ---- Build the full scene state ----
  function build() {
    var state = {
      cam: E.makeCamera(),
      orbit: true,
      paused: false,
      speed: 1,
      t: 0,
      // 6 boxes = 36 faces (two-tier platform, twin pillars, lintel, crown cap)
      monument: [
        { faces: box(0, 0.5, 0, 7, 0.5, 7, [40, 60, 120]), edge: [0, 229, 255] },      // lower platform
        { faces: box(0, 1.6, 0, 5, 0.6, 5, [50, 70, 140]), edge: [0, 229, 255] },      // upper platform
        { faces: box(-4, 5, 0, 0.7, 4, 0.7, [60, 40, 120]), edge: [255, 0, 200] },     // left pillar
        { faces: box(4, 5, 0, 0.7, 4, 0.7, [60, 40, 120]), edge: [255, 0, 200] },      // right pillar
        { faces: box(0, 9.2, 0, 5, 0.7, 0.7, [70, 50, 150]), edge: [255, 0, 200] },    // lintel
        { faces: box(0, 10.2, 0, 5.6, 0.5, 5.6, [90, 60, 180]), edge: [0, 229, 255] }  // crown cap
      ],
      // 6 orbiting octahedral crystals (6 * 8 = 48 triangles)
      crystals: [],
      // two counter-rotating rings
      ringA: ring(3.2, 4.2, 28, [0, 229, 255]),
      ringB: ring(4.6, 5.4, 28, [255, 0, 200]),
      // 180 twinkling stars
      stars: [],
      // 110 rising particles
      parts: [],
      // cyber grid floor
      grid: []
    };

    var i;
    for (i = 0; i < 6; i++) {
      state.crystals.push({
        angle: (i / 6) * Math.PI * 2,
        radius: 11,
        y: 5 + Math.sin(i * 1.3) * 1.5,
        r: 1.1,
        base: [i % 2 === 0 ? [0, 229, 255] : [255, 0, 200]]
      });
    }

    for (i = 0; i < 180; i++) {
      state.stars.push({
        x: Math.random(),
        y: Math.random(),
        r: 0.5 + Math.random() * 1.4,
        ph: Math.random() * Math.PI * 2,
        sp: 1 + Math.random() * 3
      });
    }

    for (i = 0; i < 110; i++) {
      state.parts.push({
        x: (Math.random() - 0.5) * 8,
        y: Math.random() * 14,
        z: (Math.random() - 0.5) * 8,
        vy: 0.6 + Math.random() * 1.2,
        r: 0.06 + Math.random() * 0.12,
        ph: Math.random() * Math.PI * 2
      });
    }

    // grid lines across the floor (y = -0.02)
    var g = -14, s = 14, step = 2, k;
    for (k = g; k <= s; k += step) {
      state.grid.push([[-14, -0.02, k], [14, -0.02, k]]);
      state.grid.push([[k, -0.02, -14], [k, -0.02, 14]]);
    }

    return state;
  }

  global.Scene = { build: build, box: box, octa: octa, ring: ring, rotY: rotY, rotX: rotX };
})(window);
