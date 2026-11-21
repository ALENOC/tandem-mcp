/**
 * Lightweight software 3D rendering engine for HTML5 2D Canvas.
 */
(function (global) {
  'use strict';

  const Vec3 = {
    create(x, y, z) {
      return { x: x || 0, y: y || 0, z: z || 0 };
    },
    sub(a, b) {
      return { x: a.x - b.x, y: a.y - b.y, z: a.z - b.z };
    },
    add(a, b) {
      return { x: a.x + b.x, y: a.y + b.y, z: a.z + b.z };
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
        z: a.x * b.y - a.y * b.x
      };
    },
    length(v) {
      return Math.hypot(v.x, v.y, v.z);
    },
    normalize(v) {
      const len = Math.hypot(v.x, v.y, v.z) || 1;
      return { x: v.x / len, y: v.y / len, z: v.z / len };
    }
  };

  class Camera3D {
    constructor(opts) {
      const o = opts || {};
      this.target = o.target ? { ...o.target } : { x: 0, y: 1.8, z: 0 };
      this.yaw = o.yaw !== undefined ? o.yaw : 0.45;
      this.pitch = o.pitch !== undefined ? o.pitch : 0.24;
      this.distance = o.distance !== undefined ? o.distance : 11.5;
      this.fov = o.fov !== undefined ? o.fov : 620;
      this.near = 0.25;
      this.position = { x: 0, y: 0, z: 0 };
      this.right = { x: 1, y: 0, z: 0 };
      this.up = { x: 0, y: 1, z: 0 };
      this.forward = { x: 0, y: 0, z: 1 };
      this.updateBasis();
    }

    updateBasis() {
      const cp = Math.cos(this.pitch);
      const sp = Math.sin(this.pitch);
      const cy = Math.cos(this.yaw);
      const sy = Math.sin(this.yaw);

      this.position.x = this.target.x + this.distance * cp * sy;
      this.position.y = this.target.y + this.distance * sp;
      this.position.z = this.target.z + this.distance * cp * cy;

      this.forward = Vec3.normalize(Vec3.sub(this.target, this.position));
      const worldUp = { x: 0, y: 1, z: 0 };
      this.right = Vec3.normalize(Vec3.cross(this.forward, worldUp));
      this.up = Vec3.cross(this.right, this.forward);
    }

    worldToCamera(p) {
      const dx = p.x - this.position.x;
      const dy = p.y - this.position.y;
      const dz = p.z - this.position.z;
      return {
        x: dx * this.right.x + dy * this.right.y + dz * this.right.z,
        y: dx * this.up.x + dy * this.up.y + dz * this.up.z,
        z: dx * this.forward.x + dy * this.forward.y + dz * this.forward.z
      };
    }

    projectCameraPoint(cp, width, height) {
      if (cp.z <= this.near) return null;
      const scale = this.fov / cp.z;
      return {
        x: width * 0.5 + cp.x * scale,
        y: height * 0.5 - cp.y * scale,
        z: cp.z,
        scale
      };
    }

    projectWorldPoint(p, width, height) {
      return this.projectCameraPoint(this.worldToCamera(p), width, height);
    }
  }

  /**
   * Build a 6-face box centered at (cx, cy, cz) with dimensions (w, h, d).
   * Outward winding order (CCW when viewed from outside).
   */
  function createBoxMesh(cx, cy, cz, w, h, d, style) {
    const hw = w * 0.5;
    const hh = h * 0.5;
    const hd = d * 0.5;

    const v = [
      { x: cx - hw, y: cy - hh, z: cz + hd }, // 0: front-bottom-left
      { x: cx + hw, y: cy - hh, z: cz + hd }, // 1: front-bottom-right
      { x: cx + hw, y: cy + hh, z: cz + hd }, // 2: front-top-right
      { x: cx - hw, y: cy + hh, z: cz + hd }, // 3: front-top-left
      { x: cx - hw, y: cy - hh, z: cz - hd }, // 4: back-bottom-left
      { x: cx + hw, y: cy - hh, z: cz - hd }, // 5: back-bottom-right
      { x: cx + hw, y: cy + hh, z: cz - hd }, // 6: back-top-right
      { x: cx - hw, y: cy + hh, z: cz - hd }  // 7: back-top-left
    ];

    const faceIndices = [
      [0, 1, 2, 3], // front (+Z)
      [5, 4, 7, 6], // back (-Z)
      [4, 0, 3, 7], // left (-X)
      [1, 5, 6, 2], // right (+X)
      [3, 2, 6, 7], // top (+Y)
      [4, 5, 1, 0]  // bottom (-Y)
    ];

    return faceIndices.map((idx) => ({
      verts: idx.map((i) => v[i]),
      style: style || {}
    }));
  }

  /**
   * Build an 8-triangle octahedron in local space.
   */
  function createOctahedronFaces(radius, heightScale) {
    const r = radius || 0.35;
    const h = r * (heightScale || 1.45);
    const top = { x: 0, y: h, z: 0 };
    const bot = { x: 0, y: -h, z: 0 };
    const eq = [
      { x: r, y: 0, z: 0 },
      { x: 0, y: 0, z: r },
      { x: -r, y: 0, z: 0 },
      { x: 0, y: 0, z: -r }
    ];

    const tris = [];
    for (let i = 0; i < 4; i++) {
      const next = (i + 1) % 4;
      tris.push([top, eq[next], eq[i]]);
      tris.push([bot, eq[i], eq[next]]);
    }
    return tris;
  }

  function rotatePointY(p, angle) {
    const c = Math.cos(angle);
    const s = Math.sin(angle);
    return {
      x: p.x * c + p.z * s,
      y: p.y,
      z: -p.x * s + p.z * c
    };
  }

  function rotatePointX(p, angle) {
    const c = Math.cos(angle);
    const s = Math.sin(angle);
    return {
      x: p.x,
      y: p.y * c - p.z * s,
      z: p.y * s + p.z * c
    };
  }

  class SoftwareRenderer {
    constructor(canvas) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.width = 0;
      this.height = 0;
      this.dpr = 1;
      this.polyQueue = [];
      this.lastPolyCount = 0;
    }

    resize() {
      this.dpr = Math.min(window.devicePixelRatio || 1, 2);
      this.width = window.innerWidth;
      this.height = window.innerHeight;
      this.canvas.width = Math.floor(this.width * this.dpr);
      this.canvas.height = Math.floor(this.height * this.dpr);
      this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    }

    beginFrame() {
      this.polyQueue.length = 0;
    }

    drawSpaceBackground(portalScreenPos) {
      const ctx = this.ctx;
      const w = this.width;
      const h = this.height;
      const cx = portalScreenPos ? portalScreenPos.x : w * 0.5;
      const cy = portalScreenPos ? portalScreenPos.y : h * 0.45;
      const maxR = Math.hypot(w, h) * 0.75;

      const grad = ctx.createRadialGradient(cx, cy, 10, cx, cy, maxR);
      grad.addColorStop(0, '#130b33');
      grad.addColorStop(0.35, '#09071d');
      grad.addColorStop(0.75, '#040410');
      grad.addColorStop(1, '#010105');

      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);
    }

    submitPolygon(worldVerts, camera, options) {
      const opts = options || {};
      const n = worldVerts.length;
      if (n < 3) return;

      // Compute world-space normal & centroid for lighting + culling
      const e1 = Vec3.sub(worldVerts[1], worldVerts[0]);
      const e2 = Vec3.sub(worldVerts[2], worldVerts[0]);
      const normal = Vec3.normalize(Vec3.cross(e1, e2));

      let cx = 0, cy = 0, cz = 0;
      for (let i = 0; i < n; i++) {
        cx += worldVerts[i].x;
        cy += worldVerts[i].y;
        cz += worldVerts[i].z;
      }
      const invN = 1 / n;
      const centroid = { x: cx * invN, y: cy * invN, z: cz * invN };

      if (opts.cullBackface !== false) {
        const viewDir = Vec3.sub(camera.position, centroid);
        if (Vec3.dot(normal, viewDir) <= 0) return;
      }

      const camVerts = new Array(n);
      const screenVerts = new Array(n);
      let depthSum = 0;

      for (let i = 0; i < n; i++) {
        const cv = camera.worldToCamera(worldVerts[i]);
        if (cv.z <= camera.near) return;
        camVerts[i] = cv;
        depthSum += cv.z;
        screenVerts[i] = camera.projectCameraPoint(cv, this.width, this.height);
      }

      // Compute lighting from key light + portal core light
      const keyLight = Vec3.normalize({ x: 0.45, y: 0.82, z: 0.36 });
      const diffuse = Math.max(0, Vec3.dot(normal, keyLight));

      const portalCenter = opts.portalCenter || { x: 0, y: 2.3, z: 0 };
      const toPortal = Vec3.sub(portalCenter, centroid);
      const distSq = Vec3.dot(toPortal, toPortal) + 0.5;
      const toPortalDir = Vec3.normalize(toPortal);
      const portalLight = Math.max(0, Vec3.dot(normal, toPortalDir)) * Math.min(1.2, 4.5 / distSq);

      const base = opts.baseColor || [26, 36, 68];
      const portalGlow = opts.portalGlowColor || [45, 220, 255];
      const ambient = opts.ambient !== undefined ? opts.ambient : 0.28;
      const shade = Math.min(1.15, ambient + diffuse * 0.65);

      const r = Math.min(255, Math.round(base[0] * shade + portalGlow[0] * portalLight * 0.55));
      const g = Math.min(255, Math.round(base[1] * shade + portalGlow[1] * portalLight * 0.55));
      const b = Math.min(255, Math.round(base[2] * shade + portalGlow[2] * portalLight * 0.55));

      this.polyQueue.push({
        screenVerts,
        depth: depthSum * invN,
        fill: `rgba(${r}, ${g}, ${b}, ${opts.alpha !== undefined ? opts.alpha : 0.96})`,
        stroke: opts.stroke || 'rgba(90, 225, 255, 0.38)',
        lineWidth: opts.lineWidth !== undefined ? opts.lineWidth : 1
      });
    }

    flushPolygons() {
      const ctx = this.ctx;
      const queue = this.polyQueue;
      queue.sort((a, b) => b.depth - a.depth);
      this.lastPolyCount = queue.length;

      for (let i = 0; i < queue.length; i++) {
        const poly = queue[i];
        const pts = poly.screenVerts;
        ctx.beginPath();
        ctx.moveTo(pts[0].x, pts[0].y);
        for (let j = 1; j < pts.length; j++) {
          ctx.lineTo(pts[j].x, pts[j].y);
        }
        ctx.closePath();
        ctx.fillStyle = poly.fill;
        ctx.fill();
        if (poly.stroke) {
          ctx.strokeStyle = poly.stroke;
          ctx.lineWidth = poly.lineWidth;
          ctx.stroke();
        }
      }
    }

    drawLine3D(a, b, camera, color, lineWidth) {
      const ca = camera.worldToCamera(a);
      const cb = camera.worldToCamera(b);
      if (ca.z <= camera.near && cb.z <= camera.near) return;

      // Clip segment to near plane if one endpoint is behind camera
      let p1 = ca;
      let p2 = cb;
      if (p1.z <= camera.near) {
        const t = (camera.near - p1.z) / (p2.z - p1.z);
        p1 = {
          x: p1.x + (p2.x - p1.x) * t,
          y: p1.y + (p2.y - p1.y) * t,
          z: camera.near + 0.001
        };
      } else if (p2.z <= camera.near) {
        const t = (camera.near - p2.z) / (p1.z - p2.z);
        p2 = {
          x: p2.x + (p1.x - p2.x) * t,
          y: p2.y + (p1.y - p2.y) * t,
          z: camera.near + 0.001
        };
      }

      const sa = camera.projectCameraPoint(p1, this.width, this.height);
      const sb = camera.projectCameraPoint(p2, this.width, this.height);
      if (!sa || !sb) return;

      const ctx = this.ctx;
      ctx.beginPath();
      ctx.moveTo(sa.x, sa.y);
      ctx.lineTo(sb.x, sb.y);
      ctx.strokeStyle = color;
      ctx.lineWidth = lineWidth || 1;
      ctx.stroke();
    }
  }

  global.Engine3D = {
    Vec3,
    Camera3D,
    SoftwareRenderer,
    createBoxMesh,
    createOctahedronFaces,
    rotatePointX,
    rotatePointY
  };
})(window);
