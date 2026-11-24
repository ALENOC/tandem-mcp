/* engine3d.js - self-contained software 3D renderer (Canvas 2D, no WebGL).
 * Provides vec3 math, perspective projection, camera lookAt, back-face
 * culling, painter's-algorithm depth sort, and flat shading with a
 * directional light plus emissive neon colors drawn via ctx 2D paths.
 */
(function (global) {
  'use strict';

  // ---- vec3 math -------------------------------------------------------
  function sub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
  function add(a, b) { return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]; }
  function scale(a, s) { return [a[0] * s, a[1] * s, a[2] * s]; }
  function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
  function cross(a, b) {
    return [
      a[1] * b[2] - a[2] * b[1],
      a[2] * b[0] - a[0] * b[2],
      a[0] * b[1] - a[1] * b[0]
    ];
  }
  function length(a) { return Math.sqrt(dot(a, a)); }
  function normalize(a) {
    var l = length(a);
    if (l < 1e-8) return [0, 0, 0];
    return [a[0] / l, a[1] / l, a[2] / l];
  }

  // ---- color helpers ---------------------------------------------------
  function hexToRgb(hex) {
    var h = hex.replace('#', '');
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function clamp255(v) { v = v | 0; return v < 0 ? 0 : (v > 255 ? 255 : v); }
  function rgbStr(r, g, b) { return 'rgb(' + clamp255(r) + ',' + clamp255(g) + ',' + clamp255(b) + ')'; }

  // ---- camera (lookAt) -------------------------------------------------
  function makeCamera(eye, target, up, fov, w, h) {
    var forward = normalize(sub(target, eye));
    var right = normalize(cross(forward, up));
    var upV = cross(right, forward);
    var focal = (h / 2) / Math.tan(fov / 2);
    return {
      eye: eye, target: target, up: up,
      forward: forward, right: right, upV: upV,
      fov: fov, w: w, h: h, focal: focal
    };
  }

  // Project a world point into view space. Returns null if behind camera.
  function toView(cam, p) {
    var d = sub(p, cam.eye);
    return [dot(d, cam.right), dot(d, cam.upV), dot(d, cam.forward)];
  }
  function project(cam, p) {
    var v = toView(cam, p);
    if (v[2] <= 0.05) return null;
    var s = cam.focal / v[2];
    return {
      x: cam.w / 2 + v[0] * s,
      y: cam.h / 2 - v[1] * s,
      z: v[2]
    };
  }

  // ---- polygon drawing -------------------------------------------------
  // poly: { verts: [world vec3...], color: '#rrggbb', emissive: '#rrggbb' }
  function drawPolys(ctx, cam, polys, lightDir) {
    var list = [];
    for (var i = 0; i < polys.length; i++) {
      var poly = polys[i];
      var n = poly.verts.length;
      if (n < 3) continue;
      var view = new Array(n);
      var depth = 0;
      var ok = true;
      for (var k = 0; k < n; k++) {
        view[k] = toView(cam, poly.verts[k]);
        if (view[k][2] <= 0.05) { ok = false; break; }
        depth += view[k][2];
      }
      if (!ok) continue;
      depth /= n;

      // back-face culling: normal must face the camera
      var e1 = sub(poly.verts[1], poly.verts[0]);
      var e2 = sub(poly.verts[n - 1], poly.verts[0]);
      var normal = normalize(cross(e1, e2));
      var toCam = normalize(sub(cam.eye, poly.verts[0]));
      if (dot(normal, toCam) <= 0) continue;

      // flat shading: directional light + ambient + emissive neon
      var base = hexToRgb(poly.color);
      var em = poly.emissive ? hexToRgb(poly.emissive) : [0, 0, 0];
      var diff = Math.max(0, dot(normal, lightDir));
      var ambient = 0.22;
      var lit = ambient + diff * 0.78;
      var r = clamp255(base[0] * lit + em[0]);
      var g = clamp255(base[1] * lit + em[1]);
      var b = clamp255(base[2] * lit + em[2]);

      var pts = new Array(n);
      for (var j = 0; j < n; j++) {
        var s = cam.focal / view[j][2];
        pts[j] = [
          cam.w / 2 + view[j][0] * s,
          cam.h / 2 - view[j][1] * s
        ];
      }
      list.push({ pts: pts, depth: depth, fill: rgbStr(r, g, b), stroke: rgbStr(r, g, b) });
    }

    // painter's algorithm: far to near
    list.sort(function (a, b) { return b.depth - a.depth; });
    for (var m = 0; m < list.length; m++) {
      var it = list[m];
      ctx.beginPath();
      ctx.moveTo(it.pts[0][0], it.pts[0][1]);
      for (var q = 1; q < it.pts.length; q++) ctx.lineTo(it.pts[q][0], it.pts[q][1]);
      ctx.closePath();
      ctx.fillStyle = it.fill;
      ctx.fill();
      ctx.lineWidth = 1;
      ctx.strokeStyle = it.stroke;
      ctx.stroke();
    }
    return list.length;
  }

  global.Engine3D = {
    sub: sub, add: add, scale: scale, dot: dot, cross: cross,
    length: length, normalize: normalize,
    hexToRgb: hexToRgb, rgbStr: rgbStr,
    makeCamera: makeCamera, toView: toView, project: project,
    drawPolys: drawPolys
  };
})(window);
