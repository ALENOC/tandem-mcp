/* engine3d.js - minimal software 3D renderer (perspective + painter's algorithm) */
(function (global) {
  "use strict";

  var TAU = Math.PI * 2;

  // ---- vector helpers (plain objects {x,y,z}) ----
  function v3(x, y, z) { return { x: x, y: y, z: z }; }
  function add(a, b) { return v3(a.x + b.x, a.y + b.y, a.z + b.z); }
  function sub(a, b) { return v3(a.x - b.x, a.y - b.y, a.z - b.z); }
  function scale(a, s) { return v3(a.x * s, a.y * s, a.z * s); }
  function dot(a, b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
  function cross(a, b) {
    return v3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x);
  }
  function len(a) { return Math.sqrt(dot(a, a)); }
  function norm(a) {
    var l = len(a) || 1;
    return v3(a.x / l, a.y / l, a.z / l);
  }

  // ---- camera ----
  // World: x right, y up, z toward viewer. Camera orbits a target point.
  function makeCamera() {
    return {
      tx: 0, ty: 1.6, tz: 0,   // target
      yaw: 0.6,                 // orbit around Y
      pitch: 0.32,              // orbit tilt
      dist: 11,                 // distance from target
      fov: 520                  // focal length in px
    };
  }

  // Transform a world point into camera space. Returns {x,y,z} where z>0 is in front.
  function toCamera(p, cam) {
    var x = p.x - cam.tx;
    var y = p.y - cam.ty;
    var z = p.z - cam.tz;
    var cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw);
    var x1 = x * cy - z * sy;
    var z1 = x * sy + z * cy;
    var y1 = y;
    var cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);
    var y2 = y1 * cp - z1 * sp;
    var z2 = y1 * sp + z1 * cp;
    return v3(x1, y2, z2 + cam.dist);
  }

  // Project a camera-space point to screen. Returns {x,y,z} (z = depth for sorting).
  function project(cs, cam, w, h) {
    var z = cs.z;
    if (z < 0.1) z = 0.1;
    var s = cam.fov / z;
    return { x: w / 2 + cs.x * s, y: h / 2 - cs.y * s, z: z };
  }

  // ---- geometry builders ----
  // Axis-aligned box centered at (cx,cy,cz) with half-extents (sx,sy,sz).
  // Returns 6 faces; each face = { v: [4 world pts], n: outward normal }.
  function makeBox(cx, cy, cz, sx, sy, sz) {
    var x0 = cx - sx, x1 = cx + sx;
    var y0 = cy - sy, y1 = cy + sy;
    var z0 = cz - sz, z1 = cz + sz;
    var faces = [];
    // +Z
    faces.push({ v: [v3(x0, y0, z1), v3(x1, y0, z1), v3(x1, y1, z1), v3(x0, y1, z1)], n: v3(0, 0, 1) });
    // -Z
    faces.push({ v: [v3(x1, y0, z0), v3(x0, y0, z0), v3(x0, y1, z0), v3(x1, y1, z0)], n: v3(0, 0, -1) });
    // +X
    faces.push({ v: [v3(x1, y0, z1), v3(x1, y0, z0), v3(x1, y1, z0), v3(x1, y1, z1)], n: v3(1, 0, 0) });
    // -X
    faces.push({ v: [v3(x0, y0, z0), v3(x0, y0, z1), v3(x0, y1, z1), v3(x0, y1, z0)], n: v3(-1, 0, 0) });
    // +Y (top)
    faces.push({ v: [v3(x0, y1, z1), v3(x1, y1, z1), v3(x1, y1, z0), v3(x0, y1, z0)], n: v3(0, 1, 0) });
    // -Y (bottom)
    faces.push({ v: [v3(x0, y0, z0), v3(x1, y0, z0), v3(x1, y0, z1), v3(x0, y0, z1)], n: v3(0, -1, 0) });
    return faces;
  }

  // Regular octahedron centered at (cx,cy,cz) with radius r. Returns 8 faces.
  function makeOctahedron(cx, cy, cz, r) {
    var A = v3(cx + r, cy, cz), B = v3(cx - r, cy, cz);
    var C = v3(cx, cy + r, cz), D = v3(cx, cy - r, cz);
    var E = v3(cx, cy, cz + r), F = v3(cx, cy, cz - r);
    return [
      { v: [A, C, E], n: norm(cross(sub(C, A), sub(E, A))) },
      { v: [E, C, B], n: norm(cross(sub(C, E), sub(B, E))) },
      { v: [B, C, D], n: norm(cross(sub(C, B), sub(D, B))) },
      { v: [C, A, D], n: norm(cross(sub(C, A), sub(D, A))) },
      { v: [D, A, E], n: norm(cross(sub(A, D), sub(E, D))) },
      { v: [E, B, D], n: norm(cross(sub(B, E), sub(D, E))) },
      { v: [F, A, C], n: norm(cross(sub(A, F), sub(C, F))) },
      { v: [C, B, F], n: norm(cross(sub(B, C), sub(F, C))) }
    ];
  }

  // ---- shading ----
  // base = [r,g,b] 0..255, light = normalized direction. Returns "rgb(...)".
  function shade(base, n, light) {
    var d = dot(n, light);
    var l = 0.35 + 0.65 * (d > 0 ? d : 0);
    var r = Math.min(255, Math.round(base[0] * l));
    var g = Math.min(255, Math.round(base[1] * l));
    var b = Math.min(255, Math.round(base[2] * l));
    return "rgb(" + r + "," + g + "," + b + ")";
  }

  // ---- drawing ----
  function drawPoly(ctx, pts, fill, stroke, lw) {
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (var i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
    ctx.closePath();
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) { ctx.lineWidth = lw || 1; ctx.strokeStyle = stroke; ctx.stroke(); }
  }

  // Build a list of camera-space polys from world faces, cull back faces, project.
  // Returns array of { pts, depth, fill, stroke, lw, glow }.
  function buildPolys(faces, cam, w, h, light, base, edge, glow) {
    var out = [];
    for (var i = 0; i < faces.length; i++) {
      var f = faces[i];
      var cs = [];
      for (var j = 0; j < f.v.length; j++) cs.push(toCamera(f.v[j], cam));
      // back-face cull using camera-space normal
      var n = norm(cross(sub(cs[1], cs[0]), sub(cs[2], cs[0])));
      var toC = sub(v3(0, 0, 0), cs[0]); // from face to camera origin (approx)
      if (dot(n, toC) <= 0) continue;
      var pts = [];
      var depth = 0;
      for (var k = 0; k < cs.length; k++) {
        var p = project(cs[k], cam, w, h);
        pts.push(p);
        depth += p.z;
      }
      depth /= pts.length;
      out.push({
        pts: pts, depth: depth,
        fill: shade(base, n, light),
        stroke: edge, lw: 1.4, glow: glow
      });
    }
    return out;
  }

  // Sort back-to-front (painter's) and draw.
  function renderPolys(ctx, polys) {
    polys.sort(function (a, b) { return b.depth - a.depth; });
    for (var i = 0; i < polys.length; i++) {
      var p = polys[i];
      if (p.glow) { ctx.shadowColor = p.glow; ctx.shadowBlur = 10; }
      else ctx.shadowBlur = 0;
      drawPoly(ctx, p.pts, p.fill, p.stroke, p.lw);
    }
    ctx.shadowBlur = 0;
  }

  global.Engine = {
    TAU: TAU,
    v3: v3, add: add, sub: sub, scale: scale, dot: dot, cross: cross,
    len: len, norm: norm,
    makeCamera: makeCamera, toCamera: toCamera, project: project,
    makeBox: makeBox, makeOctahedron: makeOctahedron,
    shade: shade, drawPoly: drawPoly, buildPolys: buildPolys, renderPolys: renderPolys
  };
})(typeof window !== "undefined" ? window : this);
