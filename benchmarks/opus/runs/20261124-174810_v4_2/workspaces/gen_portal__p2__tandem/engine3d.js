// engine3d.js
// Self-contained software 3D renderer (no WebGL, no libraries).
// Provides: vec3 math, perspective projection, camera lookAt, back-face
// culling, painter's algorithm (depth sort), flat shading with a directional
// light plus neon emissive edge strokes.

(function (global) {
  'use strict';

  // ---------- vec3 math ----------
  const V3 = {
    create: function (x, y, z) { return { x: x, y: y, z: z }; },
    add: function (a, b) { return { x: a.x + b.x, y: a.y + b.y, z: a.z + b.z }; },
    sub: function (a, b) { return { x: a.x - b.x, y: a.y - b.y, z: a.z - b.z }; },
    scale: function (a, s) { return { x: a.x * s, y: a.y * s, z: a.z * s }; },
    dot: function (a, b) { return a.x * b.x + a.y * b.y + a.z * b.z; },
    cross: function (a, b) {
      return {
        x: a.y * b.z - a.z * b.y,
        y: a.z * b.x - a.x * b.z,
        z: a.x * b.y - a.y * b.x
      };
    },
    length: function (a) { return Math.sqrt(a.x * a.x + a.y * a.y + a.z * a.z); },
    normalize: function (a) {
      const l = V3.length(a) || 1;
      return { x: a.x / l, y: a.y / l, z: a.z / l };
    }
  };

  // ---------- camera lookAt ----------
  // Returns an orthonormal basis. Camera looks along +f (toward target).
  function lookAt(eye, target, up) {
    const f = V3.normalize(V3.sub(target, eye));
    const s = V3.normalize(V3.cross(f, up));
    const u = V3.cross(s, f);
    return { eye: eye, f: f, s: s, u: u };
  }

  // World point -> camera space (x right, y up, z forward).
  function toCamera(cam, p) {
    const d = V3.sub(p, cam.eye);
    return {
      x: V3.dot(d, cam.s),
      y: V3.dot(d, cam.u),
      z: V3.dot(d, cam.f)
    };
  }

  // Perspective projection. Returns {x, y} in CSS pixels, plus depth z.
  function project(cam, p, width, height, fov, near) {
    const c = toCamera(cam, p);
    if (c.z < near) return null;
    const f = (height / 2) / Math.tan(fov / 2);
    return {
      x: width / 2 + (c.x * f) / c.z,
      y: height / 2 - (c.y * f) / c.z,
      z: c.z
    };
  }

  // ---------- geometry helpers ----------
  // Build a box (6 quads) from a center and half-extents. Each face has an
  // outward normal so back-face culling works.
  function makeBox(cx, cy, cz, hx, hy, hz) {
    const x0 = cx - hx, x1 = cx + hx;
    const y0 = cy - hy, y1 = cy + hy;
    const z0 = cz - hz, z1 = cz + hz;
    const faces = [
      { n: { x: 0, y: 0, z: 1 }, v: [{ x: x0, y: y0, z: z1 }, { x: x1, y: y0, z: z1 }, { x: x1, y: y1, z: z1 }, { x: x0, y: y1, z: z1 }] },
      { n: { x: 0, y: 0, z: -1 }, v: [{ x: x1, y: y0, z: z0 }, { x: x0, y: y0, z: z0 }, { x: x0, y: y1, z: z0 }, { x: x1, y: y1, z: z0 }] },
      { n: { x: 1, y: 0, z: 0 }, v: [{ x: x1, y: y0, z: z1 }, { x: x1, y: y0, z: z0 }, { x: x1, y: y1, z: z0 }, { x: x1, y: y1, z: z1 }] },
      { n: { x: -1, y: 0, z: 0 }, v: [{ x: x0, y: y0, z: z0 }, { x: x0, y: y0, z: z1 }, { x: x0, y: y1, z: z1 }, { x: x0, y: y1, z: z0 }] },
      { n: { x: 0, y: 1, z: 0 }, v: [{ x: x0, y: y1, z: z1 }, { x: x1, y: y1, z: z1 }, { x: x1, y: y1, z: z0 }, { x: x0, y: y1, z: z0 }] },
      { n: { x: 0, y: -1, z: 0 }, v: [{ x: x0, y: y0, z: z0 }, { x: x1, y: y0, z: z0 }, { x: x1, y: y0, z: z1 }, { x: x0, y: y0, z: z1 }] }
    ];
    return faces;
  }

  // Octahedron (8 triangles) centered at origin with radius r.
  function makeOctahedron(r) {
    const t = { x: 0, y: r, z: 0 }, b = { x: 0, y: -r, z: 0 };
    const a = { x: r, y: 0, z: 0 }, d = { x: -r, y: 0, z: 0 };
    const l = { x: 0, y: 0, z: r }, k = { x: 0, y: 0, z: -r };
    return [
      [t, l, a], [t, d, l], [t, k, d], [t, a, k],
      [b, a, l], [b, l, d], [b, d, k], [b, k, a]
    ];
  }

  // ---------- shading ----------
  function shade(base, normal, light, ambient) {
    let d = V3.dot(normal, light);
    if (d < 0) d = 0;
    const k = ambient + (1 - ambient) * d;
    return {
      r: Math.min(255, base.r * k) | 0,
      g: Math.min(255, base.g * k) | 0,
      b: Math.min(255, base.b * k) | 0
    };
  }

  // ---------- renderer ----------
  function Renderer() {
    this.width = 300;
    this.height = 150;
    this.fov = Math.PI / 3;
    this.near = 0.1;
    this.light = V3.normalize({ x: -0.4, y: 0.9, z: 0.5 });
    this.ambient = 0.35;
    this.polys = 0;
  }

  Renderer.prototype.resize = function (w, h) {
    this.width = w;
    this.height = h;
  };

  Renderer.prototype.begin = function (cam) {
    this.cam = cam;
    this.polys = 0;
  };

  // Draw a filled quad (4 world-space vertices) with flat shading + neon edge.
  Renderer.prototype.drawQuad = function (verts, normal, base, edge) {
    const cam = this.cam;
    // Back-face culling: skip faces whose normal points away from the camera.
    const c0 = toCamera(cam, verts[0]);
    const nCam = {
      x: V3.dot(normal, cam.s),
      y: V3.dot(normal, cam.u),
      z: V3.dot(normal, cam.f)
    };
    if (nCam.z < 0) return; // facing away
    const pts = [];
    for (let i = 0; i < verts.length; i++) {
      const p = project(cam, verts[i], this.width, this.height, this.fov, this.near);
      if (!p) return;
      pts.push(p);
    }
    const col = shade(base, normal, this.light, this.ambient);
    const ctx = this.ctx;
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
    ctx.closePath();
    ctx.fillStyle = 'rgb(' + col.r + ',' + col.g + ',' + col.b + ')';
    ctx.fill();
    ctx.strokeStyle = edge;
    ctx.lineWidth = 1.5;
    ctx.stroke();
    this.polys++;
  };

  // Draw a filled triangle (3 world-space vertices).
  Renderer.prototype.drawTri = function (a, b, c, base, edge) {
    const cam = this.cam;
    const n = V3.normalize(V3.cross(V3.sub(b, a), V3.sub(c, a)));
    const c0 = toCamera(cam, a);
    const nCam = {
      x: V3.dot(n, cam.s),
      y: V3.dot(n, cam.u),
      z: V3.dot(n, cam.f)
    };
    if (nCam.z < 0) return;
    const pa = project(cam, a, this.width, this.height, this.fov, this.near);
    const pb = project(cam, b, this.width, this.height, this.fov, this.near);
    const pc = project(cam, c, this.width, this.height, this.fov, this.near);
    if (!pa || !pb || !pc) return;
    const col = shade(base, n, this.light, this.ambient);
    const ctx = this.ctx;
    ctx.beginPath();
    ctx.moveTo(pa.x, pa.y);
    ctx.lineTo(pb.x, pb.y);
    ctx.lineTo(pc.x, pc.y);
    ctx.closePath();
    ctx.fillStyle = 'rgb(' + col.r + ',' + col.g + ',' + col.b + ')';
    ctx.fill();
    ctx.strokeStyle = edge;
    ctx.lineWidth = 1;
    ctx.stroke();
    this.polys++;
  };

  // Painter's algorithm: collect items with a depth, sort far->near, draw.
  Renderer.prototype.drawSorted = function (items) {
    const cam = this.cam;
    const withDepth = [];
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      let cx = 0, cy = 0, cz = 0;
      for (let j = 0; j < it.verts.length; j++) {
        cx += it.verts[j].x; cy += it.verts[j].y; cz += it.verts[j].z;
      }
      const n = it.verts.length;
      const c = toCamera(cam, { x: cx / n, y: cy / n, z: cz / n });
      withDepth.push({ it: it, z: c.z });
    }
    withDepth.sort(function (a, b) { return b.z - a.z; });
    for (let i = 0; i < withDepth.length; i++) {
      const it = withDepth[i].it;
      if (it.kind === 'quad') this.drawQuad(it.verts, it.normal, it.base, it.edge);
      else this.drawTri(it.verts[0], it.verts[1], it.verts[2], it.base, it.edge);
    }
  };

  // Project a polyline (array of world points) to screen points.
  Renderer.prototype.projectPolyline = function (worldPts) {
    const out = [];
    for (let i = 0; i < worldPts.length; i++) {
      const p = project(this.cam, worldPts[i], this.width, this.height, this.fov, this.near);
      if (!p) return null;
      out.push(p);
    }
    return out;
  };

  global.Engine3D = {
    V3: V3,
    lookAt: lookAt,
    toCamera: toCamera,
    project: project,
    makeBox: makeBox,
    makeOctahedron: makeOctahedron,
    Renderer: Renderer
  };
})(window);
