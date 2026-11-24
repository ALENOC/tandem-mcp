// engine3d.js - minimal software 3D renderer (vec3, rotation, perspective, painter's algorithm)
(function (global) {
  'use strict';

  function vec3(x, y, z) { return { x: x || 0, y: y || 0, z: z || 0 }; }
  function add(a, b) { return vec3(a.x + b.x, a.y + b.y, a.z + b.z); }
  function sub(a, b) { return vec3(a.x - b.x, a.y - b.y, a.z - b.z); }
  function scale(a, s) { return vec3(a.x * s, a.y * s, a.z * s); }
  function dot(a, b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
  function cross(a, b) {
    return vec3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x);
  }
  function length(a) { return Math.sqrt(dot(a, a)); }
  function normalize(a) {
    var l = length(a) || 1;
    return vec3(a.x / l, a.y / l, a.z / l);
  }
  function rotateX(v, a) {
    var c = Math.cos(a), s = Math.sin(a);
    return vec3(v.x, v.y * c - v.z * s, v.y * s + v.z * c);
  }
  function rotateY(v, a) {
    var c = Math.cos(a), s = Math.sin(a);
    return vec3(v.x * c + v.z * s, v.y, -v.x * s + v.z * c);
  }
  function rotateZ(v, a) {
    var c = Math.cos(a), s = Math.sin(a);
    return vec3(v.x * c - v.y * s, v.x * s + v.y * c, v.z);
  }

  // Camera: orbits a target. yaw/pitch/dist define position; looks at target.
  function makeCamera() {
    var cam = {
      yaw: 0, pitch: 0.32, dist: 16, target: vec3(0, 1.6, 0),
      fov: 55 * Math.PI / 180,
      pos: vec3(0, 0, 0), fwd: vec3(0, 0, -1), right: vec3(1, 0, 0), up: vec3(0, 1, 0)
    };
    cam.update = function () {
      var cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);
      var cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw);
      cam.pos = vec3(cam.dist * cp * sy, cam.dist * sp, cam.dist * cp * cy);
      cam.fwd = normalize(sub(cam.target, cam.pos));
      cam.right = normalize(cross(cam.fwd, vec3(0, 1, 0)));
      cam.up = cross(cam.right, cam.fwd);
    };
    // Transform a world point into camera space.
    cam.toCam = function (p) {
      var d = sub(p, cam.pos);
      return vec3(dot(d, cam.right), dot(d, cam.up), dot(d, cam.fwd));
    };
    // Perspective project a camera-space point. Returns null if behind camera.
    cam.project = function (cp, w, h) {
      if (cp.z <= 0.05) return null;
      var f = (h * 0.5) / Math.tan(cam.fov * 0.5);
      return { x: w * 0.5 + (cp.x * f) / cp.z, y: h * 0.5 - (cp.y * f) / cp.z, z: cp.z };
    };
    return cam;
  }

  // Build a list of renderable polygons from world-space triangles.
  // polys: array of { pts:[vec3...], color:[r,g,b], edge:[r,g,b], glow:number }
  function buildPolys(cam, polys, w, h) {
    var out = [];
    for (var i = 0; i < polys.length; i++) {
      var p = polys[i];
      var pts = p.pts;
      var n = pts.length;
      if (n < 3) continue;
      var camPts = [];
      var ok = true;
      var depth = 0;
      for (var j = 0; j < n; j++) {
        var cp = cam.toCam(pts[j]);
        depth += cp.z;
        if (cp.z <= 0.05) { ok = false; break; }
        camPts.push(cp);
      }
      if (!ok) continue;
      depth /= n;
      // Back-face culling using world-space normal vs view direction.
      var e1 = sub(pts[1], pts[0]);
      var e2 = sub(pts[n - 1], pts[0]);
      var normal = normalize(cross(e1, e2));
      var view = sub(pts[0], cam.pos);
      if (dot(normal, view) >= 0) continue;
      var proj = [];
      for (var k = 0; k < n; k++) {
        var pr = cam.project(camPts[k], w, h);
        if (!pr) { ok = false; break; }
        proj.push(pr);
      }
      if (!ok) continue;
      // Flat shading: face normal vs light direction.
      var light = normalize(vec3(-0.4, 0.9, -0.5));
      var lambert = Math.max(0, dot(normal, light));
      var shade = 0.35 + 0.65 * lambert;
      var col = p.color;
      var fill = 'rgb(' + Math.min(255, col[0] * shade | 0) + ',' + Math.min(255, col[1] * shade | 0) + ',' + Math.min(255, col[2] * shade | 0) + ')';
      out.push({ proj: proj, depth: depth, fill: fill, edge: p.edge, glow: p.glow });
    }
    // Painter's algorithm: far to near.
    out.sort(function (a, b) { return b.depth - a.depth; });
    return out;
  }

  function drawPolys(ctx, polys) {
    for (var i = 0; i < polys.length; i++) {
      var p = polys[i];
      var pts = p.proj;
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      for (var j = 1; j < pts.length; j++) ctx.lineTo(pts[j].x, pts[j].y);
      ctx.closePath();
      ctx.fillStyle = p.fill;
      ctx.fill();
      if (p.edge) {
        ctx.save();
        ctx.shadowColor = 'rgb(' + p.edge[0] + ',' + p.edge[1] + ',' + p.edge[2] + ')';
        ctx.shadowBlur = p.glow || 12;
        ctx.strokeStyle = 'rgb(' + p.edge[0] + ',' + p.edge[1] + ',' + p.edge[2] + ')';
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.restore();
      }
    }
  }

  global.Engine3D = {
    vec3: vec3, add: add, sub: sub, scale: scale, dot: dot, cross: cross,
    length: length, normalize: normalize, rotateX: rotateX, rotateY: rotateY, rotateZ: rotateZ,
    makeCamera: makeCamera, buildPolys: buildPolys, drawPolys: drawPolys
  };
})(window);
