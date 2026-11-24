// engine3d.js - minimal software 3D renderer (Canvas 2D, no WebGL, no libs)
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
  function len(a) { return Math.sqrt(dot(a, a)); }
  function norm(a) {
    var l = len(a) || 1;
    return [a[0] / l, a[1] / l, a[2] / l];
  }

  // ---- camera look-at: builds view basis (right, up, forward) ----
  function makeCamera(eye, target, up) {
    var f = norm(sub(target, eye));          // forward
    var r = norm(cross(f, up));             // right
    var u = cross(r, f);                    // true up
    return { eye: eye, target: target, f: f, r: r, u: u };
  }

  // world -> camera space
  function toCamera(cam, p) {
    var d = sub(p, cam.eye);
    return [dot(d, cam.r), dot(d, cam.u), dot(d, cam.f)];
  }

  // perspective projection. Returns null if behind camera.
  function project(cam, p, w, h, fov) {
    var c = toCamera(cam, p);
    if (c[2] <= 0.0001) return null;
    var f = (h / 2) / Math.tan(fov / 2);
    var x = (c[0] / c[2]) * f;
    var y = (c[1] / c[2]) * f;
    return { x: w / 2 + x, y: h / 2 - y, z: c[2] };
  }

  // face normal from 3 world-space vertices
  function faceNormal(a, b, c) {
    return norm(cross(sub(b, a), sub(c, a)));
  }

  // flat shading: brightness from light direction
  function shade(n, light) {
    var d = dot(n, light);
    if (d < 0) d = 0;
    return d;
  }

  // backface culling: keep face if normal faces camera
  function visible(cam, a, b, c) {
    var n = faceNormal(a, b, c);
    var toCam = norm(sub(cam.eye, a));
    return dot(n, toCam) > 0;
  }

  // painter's algorithm: sort polys far -> near by average depth
  function sortPolys(polys) {
    polys.sort(function (a, b) { return b.depth - a.depth; });
    return polys;
  }

  global.Engine3D = {
    sub: sub, add: add, scale: scale, dot: dot, cross: cross,
    len: len, norm: norm, makeCamera: makeCamera, toCamera: toCamera,
    project: project, faceNormal: faceNormal, shade: shade,
    visible: visible, sortPolys: sortPolys
  };
})(window);
