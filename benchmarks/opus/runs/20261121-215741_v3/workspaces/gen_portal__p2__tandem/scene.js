// scene.js - builds the neon portal scene geometry
(function (global) {
  'use strict';
  var E = global.Engine3D;

  // ---- box: 6 faces, each face 2 triangles ----
  // Returns { faces: [ { corners:[4], normal:[3] } x6 ] }
  function makeBox(cx, cy, cz, hx, hy, hz) {
    var x0 = cx - hx, x1 = cx + hx;
    var y0 = cy - hy, y1 = cy + hy;
    var z0 = cz - hz, z1 = cz + hz;
    // each face: 4 corners in CCW order when viewed from outside
    var faces = [
      { n: [1, 0, 0], c: [[x1, y0, z1], [x1, y1, z1], [x1, y1, z0], [x1, y0, z0]] }, // +x
      { n: [-1, 0, 0], c: [[x0, y0, z0], [x0, y1, z0], [x0, y1, z1], [x0, y0, z1]] }, // -x
      { n: [0, 1, 0], c: [[x0, y1, z1], [x1, y1, z1], [x1, y1, z0], [x0, y1, z0]] }, // +y
      { n: [0, -1, 0], c: [[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1]] }, // -y
      { n: [0, 0, 1], c: [[x1, y0, z1], [x1, y1, z1], [x0, y1, z1], [x0, y0, z1]] }, // +z
      { n: [0, 0, -1], c: [[x0, y0, z0], [x0, y1, z0], [x1, y1, z0], [x1, y0, z0]] }  // -z
    ];
    return { center: [cx, cy, cz], faces: faces };
  }

  // ---- octahedron: 8 triangles ----
  // vertices
  var A = [1, 0, 0], B = [-1, 0, 0], C = [0, 1, 0], D = [0, -1, 0], E2 = [0, 0, 1], F = [0, 0, -1];
  var OCTA = [
    [C, A, E2], [C, E2, B], [C, B, F], [C, F, A],
    [D, E2, A], [D, F, E2], [D, B, F], [D, A, B]
  ];

  // ---- build the scene ----
  function build() {
    var boxes = [];
    // two-tier platform (2 boxes)
    boxes.push(makeBox(0, 0.0, 0, 6.0, 0.5, 6.0));   // lower tier
    boxes.push(makeBox(0, 0.55, 0, 4.2, 0.45, 4.2)); // upper tier
    // twin pillars (2 boxes)
    boxes.push(makeBox(-3.2, 2.6, 0, 0.55, 2.05, 0.55)); // left pillar
    boxes.push(makeBox(3.2, 2.6, 0, 0.55, 2.05, 0.55));  // right pillar
    // lintel across pillar tops (1 box)
    boxes.push(makeBox(0, 4.75, 0, 3.9, 0.5, 0.7));
    // crown cap on the lintel (1 box)
    boxes.push(makeBox(0, 5.35, 0, 4.3, 0.35, 0.95));

    // 6 octahedral crystals orbiting at different heights
    var crystals = [];
    for (var i = 0; i < 6; i++) {
      crystals.push({
        angle: (i / 6) * Math.PI * 2,
        radius: 5.2,
        height: 1.6 + i * 0.55,
        spin: 0.6 + i * 0.12,
        scale: 0.55 + (i % 3) * 0.12,
        color: (i % 2 === 0) ? [255, 43, 214] : [0, 240, 255] // #ff2bd6 / #00f0ff
      });
    }

    // 180 twinkling stars
    var stars = [];
    for (var s = 0; s < 180; s++) {
      stars.push({
        x: Math.random(),
        y: Math.random(),
        r: 0.4 + Math.random() * 1.4,
        phase: Math.random() * Math.PI * 2,
        speed: 0.6 + Math.random() * 1.6
      });
    }

    // 110 particles rising from platform toward portal
    var particles = [];
    for (var p = 0; p < 110; p++) {
      particles.push({
        x: (Math.random() - 0.5) * 8,
        z: (Math.random() - 0.5) * 8,
        y: Math.random() * 4,
        vy: 0.4 + Math.random() * 0.8,
        color: (p % 2 === 0) ? [0, 240, 255] : [255, 43, 214],
        size: 1.5 + Math.random() * 2.5
      });
    }

    return {
      boxes: boxes,
      crystals: crystals,
      stars: stars,
      particles: particles,
      octa: OCTA,
      boxFaces: boxes.length * 6,   // 36
      crystalTris: crystals.length * 8 // 48
    };
  }

  global.Scene = { build: build, makeBox: makeBox, OCTA: OCTA };
})(window);
