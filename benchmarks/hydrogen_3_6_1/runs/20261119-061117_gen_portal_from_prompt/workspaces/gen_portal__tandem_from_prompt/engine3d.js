/* engine3d.js - minimal software 3D renderer on Canvas 2D
 * Perspective projection + painter's algorithm z-sorting.
 * No external libraries.
 */
(function (global) {
  "use strict";

  // ---- Vector / matrix helpers (column-major 4x4) ----
  function mat4Identity() {
    return new Float32Array([
      1, 0, 0, 0,
      0, 1, 0, 0,
      0, 0, 1, 0,
      0, 0, 0, 1
    ]);
  }

  function mat4Multiply(a, b) {
    // result = a * b
    const out = new Float32Array(16);
    for (let c = 0; c < 4; c++) {
      for (let r = 0; r < 4; r++) {
        let s = 0;
        for (let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k];
        out[c * 4 + r] = s;
      }
    }
    return out;
  }

  function mat4Perspective(fovY, aspect, near, far) {
    const f = 1 / Math.tan(fovY / 2);
    const nf = 1 / (near - far);
    const out = new Float32Array(16);
    out[0] = f / aspect;
    out[5] = f;
    out[10] = (far + near) * nf;
    out[11] = -1;
    out[14] = 2 * far * near * nf;
    return out;
  }

  function mat4Translate(x, y, z) {
    const m = mat4Identity();
    m[12] = x; m[13] = y; m[14] = z;
    return m;
  }

  function mat4RotateX(a) {
    const c = Math.cos(a), s = Math.sin(a);
    const m = mat4Identity();
    m[5] = c; m[6] = s; m[9] = -s; m[10] = c;
    return m;
  }

  function mat4RotateY(a) {
    const c = Math.cos(a), s = Math.sin(a);
    const m = mat4Identity();
    m[0] = c; m[2] = -s; m[8] = s; m[10] = c;
    return m;
  }

  function mat4RotateZ(a) {
    const c = Math.cos(a), s = Math.sin(a);
    const m = mat4Identity();
    m[0] = c; m[1] = s; m[4] = -s; m[5] = c;
    return m;
  }

  function mat4Scale(x, y, z) {
    const m = mat4Identity();
    m[0] = x; m[5] = y; m[10] = z;
    return m;
  }

  // Transform a point [x,y,z] by a 4x4 matrix, returns [x,y,z,w]
  function transformPoint(m, p) {
    const x = p[0], y = p[1], z = p[2];
    return [
      m[0] * x + m[4] * y + m[8] * z + m[12],
      m[1] * x + m[5] * y + m[9] * z + m[13],
      m[2] * x + m[6] * y + m[10] * z + m[14],
      m[3] * x + m[7] * y + m[11] * z + m[15]
    ];
  }

  // ---- Renderer ----
  function Renderer(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.width = 0;
    this.height = 0;
    this.dpr = 1;
    this.view = mat4Identity();
    this.proj = mat4Identity();
    this.viewProj = mat4Identity();
    this.focal = 600;
    this.resize();
  }

  Renderer.prototype.resize = function () {
    const dpr = Math.min(2, (global.devicePixelRatio || 1));
    this.dpr = dpr;
    const w = global.innerWidth;
    const h = global.innerHeight;
    this.width = w;
    this.height = h;
    this.canvas.width = Math.floor(w * dpr);
    this.canvas.height = Math.floor(h * dpr);
    this.canvas.style.width = w + "px";
    this.canvas.style.height = h + "px";
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.focal = Math.min(w, h) * 1.15;
  };

  // Build view matrix from orbit camera parameters.
  Renderer.prototype.setCamera = function (yaw, pitch, dist, target) {
    const cy = Math.cos(yaw), sy = Math.sin(yaw);
    const cp = Math.cos(pitch), sp = Math.sin(pitch);
    // camera position on a sphere around target
    const cx = target[0] + dist * cp * sy;
    const cy2 = target[1] + dist * sp;
    const cz = target[2] + dist * cp * cy;
    // look-at basis
    let fx = target[0] - cx, fy = target[1] - cy2, fz = target[2] - cz;
    const fl = Math.hypot(fx, fy, fz) || 1;
    fx /= fl; fy /= fl; fz /= fl;
    // up = +Y, right = normalize(cross(up, f))
    let rx = fz, ry = 0, rz = -fx;
    const rl = Math.hypot(rx, ry, rz) || 1;
    rx /= rl; ry /= rl; rz /= rl;
    // up2 = cross(f, r)
    const ux = fy * rz - fz * ry;
    const uy = fz * rx - fx * rz;
    const uz = fx * ry - fy * rx;
    // view matrix (world -> camera)
    const m = new Float32Array(16);
    m[0] = rx; m[4] = ry; m[8] = rz; m[12] = -(rx * cx + ry * cy2 + rz * cz);
    m[1] = ux; m[5] = uy; m[9] = uz; m[13] = -(ux * cx + uy * cy2 + uz * cz);
    m[2] = -fx; m[6] = -fy; m[10] = -fz; m[14] = (fx * cx + fy * cy2 + fz * cz);
    m[3] = 0; m[7] = 0; m[11] = 0; m[15] = 1;
    this.view = m;
    const aspect = this.width / this.height;
    this.proj = mat4Perspective(0.9, aspect, 0.1, 400);
    this.viewProj = mat4Multiply(this.proj, this.view);
  };

  // Project a world point to screen. Returns null if behind camera.
  Renderer.prototype.project = function (p) {
    const c = transformPoint(this.viewProj, p);
    if (c[3] <= 0.0001) return null;
    const nx = c[0] / c[3];
    const ny = c[1] / c[3];
    const x = (nx * 0.5 + 0.5) * this.width;
    const y = (-ny * 0.5 + 0.5) * this.height;
    return { x: x, y: y, depth: c[2] / c[3] };
  };

  // Draw a filled triangle with optional edge stroke.
  Renderer.prototype.fillTriangle = function (a, b, c, fill, stroke, lw) {
    const ctx = this.ctx;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.lineTo(c.x, c.y);
    ctx.closePath();
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = lw || 1; ctx.stroke(); }
  };

  // Draw a quad (two triangles) given 4 projected corners.
  Renderer.prototype.fillQuad = function (p0, p1, p2, p3, fill, stroke, lw) {
    const ctx = this.ctx;
    ctx.beginPath();
    ctx.moveTo(p0.x, p0.y);
    ctx.lineTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.lineTo(p3.x, p3.y);
    ctx.closePath();
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = lw || 1; ctx.stroke(); }
  };

  // ---- Geometry builders ----
  // Box centered at origin with half-extents (hx,hy,hz). Returns faces.
  // Each face: { pts: [4 world points], normal: [x,y,z] }
  function buildBox(cx, cy, cz, hx, hy, hz) {
    const x0 = cx - hx, x1 = cx + hx;
    const y0 = cy - hy, y1 = cy + hy;
    const z0 = cz - hz, z1 = cz + hz;
    const faces = [];
    // +X
    faces.push({ pts: [[x1, y0, z1], [x1, y1, z1], [x1, y1, z0], [x1, y0, z0]], normal: [1, 0, 0] });
    // -X
    faces.push({ pts: [[x0, y0, z0], [x0, y1, z0], [x0, y1, z1], [x0, y0, z1]], normal: [-1, 0, 0] });
    // +Y (top)
    faces.push({ pts: [[x0, y1, z1], [x1, y1, z1], [x1, y1, z0], [x0, y1, z0]], normal: [0, 1, 0] });
    // -Y (bottom)
    faces.push({ pts: [[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1]], normal: [0, -1, 0] });
    // +Z
    faces.push({ pts: [[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], normal: [0, 0, 1] });
    // -Z
    faces.push({ pts: [[x1, y0, z0], [x0, y0, z0], [x0, y1, z0], [x1, y1, z0]], normal: [0, 0, -1] });
    return faces;
  }

  // Octahedron centered at origin with radius r. Returns 8 triangles.
  function buildOctahedron(cx, cy, cz, r) {
    const t = [cx, cy + r, cz];
    const b = [cx, cy - r, cz];
    const e = [cx + r, cy, cz];
    const w = [cx - r, cy, cz];
    const n = [cx, cy, cz + r];
    const s = [cx, cy, cz - r];
    return [
      [t, e, n], [t, n, w], [t, w, s], [t, s, e],
      [b, n, e], [b, w, n], [b, s, w], [b, e, s]
    ];
  }

  global.Engine3D = {
    mat4Identity, mat4Multiply, mat4Perspective,
    mat4Translate, mat4RotateX, mat4RotateY, mat4RotateZ, mat4Scale,
    transformPoint, buildBox, buildOctahedron,
    Renderer: Renderer
  };
})(typeof window !== "undefined" ? window : globalThis);
