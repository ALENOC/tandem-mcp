// engine3d.js - software 3D renderer on Canvas 2D (no WebGL)
// Vector math, perspective projection, backface culling, painter's algorithm.

(function (global) {
  "use strict";

  // ---- Vector helpers (plain objects {x,y,z}) ----
  function v3(x, y, z) { return { x: x || 0, y: y || 0, z: z || 0 }; }
  function add(a, b) { return v3(a.x + b.x, a.y + b.y, a.z + b.z); }
  function sub(a, b) { return v3(a.x - b.x, a.y - b.y, a.z - b.z); }
  function scale(a, s) { return v3(a.x * s, a.y * s, a.z * s); }
  function dot(a, b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
  function cross(a, b) {
    return v3(
      a.y * b.z - a.z * b.y,
      a.z * b.x - a.x * b.z,
      a.x * b.y - a.y * b.x
    );
  }
  function len(a) { return Math.sqrt(dot(a, a)); }
  function norm(a) {
    var l = len(a) || 1;
    return v3(a.x / l, a.y / l, a.z / l);
  }

  // ---- Rotation matrices (column-major applied to vectors) ----
  function rotX(a) {
    var c = Math.cos(a), s = Math.sin(a);
    return [[1, 0, 0], [0, c, -s], [0, s, c]];
  }
  function rotY(a) {
    var c = Math.cos(a), s = Math.sin(a);
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]];
  }
  function rotZ(a) {
    var c = Math.cos(a), s = Math.sin(a);
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]];
  }
  function mulMat(a, b) {
    var out = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
    for (var i = 0; i < 3; i++)
      for (var j = 0; j < 3; j++)
        for (var k = 0; k < 3; k++)
          out[i][j] += a[i][k] * b[k][j];
    return out;
  }
  function applyMat(m, p) {
    return v3(
      m[0][0] * p.x + m[0][1] * p.y + m[0][2] * p.z,
      m[1][0] * p.x + m[1][1] * p.y + m[1][2] * p.z,
      m[2][0] * p.x + m[2][1] * p.y + m[2][2] * p.z
    );
  }

  // ---- Camera ----
  // Camera orbits a target. We transform world points into camera space
  // (camera looks down -Z), then perspective-project.
  function makeCamera() {
    return {
      target: v3(0, 1.2, 0),
      radius: 9,
      angle: 0,
      height: 3.2,
      fov: 55 * Math.PI / 180,
      pos: v3(0, 3.2, 9)
    };
  }

  function updateCamera(cam, dt) {
    cam.angle += dt * 0.25;
    cam.pos = v3(
      cam.target.x + Math.cos(cam.angle) * cam.radius,
      cam.height,
      cam.target.z + Math.sin(cam.angle) * cam.radius
    );
  }

  // Build camera basis (right, up, forward) from position + target.
  function cameraBasis(cam) {
    var fwd = norm(sub(cam.target, cam.pos)); // forward
    var right = norm(cross(fwd, v3(0, 1, 0)));
    var up = cross(right, fwd);
    return { fwd: fwd, right: right, up: up };
  }

  // Transform a world point into camera space.
  function toCamera(cam, basis, p) {
    var d = sub(p, cam.pos);
    return v3(
      dot(d, basis.right),
      dot(d, basis.up),
      dot(d, basis.fwd)
    );
  }

  // Perspective projection. Returns null if behind the near plane.
  function project(cam, p) {
    var f = (cam.fov * 0.5) / Math.tan(cam.fov * 0.5);
    if (p.z <= 0.1) return null;
    return {
      x: (p.x * f) / p.z,
      y: (p.y * f) / p.z,
      z: p.z
    };
  }

  // ---- Geometry builders ----
  // Box centered at origin, half-extents (hx,hy,hz). Returns 6 faces,
  // each face = { verts: [4 world pts], normal (local) }.
  function makeBox(hx, hy, hz) {
    var x = hx, y = hy, z = hz;
    var faces = [
      { n: v3(0, 0, 1), v: [v3(-x, -y, z), v3(x, -y, z), v3(x, y, z), v3(-x, y, z)] },
      { n: v3(0, 0, -1), v: [v3(x, -y, -z), v3(-x, -y, -z), v3(-x, y, -z), v3(x, y, -z)] },
      { n: v3(1, 0, 0), v: [v3(x, -y, z), v3(x, -y, -z), v3(x, y, -z), v3(x, y, z)] },
      { n: v3(-1, 0, 0), v: [v3(-x, -y, -z), v3(-x, -y, z), v3(-x, y, z), v3(-x, y, -z)] },
      { n: v3(0, 1, 0), v: [v3(-x, y, z), v3(x, y, z), v3(x, y, -z), v3(-x, y, -z)] },
      { n: v3(0, -1, 0), v: [v3(-x, -y, -z), v3(x, -y, -z), v3(x, -y, z), v3(-x, -y, z)] }
    ];
    return faces;
  }

  // Octahedron: 6 vertices, 8 triangular faces.
  function makeOctahedron(r) {
    var t = v3(0, r, 0), b = v3(0, -r, 0);
    var a = v3(r, 0, 0), b2 = v3(-r, 0, 0), c = v3(0, 0, r), d = v3(0, 0, -r);
    return [
      [a, t, c], [c, t, b2], [b2, t, d], [d, t, a],
      [a, b, c], [c, b, b2], [b2, b, d], [d, b, a]
    ];
  }

  // ---- Renderer ----
  function Renderer(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.w = 0;
    this.h = 0;
    this.dpr = 1;
    this.resize();
  }

  Renderer.prototype.resize = function () {
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.w = window.innerWidth;
    this.h = window.innerHeight;
    this.canvas.width = Math.floor(this.w * this.dpr);
    this.canvas.height = Math.floor(this.h * this.dpr);
    this.canvas.style.width = this.w + "px";
    this.canvas.style.height = this.h + "px";
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
  };

  // Draw a filled polygon from projected screen points (CSS px).
  Renderer.prototype.fillPoly = function (pts, fill, stroke, glow) {
    var ctx = this.ctx;
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (var i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
    ctx.closePath();
    if (glow) {
      ctx.shadowColor = glow;
      ctx.shadowBlur = 12;
    }
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.shadowBlur = 0;
    if (stroke) {
      ctx.strokeStyle = stroke;
      ctx.lineWidth = 1;
      ctx.stroke();
    }
  };

  // Draw a set of 3D faces. Each face: { verts:[world pts], color, stroke, glow, alpha }
  // Applies transform matrix + translation, backface culls, sorts by depth.
  Renderer.prototype.drawFaces = function (cam, basis, faces, mat, trans) {
    var polys = [];
    for (var i = 0; i < faces.length; i++) {
      var f = faces[i];
      var fv = f.verts || f.v;
      var world = [];
      for (var j = 0; j < fv.length; j++) {
        var p = applyMat(mat, fv[j]);
        world.push(add(p, trans));
      }
      // Backface culling: normal in camera space, cull if facing away.
      var n = applyMat(mat, f.n);
      var toCam = sub(cam.pos, world[0]);
      if (dot(n, toCam) <= 0) continue;
      // Project
      var camPts = [];
      var ok = true;
      var depth = 0;
      for (var k = 0; k < world.length; k++) {
        var cp = toCamera(cam, basis, world[k]);
        depth += cp.z;
        var pr = project(cam, cp);
        if (!pr) { ok = false; break; }
        camPts.push(pr);
      }
      if (!ok) continue;
      depth /= world.length;
      polys.push({ pts: camPts, depth: depth, color: f.color, stroke: f.stroke, glow: f.glow, alpha: f.alpha });
    }
    // Painter's algorithm: far to near.
    polys.sort(function (a, b) { return b.depth - a.depth; });
    var ctx = this.ctx;
    var cx = this.w / 2, cy = this.h / 2;
    for (var m = 0; m < polys.length; m++) {
      var poly = polys[m];
      var screen = [];
      for (var s = 0; s < poly.pts.length; s++) {
        screen.push({ x: cx + poly.pts[s].x * (this.h * 0.5), y: cy - poly.pts[s].y * (this.h * 0.5) });
      }
      var fill = poly.color;
      if (poly.alpha != null && poly.alpha < 1) {
        ctx.globalAlpha = poly.alpha;
      }
      this.fillPoly(screen, fill, poly.stroke, poly.glow);
      if (poly.alpha != null && poly.alpha < 1) ctx.globalAlpha = 1;
    }
    return polys.length;
  };

  global.Engine = {
    v3: v3, add: add, sub: sub, scale: scale, dot: dot, cross: cross,
    len: len, norm: norm, rotX: rotX, rotY: rotY, rotZ: rotZ,
    mulMat: mulMat, applyMat: applyMat, makeCamera: makeCamera,
    updateCamera: updateCamera, cameraBasis: cameraBasis, toCamera: toCamera,
    project: project, makeBox: makeBox, makeOctahedron: makeOctahedron,
    Renderer: Renderer
  };
})(typeof window !== "undefined" ? window : this);
