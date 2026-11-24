// scene.js - scene geometry: boxes, crystals, portal core, rings, grid, stars, particles
(function (global) {
  'use strict';
  var E = global.Engine3D;
  var v3 = E.vec3;

  // Box: 8 corners, 6 outward-wound quad faces.
  function boxFaces(cx, cy, cz, sx, sy, sz) {
    var hx = sx / 2, hy = sy / 2, hz = sz / 2;
    var c = [
      v3(cx - hx, cy - hy, cz - hz), v3(cx + hx, cy - hy, cz - hz),
      v3(cx + hx, cy + hy, cz - hz), v3(cx - hx, cy + hy, cz - hz),
      v3(cx - hx, cy - hy, cz + hz), v3(cx + hx, cy - hy, cz + hz),
      v3(cx + hx, cy + hy, cz + hz), v3(cx - hx, cy + hy, cz + hz)
    ];
    var idx = [[4, 5, 6, 7], [1, 0, 3, 2], [5, 1, 2, 6], [0, 4, 7, 3], [7, 6, 2, 3], [0, 1, 5, 4]];
    var faces = [];
    for (var i = 0; i < 6; i++) {
      var f = idx[i];
      faces.push([c[f[0]], c[f[1]], c[f[2]], c[f[3]]]);
    }
    return faces;
  }

  // Octahedron: 6 vertices, 8 outward-wound triangles.
  function octaFaces(cx, cy, cz, rx, ry, rz) {
    var P = {
      R: v3(cx + rx, cy, cz), L: v3(cx - rx, cy, cz),
      T: v3(cx, cy + ry, cz), B: v3(cx, cy - ry, cz),
      F: v3(cx, cy, cz + rz), K: v3(cx, cy, cz - rz)
    };
    return [
      [P.R, P.T, P.F], [P.F, P.T, P.L], [P.L, P.T, P.K], [P.K, P.T, P.R],
      [P.F, P.B, P.R], [P.L, P.B, P.F], [P.K, P.B, P.L], [P.R, P.B, P.K]
    ];
  }

  function makeScene() {
    var scene = {};

    // ---- Static architecture: 6 boxes = 36 faces ----
    scene.boxes = [];
    scene.boxes.push({ faces: boxFaces(0, 0.35, 0, 10, 0.7, 10), color: [40, 46, 92], edge: [0, 240, 255], glow: 10 });   // platform tier 1
    scene.boxes.push({ faces: boxFaces(0, 1.0, 0, 7, 0.6, 7), color: [52, 40, 96], edge: [255, 43, 214], glow: 10 });    // platform tier 2
    scene.boxes.push({ faces: boxFaces(-3.2, 3.2, 0, 0.9, 4.4, 0.9), color: [46, 40, 90], edge: [0, 240, 255], glow: 12 }); // left pillar
    scene.boxes.push({ faces: boxFaces(3.2, 3.2, 0, 0.9, 4.4, 0.9), color: [46, 40, 90], edge: [0, 240, 255], glow: 12 });  // right pillar
    scene.boxes.push({ faces: boxFaces(0, 5.5, 0, 7.6, 0.8, 1.0), color: [58, 44, 104], edge: [255, 43, 214], glow: 12 }); // lintel
    scene.boxes.push({ faces: boxFaces(0, 6.2, 0, 8.4, 0.6, 1.4), color: [40, 46, 92], edge: [0, 240, 255], glow: 12 });   // crown cap
    scene.boxFaces = 36;

    // ---- Six orbiting octahedral crystals (8 tris each = 48) ----
    scene.crystals = [];
    for (var i = 0; i < 6; i++) {
      scene.crystals.push({
        phase: (i / 6) * Math.PI * 2,
        radius: 4.6,
        height: 3.4,
        spin: 0.9 + i * 0.15,
        bob: 0.5 + i * 0.1,
        color: (i % 2 === 0) ? [0, 240, 255] : [255, 43, 214],
        edge: (i % 2 === 0) ? [0, 240, 255] : [255, 43, 214],
        glow: 16
      });
    }
    scene.crystalTris = 48;

    // ---- Portal core + two counter-rotating rings ----
    scene.rings = [
      { angle: 0, dir: 1, radius: 2.2, y: 3.4, color: [0, 240, 255] },
      { angle: 0, dir: -1, radius: 2.9, y: 3.4, color: [255, 43, 214] }
    ];

    // ---- 180 twinkling stars ----
    scene.stars = [];
    for (var s = 0; s < 180; s++) {
      scene.stars.push({
        x: Math.random(), y: Math.random(),
        tw: Math.random() * Math.PI * 2,
        sp: 0.6 + Math.random() * 1.6,
        size: 0.5 + Math.random() * 1.4
      });
    }

    // ---- 110 rising particles ----
    scene.particles = [];
    for (var p = 0; p < 110; p++) {
      scene.particles.push({
        x: (Math.random() - 0.5) * 3.4,
        y: Math.random() * 4.5,
        z: (Math.random() - 0.5) * 3.4,
        vy: 0.5 + Math.random() * 0.9,
        life: Math.random(),
        max: 3 + Math.random() * 2
      });
    }

    return scene;
  }

  global.Scene = { makeScene: makeScene, boxFaces: boxFaces, octaFaces: octaFaces };
})(window);
