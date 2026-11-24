// engine3d.js - minimal software 3D renderer on CanvasRenderingContext2D
(function (global) {
  'use strict';

  // ---- vec3 math ----
  function v3(x, y, z) { return { x: x, y: y, z: z }; }
  function v3add(a, b) { return v3(a.x + b.x, a.y + b.y, a.z + b.z); }
  function v3sub(a, b) { return v3(a.x - b.x, a.y - b.y, a.z - b.z); }
  function v3scale(a, s) { return v3(a.x * s, a.y * s, a.z * s); }
  function v3dot(a, b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
  function v3cross(a, b) {
    return v3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x);
  }
  function v3len(a) { return Math.sqrt(v3dot(a, a)); }
  function v3norm(a) {
    var l = v3len(a) || 1;
    return v3(a.x / l, a.y / l, a.z / l);
  }

  // ---- color helpers ----
  function hexToRgb(hex) {
    hex = hex.replace('#', '');
    if (hex.length === 3) hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
    var n = parseInt(hex, 16);
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
  }
  function rgba(r, g, b, a) {
    return 'rgba(' + (r | 0) + ',' + (g | 0) + ',' + (b | 0) + ',' + a + ')';
  }

  // ---- camera (lookAt) ----
  // Right-handed; camera looks down -z in view space.
  function makeCamera(eye, target, up) {
    var f = v3norm(v3sub(target, eye));
    var s = v3norm(v3cross(f, up));
    var u = v3cross(s, f);
    return {
      eye: eye,
      f: f, s: s, u: u,
      toView: function (p) {
        var d = v3sub(p, eye);
        return v3(v3dot(d, s), v3dot(d, u), -v3dot(d, f));
      }
    };
  }

  // ---- perspective projection ----
  var FOV = 60 * Math.PI / 180;
  var NEAR = 0.1;
  var FOCAL = 1 / Math.tan(FOV / 2);

  // project a view-space point to screen; returns null if behind near plane
  function project(vp, width, height) {
    if (vp.z >= -NEAR) return null;
    var inv = FOCAL / (-vp.z);
    var sx = (vp.x * inv * 0.5 + 0.5) * width;
    var sy = (0.5 - vp.y * inv * 0.5) * height;
    return { x: sx, y: sy, z: vp.z };
  }

  // ---- flat shading ----
  var LIGHT = v3norm(v3(0.4, 0.8, 0.3));
  var AMBIENT = 0.35;

  // normal from three world-space vertices (right-hand order)
  function faceNormal(a, b, c) {
    return v3norm(v3cross(v3sub(b, a), v3sub(c, a)));
  }

  // Lambert term for a face normal (world space)
  function shade(n) {
    var l = Math.max(0, v3dot(n, LIGHT));
    return AMBIENT + (1 - AMBIENT) * l;
  }

  // ---- renderer ----
  // faces: array of { verts: [world v3...], color: hex, edge: hex }
  // returns number of polygons actually drawn (after culling)
  function renderFaces(ctx, cam, faces, width, height) {
    var drawn = 0;
    var list = [];
    for (var i = 0; i < faces.length; i++) {
      var face = faces[i];
      var vs = face.verts;
      var n = vs.length;
      if (n < 3) continue;
      var view = new Array(n);
      var sumz = 0;
      for (var k = 0; k < n; k++) {
        view[k] = cam.toView(vs[k]);
        sumz += view[k].z;
      }
      var avgz = sumz / n;
      // back-face culling: normal in view space, keep if facing camera (z<0)
      var nrm = faceNormal(vs[0], vs[1], vs[2]);
      var nv = cam.toView(v3add(vs[0], nrm));
      var facing = (nv.z - view[0].z) < 0;
      if (!facing) continue;
      list.push({ view: view, avgz: avgz, color: face.color, edge: face.edge, shade: shade(nrm) });
    }
    // painter's algorithm: far (more negative z) to near
    list.sort(function (a, b) { return a.avgz - b.avgz; });
    for (var j = 0; j < list.length; j++) {
      var item = list[j];
      var pts = new Array(item.view.length);
      var ok = true;
      for (var m = 0; m < item.view.length; m++) {
        var p = project(item.view[m], width, height);
        if (!p) { ok = false; break; }
        pts[m] = p;
      }
      if (!ok) continue;
      var base = hexToRgb(item.color);
      var sh = item.shade;
      ctx.beginPath();
      ctx.moveTo(pts[0].x, pts[0].y);
      for (var q = 1; q < pts.length; q++) ctx.lineTo(pts[q].x, pts[q].y);
      ctx.closePath();
      ctx.fillStyle = rgba(base.r * sh, base.g * sh, base.b * sh, 1);
      ctx.fill();
      ctx.lineWidth = 1;
      ctx.strokeStyle = rgba(hexToRgb(item.edge).r, hexToRgb(item.edge).g, hexToRgb(item.edge).b, 0.9);
      ctx.stroke();
      drawn++;
    }
    return drawn;
  }

  global.Engine3D = {
    v3: v3, v3add: v3add, v3sub: v3sub, v3scale: v3scale,
    v3dot: v3dot, v3cross: v3cross, v3len: v3len, v3norm: v3norm,
    hexToRgb: hexToRgb, rgba: rgba,
    makeCamera: makeCamera, project: project,
    faceNormal: faceNormal, shade: shade, renderFaces: renderFaces,
    FOCAL: FOCAL, NEAR: NEAR, LIGHT: LIGHT, AMBIENT: AMBIENT
  };
})(window);
