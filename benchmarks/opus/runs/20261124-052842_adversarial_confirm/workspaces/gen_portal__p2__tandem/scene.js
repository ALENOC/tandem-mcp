// scene.js - builds the neon portal scene geometry
(function (global) {
  'use strict';

  var E = global.Engine3D;

  // ---- box: 8 corners + 6 outward faces (CCW from outside) ----
  function makeBox(cx, cy, cz, hx, hy, hz) {
    var c = [
      [cx - hx, cy - hy, cz - hz], // 0
      [cx + hx, cy - hy, cz - hz], // 1
      [cx + hx, cy + hy, cz - hz], // 2
      [cx - hx, cy + hy, cz - hz], // 3
      [cx - hx, cy - hy, cz + hz], // 4
      [cx + hx, cy - hy, cz + hz], // 5
      [cx + hx, cy + hy, cz + hz], // 6
      [cx - hx, cy + hy, cz + hz]  // 7
    ];
    var faces = [
      [0, 1, 5, 4], // bottom (-y)
      [3, 7, 6, 2], // top (+y)
      [4, 5, 6, 7], // front (+z)
      [1, 0, 3, 2], // back (-z)
      [0, 4, 7, 3], // left (-x)
      [1, 2, 6, 5]  // right (+x)
    ];
    return { center: [cx, cy, cz], corners: c, faces: faces };
  }

  // ---- octahedron: 6 vertices + 8 triangles ----
  function makeOcta(s) {
    var v = [
      [s, 0, 0], [-s, 0, 0],
      [0, s, 0], [0, -s, 0],
      [0, 0, s], [0, 0, -s]
    ];
    var tris = [
      [0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4],
      [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5]
    ];
    return { verts: v, tris: tris };
  }

  function buildScene() {
    // 6 boxes: two-tier platform, twin pillars, lintel, crown cap
    var boxes = [
      makeBox(0, 0.5, 0, 6, 0.5, 4),     // lower wide platform
      makeBox(0, 1.5, 0, 3.5, 0.5, 2.5), // upper smaller platform
      makeBox(-4, 3.5, 0, 0.5, 2.5, 0.5), // left pillar
      makeBox(4, 3.5, 0, 0.5, 2.5, 0.5),  // right pillar
      makeBox(0, 6.2, 0, 4.5, 0.4, 0.5),  // lintel spanning pillar tops
      makeBox(0, 6.9, 0, 2.5, 0.4, 0.5)   // crown cap on top of lintel
    ];

    // 6 octahedral crystals orbiting at different heights
    var crystalColors = ['#00f0ff', '#ff2bd6', '#9d4dff'];
    var crystals = [];
    for (var i = 0; i < 6; i++) {
      crystals.push({
        baseAngle: (i / 6) * Math.PI * 2,
        radius: 5.5,
        height: 2.5 + i * 0.7,
        orbitSpeed: 0.6 + i * 0.12,
        spinSpeed: 1.5 + i * 0.3,
        size: 0.5 + (i % 3) * 0.12,
        color: crystalColors[i % 3],
        octa: makeOcta(0.5 + (i % 3) * 0.12)
      });
    }

    // 180 stars on a background sphere
    var stars = [];
    for (var s = 0; s < 180; s++) {
      var u = Math.random() * 2 - 1;
      var th = Math.random() * Math.PI * 2;
      var r = Math.sqrt(1 - u * u);
      stars.push({
        dir: [r * Math.cos(th), u, r * Math.sin(th)],
        phase: Math.random() * Math.PI * 2,
        speed: 0.5 + Math.random() * 2.5,
        size: 0.6 + Math.random() * 1.6
      });
    }

    // 110 particles rising from the platform
    var particles = [];
    for (var p = 0; p < 110; p++) {
      particles.push({
        x: (Math.random() - 0.5) * 9,
        y: Math.random() * 6,
        z: (Math.random() - 0.5) * 6,
        vy: 0.4 + Math.random() * 0.8,
        size: 1.5 + Math.random() * 3,
        hue: Math.random() < 0.5 ? '#00f0ff' : '#ff2bd6'
      });
    }

    return {
      boxes: boxes,
      crystals: crystals,
      stars: stars,
      particles: particles,
      boxFaceCount: 36,
      crystalTriCount: 48
    };
  }

  global.Scene = {
    makeBox: makeBox,
    makeOcta: makeOcta,
    buildScene: buildScene
  };
})(window);
