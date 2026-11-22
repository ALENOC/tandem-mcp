// scene.js - geometry builders for the neon portal scene.
// Pure data builders: boxes (6 quad faces), octahedra (8 triangles),
// grid floor, stars and particles. No rendering here.

(function (global) {
  'use strict';

  // Build an axis-aligned box centered at (cx,cy,cz) with half-extents (hx,hy,hz).
  // Returns { faces: [ {pts:[4 world points], normal:[x,y,z]} x6 ] }.
  function buildBox(cx, cy, cz, hx, hy, hz) {
    var x0 = cx - hx, x1 = cx + hx;
    var y0 = cy - hy, y1 = cy + hy;
    var z0 = cz - hz, z1 = cz + hz;
    // Each face: 4 corners in CCW order when viewed from outside.
    var faces = [
      { n: [0, 0, 1], pts: [[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]] }, // front +z
      { n: [0, 0, -1], pts: [[x1, y0, z0], [x0, y0, z0], [x0, y1, z0], [x1, y1, z0]] }, // back -z
      { n: [1, 0, 0], pts: [[x1, y0, z1], [x1, y0, z0], [x1, y1, z0], [x1, y1, z1]] }, // right +x
      { n: [-1, 0, 0], pts: [[x0, y0, z0], [x0, y0, z1], [x0, y1, z1], [x0, y1, z0]] }, // left -x
      { n: [0, 1, 0], pts: [[x0, y1, z1], [x1, y1, z1], [x1, y1, z0], [x0, y1, z0]] }, // top +y
      { n: [0, -1, 0], pts: [[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1]] }  // bottom -y
    ];
    return { faces: faces };
  }

  // Build an octahedron centered at origin with radius r.
  // Returns { tris: [ [3 world points] x8 ] }.
  function buildOctahedron(r) {
    var t = [0, r, 0], b = [0, -r, 0];
    var a = [r, 0, 0], d = [-r, 0, 0], c = [0, 0, r], e = [0, 0, -r];
    return {
      tris: [
        [t, a, c], [t, c, d], [t, d, e], [t, e, a],
        [b, c, a], [b, d, c], [b, e, d], [b, a, e]
      ]
    };
  }

  // Build the full scene graph (static geometry + dynamic state).
  function buildScene() {
    var boxes = [
      buildBox(0, 0.5, 0, 6, 0.5, 6),     // 1 lower wide platform
      buildBox(0, 1.5, 0, 3.5, 0.5, 3.5), // 2 upper smaller platform
      buildBox(-3, 3.5, 0, 0.5, 2, 0.5),  // 3 left pillar
      buildBox(3, 3.5, 0, 0.5, 2, 0.5),   // 4 right pillar
      buildBox(0, 5.5, 0, 3.5, 0.5, 0.5), // 5 lintel across pillar tops
      buildBox(0, 6.2, 0, 2, 0.4, 0.5)    // 6 crown cap on the lintel
    ];

    // 6 octahedral crystals orbiting at mid height.
    var crystalColors = ['#00f0ff', '#ff2bd6', '#9d4dff'];
    var crystals = [];
    for (var i = 0; i < 6; i++) {
      crystals.push({
        baseAngle: (i / 6) * Math.PI * 2,
        radius: 4.5,
        height: 3.5,
        spin: 0.6 + i * 0.15,
        size: 0.55,
        color: crystalColors[i % 3],
        geo: buildOctahedron(0.55)
      });
    }

    // 180 stars on a large sphere shell.
    var stars = [];
    for (var s = 0; s < 180; s++) {
      var u = Math.random() * 2 - 1;
      var th = Math.random() * Math.PI * 2;
      var rr = Math.sqrt(1 - u * u);
      var R = 90;
      stars.push({
        x: rr * Math.cos(th) * R,
        y: Math.abs(u) * R * 0.6 + 5,
        z: rr * Math.sin(th) * R,
        phase: Math.random() * Math.PI * 2,
        speed: 0.5 + Math.random() * 1.5,
        size: 0.5 + Math.random() * 1.2
      });
    }

    // 110 rising particles.
    var particles = [];
    for (var p = 0; p < 110; p++) {
      particles.push({
        x: (Math.random() * 2 - 1) * 5,
        y: Math.random() * 6,
        z: (Math.random() * 2 - 1) * 5,
        vy: 0.5 + Math.random() * 1.0,
        color: Math.random() < 0.5 ? '#00f0ff' : '#ff2bd6',
        size: 1 + Math.random() * 2
      });
    }

    return {
      boxes: boxes,
      boxFaces: boxes.length * 6,
      crystals: crystals,
      crystalTris: crystals.length * 8,
      stars: stars,
      particles: particles,
      portal: { x: 0, y: 3.5, z: 0, innerR: 1.4, outerR: 2.2, seg: 64 }
    };
  }

  global.Scene = {
    buildBox: buildBox,
    buildOctahedron: buildOctahedron,
    buildScene: buildScene
  };

})(typeof window !== 'undefined' ? window : this);
