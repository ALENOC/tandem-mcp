// scene.js - geometry and scene state for the neon portal demo
(function (global) {
  'use strict';
  var E = global.Engine3D;
  var v3 = E.v3;

  // ---- box helper: 6 faces, outward winding (right-hand) ----
  function boxFaces(cx, cy, cz, sx, sy, sz, color, edge) {
    var hx = sx / 2, hy = sy / 2, hz = sz / 2;
    var x0 = cx - hx, x1 = cx + hx;
    var y0 = cy - hy, y1 = cy + hy;
    var z0 = cz - hz, z1 = cz + hz;
    var faces = [];
    // +x
    faces.push({ verts: [v3(x1, y0, z1), v3(x1, y0, z0), v3(x1, y1, z0), v3(x1, y1, z1)], color: color, edge: edge });
    // -x
    faces.push({ verts: [v3(x0, y0, z0), v3(x0, y0, z1), v3(x0, y1, z1), v3(x0, y1, z0)], color: color, edge: edge });
    // +y
    faces.push({ verts: [v3(x0, y1, z1), v3(x1, y1, z1), v3(x1, y1, z0), v3(x0, y1, z0)], color: color, edge: edge });
    // -y
    faces.push({ verts: [v3(x0, y0, z0), v3(x1, y0, z0), v3(x1, y0, z1), v3(x0, y0, z1)], color: color, edge: edge });
    // +z
    faces.push({ verts: [v3(x0, y0, z1), v3(x1, y0, z1), v3(x1, y1, z1), v3(x0, y1, z1)], color: color, edge: edge });
    // -z
    faces.push({ verts: [v3(x1, y0, z0), v3(x0, y0, z0), v3(x0, y1, z0), v3(x1, y1, z0)], color: color, edge: edge });
    return faces;
  }

  // ---- octahedron: 8 triangles, radius r (equator), half-height h ----
  function octaTris(cx, cy, cz, r, h, color, edge) {
    var top = v3(cx, cy + h, cz);
    var bot = v3(cx, cy - h, cz);
    var e = [
      v3(cx + r, cy, cz), v3(cx, cy, cz + r),
      v3(cx - r, cy, cz), v3(cx, cy, cz - r)
    ];
    var tris = [];
    for (var i = 0; i < 4; i++) {
      var a = e[i], b = e[(i + 1) % 4];
      tris.push({ verts: [top, a, b], color: color, edge: edge });
      tris.push({ verts: [bot, b, a], color: color, edge: edge });
    }
    return tris;
  }

  var CRYSTAL_COLORS = ['#00f0ff', '#ff2bd6', '#ffd23f', '#7cff6b', '#8a5cff', '#ff6b3d'];

  // ---- build the static box set (6 boxes = 36 faces) ----
  function buildBoxes() {
    var faces = [];
    // platform tier 1
    faces = faces.concat(boxFaces(0, 0.2, 0, 6, 0.4, 4, '#2a1a5e', '#00f0ff'));
    // platform tier 2
    faces = faces.concat(boxFaces(0, 0.55, 0, 4.4, 0.3, 2.8, '#34206e', '#00f0ff'));
    // two pillars
    faces = faces.concat(boxFaces(-1.6, 2.3, 0, 0.5, 3.2, 0.5, '#3b1f7a', '#ff2bd6'));
    faces = faces.concat(boxFaces(1.6, 2.3, 0, 0.5, 3.2, 0.5, '#3b1f7a', '#ff2bd6'));
    // lintel
    faces = faces.concat(boxFaces(0, 4.12, 0, 4.2, 0.45, 0.7, '#3b1f7a', '#ff2bd6'));
    // crown cap
    faces = faces.concat(boxFaces(0, 4.52, 0, 1.6, 0.35, 0.6, '#4a2590', '#ffd23f'));
    return faces;
  }

  // ---- stars: 180 fixed directions on a sphere of radius 60 ----
  function buildStars() {
    var stars = [];
    for (var i = 0; i < 180; i++) {
      // uniform on sphere
      var u = Math.random() * 2 - 1;
      var th = Math.random() * Math.PI * 2;
      var s = Math.sqrt(1 - u * u);
      var dir = v3(s * Math.cos(th), u, s * Math.sin(th));
      stars.push({
        dir: dir,
        size: 0.6 + Math.random() * 1.2,
        speed: 1 + Math.random() * 3,
        phase: Math.random() * Math.PI * 2,
        tint: Math.random() < 0.5 ? '#ffffff' : '#cfe8ff'
      });
    }
    return stars;
  }

  // ---- particles: 110 always alive ----
  function spawnParticle(p) {
    p.x = (Math.random() * 2 - 1) * 1.2;
    p.z = (Math.random() * 2 - 1) * 0.3;
    p.y = 0.7 + Math.random() * 0.5;
    p.vy = 0.4 + Math.random() * 0.7;
    p.vx = (Math.random() * 2 - 1) * 0.15;
    p.vz = (Math.random() * 2 - 1) * 0.15;
    p.life = 2.5 + Math.random() * 2.5;
    p.age = 0;
    p.r = 1.5 + Math.random() * 1.5;
    p.cyan = Math.random() < 0.5;
    return p;
  }
  function buildParticles() {
    var parts = [];
    for (var i = 0; i < 110; i++) {
      var p = spawnParticle({});
      p.age = Math.random() * p.life; // stagger initial ages
      parts.push(p);
    }
    return parts;
  }

  global.Scene = {
    buildBoxes: buildBoxes,
    octaTris: octaTris,
    CRYSTAL_COLORS: CRYSTAL_COLORS,
    buildStars: buildStars,
    buildParticles: buildParticles,
    spawnParticle: spawnParticle
  };
})(window);
