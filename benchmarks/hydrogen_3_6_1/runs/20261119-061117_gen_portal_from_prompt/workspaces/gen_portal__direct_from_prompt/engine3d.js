/**
 * engine3d.js - Lightweight software 3D math, geometry, and canvas renderer.
 */
(function (global) {
  'use strict';

  const Vec3 = {
    create(x = 0, y = 0, z = 0) {
      return { x, y, z };
    },
    add(a, b) {
      return { x: a.x + b.x, y: a.y + b.y, z: a.z + b.z };
    },
    sub(a, b) {
      return { x: a.x - b.x, y: a.y - b.y, z: a.z - b.z };
    },
    scale(v, s) {
      return { x: v.x * s, y: v.y * s, z: v.z * s };
    },
    dot(a, b) {
      return a.x * b.x + a.y * b.y + a.z * b.z;
    },
    cross(a, b) {
      return {
        x: a.y * b.z - a.z * b.y,
        y: a.z * b.x - a.x * b.z,
        z: a.x * b.y - a.y * b.x,
      };
    },
    length(v) {
      return Math.hypot(v.x, v.y, v.z);
    },
    normalize(v) {
      const len = Math.hypot(v.x, v.y, v.z) || 1;
      return { x: v.x / len, y: v.y / len, z: v.z / len };
    },
    rotateX(v, a) {
      const c = Math.cos(a), s = Math.sin(a);
      return { x: v.x, y: v.y * c - v.z * s, z: v.y * s + v.z * c };
    },
    rotateY(v, a) {
      const c = Math.cos(a), s = Math.sin(a);
      return { x: v.x * c + v.z * s, y: v.y, z: -v.x * s + v.z * c };
    },
    rotateZ(v, a) {
      const c = Math.cos(a), s = Math.sin(a);
      return { x: v.x * c - v.y * s, y: v.x * s + v.y * c, z: v.z };
    },
  };

  /**
   * Orbiting perspective camera.
   */
  class Camera {
    constructor(opts = {}) {
      this.yaw = opts.yaw ?? 0.45;
      this.pitch = opts.pitch ?? 0.26;
      this.distance = opts.distance ?? 15.5;
      this.target = opts.target ?? { x: 0, y: 1.9, z: 0 };
      this.fov = opts.fov ?? 680;
      this.near = opts.near ?? 0.35;
      this.eye = { x: 0, y: 0, z: 0 };
      this.forward = { x: 0, y: 0, z: 1 };
      this.right = { x: 1, y: 0, z: 0 };
      this.up = { x: 0, y: 1, z: 0 };
      this.updateBasis();
    }

    updateBasis() {
      const cp = Math.cos(this.pitch);
      const sp = Math.sin(this.pitch);
      const cy = Math.cos(this.yaw);
      const sy = Math.sin(this.yaw);

      this.eye = {
        x: this.target.x + this.distance * cp * sy,
        y: this.target.y + this.distance * sp,
        z: this.target.z + this.distance * cp * cy,
      };

      this.forward = Vec3.normalize(Vec3.sub(this.target, this.eye));
      const worldUp = { x: 0, y: 1, z: 0 };
      this.right = Vec3.normalize(Vec3.cross(this.forward, worldUp));
      this.up = Vec3.cross(this.right, this.forward);
    }

    worldToView(p) {
      const d = Vec3.sub(p, this.eye);
      return {
        x: Vec3.dot(d, this.right),
        y: Vec3.dot(d, this.up),
        z: Vec3.dot(d, this.forward),
      };
    }

    projectView(v, cx, cy, scale) {
      if (v.z <= this.near) return null;
      const f = (this.fov * scale) / v.z;
      return {
        x: cx + v.x * f,
        y: cy - v.y * f,
        z: v.z,
        scale: f,
      };
    }

    projectWorld(p, cx, cy, scale) {
      return this.projectView(this.worldToView(p), cx, cy, scale);
    }
  }

  /**
   * Build a 6-face axis-aligned box centered at (cx, cy, cz).
   * Winding is CCW when viewed from outside.
   */
  function createBox(w, h, d, cx, cy, cz, style) {
    const hw = w * 0.5, hh = h * 0.5, hd = d * 0.5;
    const verts = [
      { x: cx - hw, y: cy - hh, z: cz + hd }, // 0: front-bottom-left
      { x: cx + hw, y: cy - hh, z: cz + hd }, // 1: front-bottom-right
      { x: cx + hw, y: cy + hh, z: cz + hd }, // 2: front-top-right
      { x: cx - hw, y: cy + hh, z: cz + hd }, // 3: front-top-left
      { x: cx - hw, y: cy - hh, z: cz - hd }, // 4: back-bottom-left
      { x: cx + hw, y: cy - hh, z: cz - hd }, // 5: back-bottom-right
      { x: cx + hw, y: cy + hh, z: cz - hd }, // 6: back-top-right
      { x: cx - hw, y: cy + hh, z: cz - hd }, // 7: back-top-left
    ];

    const indices = [
      [0, 1, 2, 3], // front (+Z)
      [5, 4, 7, 6], // back (-Z)
      [4, 0, 3, 7], // left (-X)
      [1, 5, 6, 2], // right (+X)
      [3, 2, 6, 7], // top (+Y)
      [4, 5, 1, 0], // bottom (-Y)
    ];

    return indices.map((idx) => ({
      pts: idx.map((i) => verts[i]),
      baseColor: style.fill,
      edgeColor: style.edge,
      emissive: style.emissive ?? 0.25,
      lineWidth: style.lineWidth ?? 1.25,
      glow: style.glow ?? 8,
    }));
  }

  /**
   * Build an 8-triangle octahedron in local space.
   */
  function createOctahedron(radius, heightScale = 1.35) {
    const r = radius;
    const h = radius * heightScale;
    const v = [
      { x: 0, y: h, z: 0 },   // 0: top
      { x: r, y: 0, z: 0 },   // 1: +X
      { x: 0, y: 0, z: r },   // 2: +Z
      { x: -r, y: 0, z: 0 },  // 3: -X
      { x: 0, y: 0, z: -r },  // 4: -Z
      { x: 0, y: -h, z: 0 },  // 5: bottom
    ];
    // CCW outward winding
    const tris = [
      [0, 2, 1],
      [0, 1, 4],
      [0, 4, 3],
      [0, 3, 2],
      [5, 1, 2],
      [5, 4, 1],
      [5, 3, 4],
      [5, 2, 3],
    ];
    return { verts: v, tris };
  }

  function shadeColor(rgb, intensity, emissive = 0.2) {
    const k = Math.min(1.4, emissive + intensity * 0.85);
    const r = Math.min(255, Math.round(rgb[0] * k));
    const g = Math.min(255, Math.round(rgb[1] * k));
    const b = Math.min(255, Math.round(rgb[2] * k));
    return `rgb(${r},${g},${b})`;
  }

  /**
   * Project & shade a polygon face (triangle or quad) in world space.
   * Returns a renderable item or null if culled / behind near plane.
   */
  function prepareFace(pts, camera, cx, cy, scale, lightDir, style) {
    const viewPts = new Array(pts.length);
    let zSum = 0;
    for (let i = 0; i < pts.length; i++) {
      const vp = camera.worldToView(pts[i]);
      if (vp.z <= camera.near) return null;
      viewPts[i] = vp;
      zSum += vp.z;
    }

    // View-space face normal for culling and lighting
    const e1 = Vec3.sub(viewPts[1], viewPts[0]);
    const e2 = Vec3.sub(viewPts[2], viewPts[0]);
    const vNormal = Vec3.cross(e1, e2);

    // Camera is at origin in view space looking +Z; face is visible if normal points toward camera
    if (Vec3.dot(vNormal, viewPts[0]) >= 0) return null;

    // World-space normal for directional lighting
    const we1 = Vec3.sub(pts[1], pts[0]);
    const we2 = Vec3.sub(pts[2], pts[0]);
    const wNormal = Vec3.normalize(Vec3.cross(we1, we2));
    const diff = Math.max(0, Vec3.dot(wNormal, lightDir));

    const screenPts = new Array(pts.length);
    for (let i = 0; i < pts.length; i++) {
      const f = (camera.fov * scale) / viewPts[i].z;
      screenPts[i] = {
        x: cx + viewPts[i].x * f,
        y: cy - viewPts[i].y * f,
      };
    }

    return {
      depth: zSum / pts.length,
      screenPts,
      fillStyle: shadeColor(style.baseColor, diff, style.emissive),
      edgeColor: style.edgeColor,
      lineWidth: style.lineWidth ?? 1.2,
      glow: style.glow ?? 6,
      alpha: style.alpha ?? 0.94,
    };
  }

  function drawFace(ctx, face) {
    const pts = face.screenPts;
    ctx.save();
    ctx.globalAlpha = face.alpha;
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) {
      ctx.lineTo(pts[i].x, pts[i].y);
    }
    ctx.closePath();
    ctx.fillStyle = face.fillStyle;
    ctx.fill();

    if (face.edgeColor) {
      ctx.strokeStyle = face.edgeColor;
      ctx.lineWidth = face.lineWidth;
      ctx.shadowColor = face.edgeColor;
      ctx.shadowBlur = face.glow;
      ctx.stroke();
    }
    ctx.restore();
  }

  global.Engine3D = {
    Vec3,
    Camera,
    createBox,
    createOctahedron,
    prepareFace,
    drawFace,
  };
})(window);
