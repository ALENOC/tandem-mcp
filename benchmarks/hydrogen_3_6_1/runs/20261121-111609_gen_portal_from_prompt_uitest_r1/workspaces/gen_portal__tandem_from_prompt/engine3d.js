// engine3d.js - self-contained software 3D renderer
// Perspective projection, rotation matrices, painter's algorithm z-sort,
// back-face culling and diffuse + rim shading. No external dependencies.

(function (global) {
  "use strict";

  // ---- vector / matrix helpers -------------------------------------------
  function rotY(p, a) {
    const c = Math.cos(a), s = Math.sin(a);
    return [p[0] * c + p[2] * s, p[1], -p[0] * s + p[2] * c];
  }
  function rotX(p, a) {
    const c = Math.cos(a), s = Math.sin(a);
    return [p[0], p[1] * c - p[2] * s, p[1] * s + p[2] * c];
  }
  function rotZ(p, a) {
    const c = Math.cos(a), s = Math.sin(a);
    return [p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2]];
  }
  function sub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
  function cross(a, b) {
    return [
      a[1] * b[2] - a[2] * b[1],
      a[2] * b[0] - a[0] * b[2],
      a[0] * b[1] - a[1] * b[0]
    ];
  }
  function norm(a) {
    const l = Math.hypot(a[0], a[1], a[2]) || 1;
    return [a[0] / l, a[1] / l, a[2] / l];
  }
  function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }

  // A polygon: { verts: [[x,y,z],...], color:[r,g,b], rim:[r,g,b], glow:0..1,
  //              noCull:bool, depthBias:0..1 }
  // The renderer transforms verts by the camera, projects, culls, shades,
  // z-sorts and fills.

  class Renderer {
    constructor(canvas) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.w = 0;
      this.h = 0;
      this.focal = 700;
      this.camPos = [0, 6, 16];
      this.camTarget = [0, 3, 0];
      this.light = norm([-0.4, 0.9, 0.6]);
      this.polys = 0;
      this._resize();
    }

    _resize() {
      const dpr = Math.min(global.devicePixelRatio || 1, 2);
      this.w = this.canvas.clientWidth || global.innerWidth;
      this.h = this.canvas.clientHeight || global.innerHeight;
      this.canvas.width = Math.floor(this.w * dpr);
      this.canvas.height = Math.floor(this.h * dpr);
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      this.focal = Math.min(this.w, this.h) * 1.15;
    }

    // Build the camera basis (look-at) and return { proj, projLine }.
    _camera() {
      const eye = this.camPos;
      const fwd = norm(sub(this.camTarget, eye));
      const right = norm(cross(fwd, [0, 1, 0]));
      const up = cross(right, fwd);
      const focal = this.focal;
      const cx = this.w / 2, cy = this.h / 2;
      const near = 0.1;

      function toCam(p) {
        const d = sub(p, eye);
        return [dot(d, right), dot(d, up), dot(d, fwd)];
      }
      function toScreen(c) {
        const s = focal / c[2];
        return [cx + c[0] * s, cy - c[1] * s, c[2]];
      }

      const proj = (p) => {
        const c = toCam(p);
        if (c[2] <= near) return null;
        return toScreen(c);
      };

      const projLine = (p0, p1) => {
        let a = toCam(p0);
        let b = toCam(p1);
        if (a[2] <= near && b[2] <= near) return null;
        if (a[2] < near) {
          const t = (near - a[2]) / (b[2] - a[2]);
          a = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, near];
        } else if (b[2] < near) {
          const t = (near - b[2]) / (a[2] - b[2]);
          b = [b[0] + (a[0] - b[0]) * t, b[1] + (a[1] - b[1]) * t, near];
        }
        return [toScreen(a), toScreen(b)];
      };

      return { proj, projLine };
    }

    // Draw a list of polygons. Each poly: { verts, color, rim, glow, noCull, depthBias }
    // verts length 1 => glowing point, 2 => neon line, >=3 => shaded polygon.
    draw(polys) {
      this.ctx.clearRect(0, 0, this.w, this.h);
      const { proj, projLine } = this._camera();
      const light = this.light;
      const items = [];
      let count = 0;

      for (let i = 0; i < polys.length; i++) {
        const poly = polys[i];
        const v = poly.verts;

        // glowing point (star / particle)
        if (v.length === 1) {
          const p = proj(v[0]);
          if (!p) continue;
          items.push({ type: "point", p: p, depth: p[2], color: poly.color, glow: poly.glow || 0, sz: poly.sz || 2 });
          continue;
        }

        // neon line (grid)
        if (v.length === 2) {
          const seg = projLine(v[0], v[1]);
          if (!seg) continue;
          const a = seg[0], b = seg[1];
          items.push({ type: "line", a: a, b: b, depth: (a[2] + b[2]) / 2, rim: poly.rim || poly.color, glow: poly.glow || 0, lw: poly.lw || 1.5 });
          continue;
        }

        if (v.length < 3) continue;

        // project all verts
        const pv = new Array(v.length);
        let ok = true;
        let depth = 0;
        for (let k = 0; k < v.length; k++) {
          const p = proj(v[k]);
          if (!p) { ok = false; break; }
          pv[k] = p;
          depth += p[2];
        }
        if (!ok) continue;
        depth /= v.length;

        // back-face culling using screen-space winding
        let cull = false;
        if (!poly.noCull) {
          const a = pv[0], b = pv[1], c = pv[2];
          const area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
          if (area >= 0) cull = true; // clockwise on screen = back-facing
        }
        if (cull) continue;

        // normal for shading (world space)
        const n = norm(cross(sub(v[1], v[0]), sub(v[2], v[0])));
        let diff = Math.max(0, dot(n, light));
        // rim: how much the normal faces away from the camera view dir
        const viewDir = norm(sub(this.camPos, v[0]));
        const rim = Math.pow(1 - Math.max(0, dot(n, viewDir)), 2);

        const base = poly.color;
        const rimC = poly.rim || base;
        const glow = poly.glow || 0;
        const shade = 0.35 + 0.65 * diff;
        const r = Math.min(255, base[0] * shade + rimC[0] * rim * 0.9 + glow * 60);
        const g = Math.min(255, base[1] * shade + rimC[1] * rim * 0.9 + glow * 60);
        const b2 = Math.min(255, base[2] * shade + rimC[2] * rim * 0.9 + glow * 60);

        items.push({ type: "poly", pv: pv, depth: depth + (poly.depthBias || 0), r, g, b: b2, glow, rimC, rim });
        count++;
      }

      // painter's algorithm: far to near
      items.sort((a, b) => b.depth - a.depth);

      const ctx = this.ctx;
      for (let i = 0; i < items.length; i++) {
        const it = items[i];

        if (it.type === "point") {
          const rad = it.sz * (0.6 + it.glow * 0.8);
          const grd = ctx.createRadialGradient(it.p[0], it.p[1], 0, it.p[0], it.p[1], rad * 3);
          const c = it.color;
          grd.addColorStop(0, "rgba(255,255,255," + (0.5 + it.glow * 0.5) + ")");
          grd.addColorStop(0.4, "rgba(" + (c[0] | 0) + "," + (c[1] | 0) + "," + (c[2] | 0) + "," + (0.3 + it.glow * 0.4) + ")");
          grd.addColorStop(1, "rgba(" + (c[0] | 0) + "," + (c[1] | 0) + "," + (c[2] | 0) + ",0)");
          ctx.fillStyle = grd;
          ctx.beginPath();
          ctx.arc(it.p[0], it.p[1], rad * 3, 0, Math.PI * 2);
          ctx.fill();
          continue;
        }

        if (it.type === "line") {
          const c = it.rim;
          ctx.lineWidth = it.lw;
          ctx.strokeStyle = "rgba(" + (c[0] | 0) + "," + (c[1] | 0) + "," + (c[2] | 0) + "," + (0.15 + it.glow * 0.5) + ")";
          ctx.beginPath();
          ctx.moveTo(it.a[0], it.a[1]);
          ctx.lineTo(it.b[0], it.b[1]);
          ctx.stroke();
          continue;
        }

        const pv = it.pv;
        ctx.beginPath();
        ctx.moveTo(pv[0][0], pv[0][1]);
        for (let k = 1; k < pv.length; k++) ctx.lineTo(pv[k][0], pv[k][1]);
        ctx.closePath();
        ctx.fillStyle = "rgb(" + (it.r | 0) + "," + (it.g | 0) + "," + (it.b | 0) + ")";
        ctx.fill();
        // neon edge
        ctx.lineWidth = 1.2;
        ctx.strokeStyle = "rgba(" + (it.rimC[0] | 0) + "," + (it.rimC[1] | 0) + "," + (it.rimC[2] | 0) + "," + (0.5 + it.rim * 0.5) + ")";
        ctx.stroke();
      }
      this.polys = count;
    }
  }

  // Convenience geometry builders (world-space, untransformed).

  // Axis-aligned box centered at c with half-extents (hx,hy,hz).
  // Returns 6 quads (36 box faces total across the monument).
  function boxFaces(c, hx, hy, hz) {
    const x0 = c[0] - hx, x1 = c[0] + hx;
    const y0 = c[1] - hy, y1 = c[1] + hy;
    const z0 = c[2] - hz, z1 = c[2] + hz;
    // each face listed counter-clockwise when viewed from outside
    return [
      [[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], // +z front
      [[x1, y0, z0], [x0, y0, z0], [x0, y1, z0], [x1, y1, z0]], // -z back
      [[x1, y0, z1], [x1, y0, z0], [x1, y1, z0], [x1, y1, z1]], // +x right
      [[x0, y0, z0], [x0, y0, z1], [x0, y1, z1], [x0, y1, z0]], // -x left
      [[x0, y1, z1], [x1, y1, z1], [x1, y1, z0], [x0, y1, z0]], // +y top
      [[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1]]  // -y bottom
    ];
  }

  // Octahedron centered at c with radius r. 8 triangles.
  function octaFaces(c, r) {
    const t = [c[0], c[1] + r, c[2]];
    const b = [c[0], c[1] - r, c[2]];
    const p1 = [c[0] + r, c[1], c[2]];
    const p2 = [c[0], c[1], c[2] + r];
    const p3 = [c[0] - r, c[1], c[2]];
    const p4 = [c[0], c[1], c[2] - r];
    return [
      [t, p2, p1], [t, p3, p2], [t, p4, p3], [t, p1, p4],
      [b, p1, p2], [b, p2, p3], [b, p3, p4], [b, p4, p1]
    ];
  }

  // A ring of quads forming a flat annulus in the XZ plane at height y.
  function ringFaces(c, rIn, rOut, segs) {
    const faces = [];
    for (let i = 0; i < segs; i++) {
      const a0 = (i / segs) * Math.PI * 2;
      const a1 = ((i + 1) / segs) * Math.PI * 2;
      const c0 = Math.cos(a0), s0 = Math.sin(a0);
      const c1 = Math.cos(a1), s1 = Math.sin(a1);
      const o0 = [c[0] + c0 * rOut, c[1], c[2] + s0 * rOut];
      const o1 = [c[0] + c1 * rOut, c[1], c[2] + s1 * rOut];
      const i1 = [c[0] + c1 * rIn, c[1], c[2] + s1 * rIn];
      const i0 = [c[0] + c0 * rIn, c[1], c[2] + s0 * rIn];
      faces.push([o0, o1, i1, i0]);
    }
    return faces;
  }

  global.Engine3D = {
    Renderer, boxFaces, octaFaces, ringFaces,
    rotX, rotY, rotZ, sub, cross, norm, dot
  };
})(typeof window !== "undefined" ? window : globalThis);
