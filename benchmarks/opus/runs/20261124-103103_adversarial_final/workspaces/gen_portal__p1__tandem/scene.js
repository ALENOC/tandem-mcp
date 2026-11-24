/* scene.js - builds the neon portal scene: two-tier platform, twin pillars,
 * lintel, crown cap (6 boxes = 36 faces), six orbiting octahedral crystals
 * (6 x 8 = 48 triangles), 180 twinkling stars, 110 rising particles, the
 * portal core and the cyber grid floor.
 */
(function (global) {
  'use strict';
  var E = global.Engine3D;

  var CYAN = '#00f0ff';
  var MAGENTA = '#ff2bd6';
  var VIOLET = '#9d4bff';
  var CRYSTAL_COLORS = [CYAN, MAGENTA, VIOLET];

  // ---- box face builder (6 outward-facing quads) ------------------------
  function boxFaces(cx, cy, cz, hx, hy, hz, color, emissive) {
    var x0 = cx - hx, x1 = cx + hx;
    var y0 = cy - hy, y1 = cy + hy;
    var z0 = cz - hz, z1 = cz + hz;
    var faces = [
      [[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1]], // bottom
      [[x0, y1, z0], [x0, y1, z1], [x1, y1, z1], [x1, y1, z0]], // top
      [[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], // front
      [[x0, y0, z0], [x0, y1, z0], [x1, y1, z0], [x1, y0, z0]], // back
      [[x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]], // right
      [[x0, y0, z0], [x0, y0, z1], [x0, y1, z1], [x0, y1, z0]]  // left
    ];
    var out = [];
    for (var i = 0; i < faces.length; i++) {
      out.push({ verts: faces[i], color: color, emissive: emissive });
    }
    return out;
  }

  // ---- octahedron (8 triangles) ----------------------------------------
  function octaTris(cx, cy, cz, rx, ry, rz, color) {
    var T = [cx, cy + ry, cz];
    var B = [cx, cy - ry, cz];
    var A = [cx + rx, cy, cz];
    var C = [cx - rx, cy, cz];
    var D = [cx, cy, cz + rz];
    var F = [cx, cy, cz - rz];
    var tris = [
      [T, D, A], [T, C, D], [T, F, C], [T, A, F],
      [B, A, D], [B, D, C], [B, C, F], [B, F, A]
    ];
    var out = [];
    for (var i = 0; i < tris.length; i++) {
      out.push({ verts: tris[i], color: color, emissive: color });
    }
    return out;
  }

  // ---- scene state -----------------------------------------------------
  var scene = {
    boxFaces: [],
    boxCount: 0,
    crystals: [],
    crystalTris: 0,
    stars: [],
    particles: [],
    portal: { x: 0, y: 3.2, z: 0 }
  };

  // ---- build the static structure --------------------------------------
  function buildStructure() {
    var polys = [];
    var add = function (arr) { for (var i = 0; i < arr.length; i++) polys.push(arr[i]); };

    // lower wide platform
    add(boxFaces(0, 0.5, 0, 5.0, 0.5, 3.0, '#141a3a', '#0a1030'));
    // upper narrower platform
    add(boxFaces(0, 1.5, 0, 3.2, 0.5, 2.0, '#1a2148', '#0d1236'));
    // twin pillars
    add(boxFaces(-2.6, 3.5, 0, 0.45, 2.0, 0.45, '#20264f', '#101638'));
    add(boxFaces(2.6, 3.5, 0, 0.45, 2.0, 0.45, '#20264f', '#101638'));
    // lintel across the pillar tops
    add(boxFaces(0, 5.7, 0, 3.0, 0.4, 0.5, '#262c5c', '#121840'));
    // crown cap on top of the lintel
    add(boxFaces(0, 6.35, 0, 1.6, 0.35, 0.7, '#2c3268', '#141a48'));

    scene.boxFaces = polys;
    scene.boxCount = polys.length; // 6 boxes x 6 faces = 36
  }

  // ---- crystals --------------------------------------------------------
  function buildCrystals() {
    var arr = [];
    for (var i = 0; i < 6; i++) {
      arr.push({
        baseAngle: (i / 6) * Math.PI * 2,
        radius: 4.6,
        height: 3.4 + (i % 3) * 0.5,
        spin: 1.2 + i * 0.15,
        phase: i * 0.7,
        colorIndex: i % 3
      });
    }
    scene.crystals = arr;
    scene.crystalTris = 6 * 8; // 48
  }

  // ---- stars (180) -----------------------------------------------------
  function buildStars() {
    var arr = [];
    for (var i = 0; i < 180; i++) {
      var theta = Math.random() * Math.PI * 2;
      var phi = Math.acos(2 * Math.random() - 1);
      var R = 60 + Math.random() * 40;
      arr.push({
        x: R * Math.sin(phi) * Math.cos(theta),
        y: R * Math.cos(phi) * 0.6 + 8,
        z: R * Math.sin(phi) * Math.sin(theta),
        size: 0.6 + Math.random() * 1.6,
        phase: Math.random() * Math.PI * 2,
        speed: 0.8 + Math.random() * 2.0
      });
    }
    scene.stars = arr;
  }

  // ---- particles (110) -------------------------------------------------
  function buildParticles() {
    var arr = [];
    for (var i = 0; i < 110; i++) {
      arr.push({
        x: (Math.random() - 0.5) * 8,
        y: Math.random() * 6,
        z: (Math.random() - 0.5) * 5,
        vy: 0.4 + Math.random() * 0.8,
        phase: Math.random() * Math.PI * 2,
        colorIndex: i % 3
      });
    }
    scene.particles = arr;
  }

  // ---- per-frame updates -----------------------------------------------
  function updateParticles(dt) {
    var maxH = 7.0;
    for (var i = 0; i < scene.particles.length; i++) {
      var p = scene.particles[i];
      p.y += p.vy * dt;
      p.phase += dt * 2;
      p.x += Math.sin(p.phase) * 0.15 * dt;
      if (p.y > maxH) {
        p.y = 0.2;
        p.x = (Math.random() - 0.5) * 8;
        p.z = (Math.random() - 0.5) * 5;
      }
    }
  }

  function crystalColor(c, time) {
    // cycle cyan -> magenta -> violet over time
    var idx = (c.colorIndex + Math.floor(time * 0.6 + c.phase)) % 3;
    if (idx < 0) idx += 3;
    return CRYSTAL_COLORS[idx];
  }

  // Build the current triangle list for all crystals (world space).
  function crystalPolys(time) {
    var polys = [];
    for (var i = 0; i < scene.crystals.length; i++) {
      var c = scene.crystals[i];
      var a = c.baseAngle + time * 0.5;
      var cx = Math.cos(a) * c.radius;
      var cz = Math.sin(a) * c.radius;
      var cy = c.height + Math.sin(time * 0.8 + c.phase) * 0.3;
      var s = time * c.spin + c.phase;
      var rx = 0.5, ry = 0.8, rz = 0.5;
      var color = crystalColor(c, time);
      var tris = octaTris(cx, cy, cz, rx, ry, rz, color);
      // spin each crystal about its own vertical axis
      var cosS = Math.cos(s), sinS = Math.sin(s);
      for (var t = 0; t < tris.length; t++) {
        for (var v = 0; v < 3; v++) {
          var vx = tris[t].verts[v][0] - cx;
          var vz = tris[t].verts[v][2] - cz;
          tris[t].verts[v][0] = cx + vx * cosS - vz * sinS;
          tris[t].verts[v][2] = cz + vx * sinS + vz * cosS;
        }
      }
      for (var k = 0; k < tris.length; k++) polys.push(tris[k]);
    }
    return polys;
  }

  // ---- drawing ---------------------------------------------------------
  function drawBackground(ctx, w, h) {
    var g = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, Math.max(w, h) * 0.7);
    g.addColorStop(0, '#1a0b2e');
    g.addColorStop(1, '#05010a');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
  }

  function drawStars(ctx, cam, time) {
    for (var i = 0; i < scene.stars.length; i++) {
      var s = scene.stars[i];
      var p = E.project(cam, [s.x, s.y, s.z]);
      if (!p) continue;
      var tw = 0.5 + 0.5 * Math.sin(time * s.speed + s.phase);
      var alpha = 0.25 + 0.75 * tw;
      ctx.globalAlpha = alpha;
      ctx.fillStyle = '#ffffff';
      ctx.beginPath();
      ctx.arc(p.x, p.y, s.size, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  function drawGrid(ctx, cam) {
    var ext = 24;
    var step = 2;
    ctx.lineWidth = 1;
    for (var i = -ext; i <= ext; i += step) {
      // lines along z
      var a1 = E.project(cam, [i, 0, -ext]);
      var a2 = E.project(cam, [i, 0, ext]);
      if (a1 && a2) {
        var grad = ctx.createLinearGradient(a1.x, a1.y, a2.x, a2.y);
        grad.addColorStop(0, 'rgba(0,240,255,0.05)');
        grad.addColorStop(1, 'rgba(0,240,255,0.55)');
        ctx.strokeStyle = grad;
        ctx.beginPath();
        ctx.moveTo(a1.x, a1.y);
        ctx.lineTo(a2.x, a2.y);
        ctx.stroke();
      }
      // lines along x
      var b1 = E.project(cam, [-ext, 0, i]);
      var b2 = E.project(cam, [ext, 0, i]);
      if (b1 && b2) {
        var grad2 = ctx.createLinearGradient(b1.x, b1.y, b2.x, b2.y);
        grad2.addColorStop(0, 'rgba(0,240,255,0.05)');
        grad2.addColorStop(1, 'rgba(0,240,255,0.55)');
        ctx.strokeStyle = grad2;
        ctx.beginPath();
        ctx.moveTo(b1.x, b1.y);
        ctx.lineTo(b2.x, b2.y);
        ctx.stroke();
      }
    }
  }

  function drawPortal(ctx, cam, time) {
    var p = E.project(cam, [scene.portal.x, scene.portal.y, scene.portal.z]);
    if (!p) return;
    var R = 120;
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';

    // glowing core
    var core = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, R);
    core.addColorStop(0, 'rgba(255,255,255,0.95)');
    core.addColorStop(0.3, 'rgba(0,240,255,0.7)');
    core.addColorStop(0.7, 'rgba(157,75,255,0.35)');
    core.addColorStop(1, 'rgba(157,75,255,0)');
    ctx.fillStyle = core;
    ctx.beginPath();
    ctx.arc(p.x, p.y, R, 0, Math.PI * 2);
    ctx.fill();

    // outer ring (cyan) rotating one way
    ctx.shadowBlur = 24;
    ctx.shadowColor = CYAN;
    ctx.strokeStyle = CYAN;
    ctx.lineWidth = 4;
    ctx.beginPath();
    var seg = 40;
    for (var i = 0; i <= seg; i++) {
      var ang = (i / seg) * Math.PI * 2 + time * 0.6;
      var rr = R * 0.82 + Math.sin(ang * 6 + time * 2) * 4;
      var x = p.x + Math.cos(ang) * rr;
      var y = p.y + Math.sin(ang) * rr;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // inner ring (magenta) rotating the opposite way
    ctx.shadowColor = MAGENTA;
    ctx.strokeStyle = MAGENTA;
    ctx.lineWidth = 3;
    ctx.beginPath();
    for (var j = 0; j <= seg; j++) {
      var ang2 = (j / seg) * Math.PI * 2 - time * 0.9;
      var rr2 = R * 0.5 + Math.cos(ang2 * 5 - time * 2) * 3;
      var x2 = p.x + Math.cos(ang2) * rr2;
      var y2 = p.y + Math.sin(ang2) * rr2;
      if (j === 0) ctx.moveTo(x2, y2); else ctx.lineTo(x2, y2);
    }
    ctx.stroke();

    ctx.restore();
  }

  function drawParticles(ctx, cam, time) {
    for (var i = 0; i < scene.particles.length; i++) {
      var p = scene.particles[i];
      var pr = E.project(cam, [p.x, p.y, p.z]);
      if (!pr) continue;
      var col = CRYSTAL_COLORS[p.colorIndex];
      var rgb = E.hexToRgb(col);
      ctx.globalAlpha = 0.7;
      ctx.fillStyle = 'rgba(' + rgb[0] + ',' + rgb[1] + ',' + rgb[2] + ',0.9)';
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, 2.2, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  scene.buildStructure = buildStructure;
  scene.buildCrystals = buildCrystals;
  scene.buildStars = buildStars;
  scene.buildParticles = buildParticles;
  scene.updateParticles = updateParticles;
  scene.crystalPolys = crystalPolys;
  scene.drawBackground = drawBackground;
  scene.drawStars = drawStars;
  scene.drawGrid = drawGrid;
  scene.drawPortal = drawPortal;
  scene.drawParticles = drawParticles;

  global.Scene = scene;
})(window);
