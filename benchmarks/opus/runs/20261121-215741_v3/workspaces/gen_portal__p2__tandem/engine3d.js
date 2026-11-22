// engine3d.js - software 3D renderer (no WebGL, no libraries)
// Vector/matrix math, perspective projection, back-face culling,
// painter's algorithm depth sort, flat shading (directional light + emissive).
(function (global) {
  'use strict';

  // ---- vector math ----
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
    var l = length(a) || 1;
    return [a[0] / l, a[1] / l, a[2] / l];
  }

  // ---- camera (view matrix) ----
  // Camera looks down -z in camera space. Basis: right, up, back.
  function makeCamera(eye, target, up) {
    up = up || [0, 1, 0];
    var back = normalize(sub(eye, target));
    var right = normalize(cross(back, up));
    var upv = cross(right, back);
    return {
      eye: eye,
      target: target,
      right: right,
      up: upv,
      back: back
    };
  }

  // Transform a world point into camera space.
  function toCamera(p, cam) {
    var d = sub(p, cam.eye);
    return [
      dot(d, cam.right),
      dot(d, cam.up),
      dot(d, cam.back)
    ];
  }

  // Perspective projection. Returns {x, y, depth} in pixels, depth>0 in front.
  function project(p, cam, view) {
    var c = toCamera(p, cam);
    var depth = -c[2];
    var f = view.focal;
    var s = f / (depth > 0.0001 ? depth : 0.0001);
    return {
      x: view.cx + c[0] * s,
      y: view.cy - c[1] * s,
      depth: depth,
      cam: c
    };
  }

  // ---- back-face culling ----
  // A triangle is visible when its normal points toward the camera.
  function faceVisible(a, b, c, cam) {
    var n = cross(sub(b, a), sub(c, a));
    var centroid = [(a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3, (a[2] + b[2] + c[2]) / 3];
    return dot(n, sub(cam.eye, centroid)) > 0;
  }

  // ---- painter's algorithm depth sort ----
  // Sort triangles far-to-near by centroid depth so near ones draw last.
  function sortTriangles(tris, cam) {
    for (var i = 0; i < tris.length; i++) {
      var t = tris[i];
      var cx = (t.a[0] + t.b[0] + t.c[0]) / 3;
      var cy = (t.a[1] + t.b[1] + t.c[1]) / 3;
      var cz = (t.a[2] + t.b[2] + t.c[2]) / 3;
      t.depth = -dot(sub([cx, cy, cz], cam.eye), cam.back);
    }
    tris.sort(function (x, y) { return y.depth - x.depth; });
    return tris;
  }

  // ---- flat shading ----
  // Directional light direction (points toward the light).
  var LIGHT_DIR = normalize([0.4, 0.9, 0.5]);
  var AMBIENT = 0.28;

  // base: [r,g,b] 0..255, emissive: [r,g,b] 0..255
  function shade(normal, base, emissive) {
    var n = normalize(normal);
    var diff = Math.max(0, dot(n, LIGHT_DIR));
    var k = AMBIENT + (1 - AMBIENT) * diff;
    var r = Math.min(255, base[0] * k + (emissive ? emissive[0] : 0));
    var g = Math.min(255, base[1] * k + (emissive ? emissive[1] : 0));
    var b = Math.min(255, base[2] * k + (emissive ? emissive[2] : 0));
    return [r | 0, g | 0, b | 0];
  }

  function rgb(c) { return 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')'; }

  global.Engine3D = {
    sub: sub, add: add, scale: scale, dot: dot, cross: cross,
    length: length, normalize: normalize,
    makeCamera: makeCamera, toCamera: toCamera, project: project,
    faceVisible: faceVisible, sortTriangles: sortTriangles,
    shade: shade, rgb: rgb, LIGHT_DIR: LIGHT_DIR
  };
})(window);
