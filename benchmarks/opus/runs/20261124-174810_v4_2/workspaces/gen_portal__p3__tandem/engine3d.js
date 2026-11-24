// engine3d.js - custom software 3D renderer (no WebGL, no libraries)
(function (global) {
  "use strict";

  // ---- vec3 math ----
  function vec3(x, y, z) { return { x: x || 0, y: y || 0, z: z || 0 }; }
  function v3add(a, b) { return vec3(a.x + b.x, a.y + b.y, a.z + b.z); }
  function v3sub(a, b) { return vec3(a.x - b.x, a.y - b.y, a.z - b.z); }
  function v3scale(a, s) { return vec3(a.x * s, a.y * s, a.z * s); }
  function v3dot(a, b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
  function v3cross(a, b) {
    return vec3(
      a.y * b.z - a.z * b.y,
      a.z * b.x - a.x * b.z,
      a.x * b.y - a.y * b.x
    );
  }
  function v3len(a) { return Math.sqrt(v3dot(a, a)); }
  function v3norm(a) {
    var l = v3len(a) || 1;
    return vec3(a.x / l, a.y / l, a.z / l);
  }

  // ---- camera lookAt: builds view matrix (world -> camera space) ----
  function lookAt(eye, target, up) {
    var f = v3norm(v3sub(target, eye));      // forward (camera looks along -z)
    var s = v3norm(v3cross(f, up));          // right
    var u = v3cross(s, f);                  // true up
    // view matrix rows
    return {
      eye: eye,
      f: f, s: s, u: u,
      // transform a world point into camera space
      toCam: function (p) {
        var d = v3sub(p, eye);
        return vec3(
          v3dot(d, s),
          v3dot(d, u),
          v3dot(d, f)
        );
      }
    };
  }

  // ---- perspective projection ----
  function project(cam, p, width, height, fov) {
    var c = cam.toCam(p);
    var f = (height / 2) / Math.tan(fov / 2);
    var z = c.z;
    if (z <= 0.1) z = 0.1; // clip near
    var sx = (c.x / z) * f + width / 2;
    var sy = height / 2 - (c.y / z) * f;
    return { x: sx, y: sy, z: z, cam: c };
  }

  // ---- flat shading with a directional light ----
  var LIGHT = v3norm(vec3(-0.4, 0.9, -0.5));
  function shade(base, normal, light) {
    var d = Math.max(0, v3dot(normal, light));
    var amb = 0.35;
    var k = amb + (1 - amb) * d;
    return {
      r: Math.min(255, base.r * k),
      g: Math.min(255, base.g * k),
      b: Math.min(255, base.b * k)
    };
  }

  // ---- back-face culling: returns true if face is front-facing ----
  function isFrontFace(cam, verts) {
    // normal in world space
    var e1 = v3sub(verts[1], verts[0]);
    var e2 = v3sub(verts[2], verts[0]);
    var n = v3cross(e1, e2);
    // vector from face to camera
    var toCam = v3sub(cam.eye, verts[0]);
    return v3dot(n, toCam) > 0;
  }

  // ---- painter's algorithm: sort faces back to front ----
  function depthSort(faces, cam) {
    for (var i = 0; i < faces.length; i++) {
      var f = faces[i];
      var z = 0;
      for (var j = 0; j < f.pts.length; j++) z += f.pts[j].z;
      f.depth = z / f.pts.length;
    }
    faces.sort(function (a, b) { return b.depth - a.depth; });
    return faces;
  }

  // ---- draw a filled polygon with neon edge stroke ----
  function drawPoly(ctx, pts, fill, edge, glow) {
    if (pts.length < 3) return;
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (var i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
    if (edge) {
      ctx.save();
      ctx.strokeStyle = edge;
      ctx.lineWidth = 1.5;
      ctx.shadowColor = glow || edge;
      ctx.shadowBlur = 8;
      ctx.stroke();
      ctx.restore();
    }
  }

  global.Engine3D = {
    vec3: vec3,
    v3add: v3add,
    v3sub: v3sub,
    v3scale: v3scale,
    v3dot: v3dot,
    v3cross: v3cross,
    v3len: v3len,
    v3norm: v3norm,
    lookAt: lookAt,
    project: project,
    shade: shade,
    isFrontFace: isFrontFace,
    depthSort: depthSort,
    drawPoly: drawPoly,
    LIGHT: LIGHT
  };
})(window);
