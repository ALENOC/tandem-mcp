// engine3d.js
// Software 3D renderer: vector math, perspective projection,
// painter's-algorithm triangle renderer with flat shading.
// No WebGL, no libraries.

(function (global) {
  "use strict";

  // ---- Vector math ----
  function v3(x, y, z) { return { x: x, y: y, z: z }; }
  function add(a, b) { return { x: a.x + b.x, y: a.y + b.y, z: a.z + b.z }; }
  function sub(a, b) { return { x: a.x - b.x, y: a.y - b.y, z: a.z - b.z }; }
  function scale(a, s) { return { x: a.x * s, y: a.y * s, z: a.z * s }; }
  function dot(a, b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
  function cross(a, b) {
    return {
      x: a.y * b.z - a.z * b.y,
      y: a.z * b.x - a.x * b.z,
      z: a.x * b.y - a.y * b.x
    };
  }
  function len(a) { return Math.sqrt(dot(a, a)); }
  function normalize(a) {
    var l = len(a) || 1;
    return { x: a.x / l, y: a.y / l, z: a.z / l };
  }

  // ---- Camera (look-at) ----
  // Returns a transform that maps world points into camera space.
  function makeCamera(eye, target, up) {
    var f = normalize(sub(target, eye));   // forward
    var r = normalize(cross(f, up));       // right
    var u = cross(r, f);                   // up
    return {
      eye: eye,
      toCam: function (p) {
        var d = sub(p, eye);
        return { x: dot(d, r), y: dot(d, u), z: dot(d, f) };
      }
    };
  }

  // ---- Perspective projection ----
  function makeProjection(focal, width, height) {
    return {
      focal: focal,
      width: width,
      height: height,
      project: function (cp) {
        var s = focal / cp.z;
        return {
          x: width / 2 + cp.x * s,
          y: height / 2 - cp.y * s,
          z: cp.z,
          s: s
        };
      }
    };
  }

  // ---- Painter's-algorithm triangle renderer with flat shading ----
  function Renderer(ctx) {
    this.ctx = ctx;
    this.tris = [];
    this.count = 0;
  }

  Renderer.prototype.begin = function () {
    this.tris = [];
    this.count = 0;
  };

  // a, b, c are camera-space points {x,y,z}.
  // color: css color string, glow: shadowBlur px, alpha: 0..1
  Renderer.prototype.triangle = function (a, b, c, color, glow, alpha) {
    var depth = (a.z + b.z + c.z) / 3;
    this.tris.push({ a: a, b: b, c: c, color: color, glow: glow, alpha: alpha, depth: depth });
  };

  Renderer.prototype.render = function () {
    var self = this;
    // far to near
    this.tris.sort(function (p, q) { return q.depth - p.depth; });
    var ctx = this.ctx;
    for (var i = 0; i < this.tris.length; i++) {
      var t = this.tris[i];
      var pa = this.proj.project(t.a);
      var pb = this.proj.project(t.b);
      var pc = this.proj.project(t.c);
      ctx.save();
      ctx.globalAlpha = t.alpha;
      ctx.fillStyle = t.color;
      if (t.glow) {
        ctx.shadowColor = t.color;
        ctx.shadowBlur = t.glow;
      }
      ctx.beginPath();
      ctx.moveTo(pa.x, pa.y);
      ctx.lineTo(pb.x, pb.y);
      ctx.lineTo(pc.x, pc.y);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
      this.count++;
    }
    this.tris = [];
    return this.count;
  };

  // ---- Flat shading: pick a face color from a base color by normal ----
  // light direction is fixed; brightness in [0.35, 1.0]
  function shade(base, normal, light) {
    var d = dot(normal, light);
    if (d < 0) d = 0;
    var b = 0.35 + 0.65 * d;
    return shadeColor(base, b);
  }

  // base: {r,g,b}, returns css rgb string scaled by brightness
  function shadeColor(base, b) {
    var r = Math.min(255, Math.round(base.r * b));
    var g = Math.min(255, Math.round(base.g * b));
    var bl = Math.min(255, Math.round(base.b * b));
    return "rgb(" + r + "," + g + "," + bl + ")";
  }

  global.Engine3D = {
    v3: v3, add: add, sub: sub, scale: scale, dot: dot, cross: cross,
    len: len, normalize: normalize,
    makeCamera: makeCamera, makeProjection: makeProjection,
    Renderer: Renderer, shade: shade, shadeColor: shadeColor
  };
})(window);
