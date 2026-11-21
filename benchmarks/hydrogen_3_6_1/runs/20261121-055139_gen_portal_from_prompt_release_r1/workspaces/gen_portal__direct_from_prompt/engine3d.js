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
        z: a.x * b.y - a.y * b.x
      };
    },
    normalize(v) {
      const len = Math.hypot(v.x, v.y, v.z) || 1;
      return { x: v.x / len, y: v.y / len, z: v.z / len };
    },
    rotateY(v, angle) {
      const c = Math.cos(angle);
      const s = Math.sin(angle);
      return {
        x: v.x * c + v.z * s,
        y: v.y,
        z: -v.x * s + v.z * c
      };
    },
    rotateX(v, angle) {
      const c = Math.cos(angle);
      const s = Math.sin(angle);
      return {
        x: v.x,
        y: v.y * c - v.z * s,
        z: v.y * s + v.z * c
      };
    },
    rotateZ(v, angle) {
      const c = Math.cos(angle);
      const s = Math.sin(angle);
      return {
        x: v.x * c - v.y * s,
        y: v.x * s + v.y * c,
        z: v.z
      };
    }
  };

  class Camera3D {
    constructor() {
      this.reset();
    }

    reset() {
      this.yaw = 0.45;
      this.pitch = 0.28;
      this.distance = 8.8;
      this.target = { x: 0, y: 0.25, z: 0 };
      this.fov = 620;
    }

    getPosition() {
      const cp = Math.cos(this.pitch);
      return {
        x: this.target.x + this.distance * cp * Math.sin(this.yaw),
        y: this.target.y + this.distance * Math.sin(this.pitch),
        z: this.target.z + this.distance * cp * Math.cos(this.yaw)
      };
    }

    project(worldPt, width, height) {
      const dx = worldPt.x - this.target.x;
      const dy = worldPt.y - this.target.y;
      const dz = worldPt.z - this.target.z;

      // Rotate world into camera view space
      const cy = Math.cos(-this.yaw);
      const sy = Math.sin(-this.yaw);
      const rx = dx * cy + dz * sy;
      const rz0 = -dx * sy + dz * cy;

      const cp = Math.cos(-this.pitch);
      const sp = Math.sin(-this.pitch);
      const ry = dy * cp - rz0 * sp;
      const rz = dy * sp + rz0 * cp;

      const camZ = this.distance - rz;
      if (camZ <= 0.25) return null;

      const scale = this.fov / camZ;
      return {
        x: width * 0.5 + rx * scale,
        y: height * 0.5 - ry * scale,
        z: camZ,
        scale
      };
    }
  }

  function makeBoxFaces(cx, cy, cz, w, h, d, baseColor, edgeColor) {
    const hw = w * 0.5;
    const hh = h * 0.5;
    const hd = d * 0.5;

    const v = [
      { x: cx - hw, y: cy - hh, z: cz - hd }, // 0: L B Back
      { x: cx + hw, y: cy - hh, z: cz - hd }, // 1: R B Back
      { x: cx + hw, y: cy + hh, z: cz - hd }, // 2: R T Back
      { x: cx - hw, y: cy + hh, z: cz - hd }, // 3: L T Back
      { x: cx - hw, y: cy - hh, z: cz + hd }, // 4: L B Front
      { x: cx + hw, y: cy - hh, z: cz + hd }, // 5: R B Front
      { x: cx + hw, y: cy + hh, z: cz + hd }, // 6: R T Front
      { x: cx - hw, y: cy + hh, z: cz + hd }  // 7: L T Front
    ];

    // Outward-facing CCW vertex order
    const indices = [
      [4, 5, 6, 7], // front
      [1, 0, 3, 2], // back
      [0, 4, 7, 3], // left
      [5, 1, 2, 6], // right
      [7, 6, 2, 3], // top
      [0, 1, 5, 4]  // bottom
    ];

    return indices.map((quad) => ({
      verts: quad.map((idx) => v[idx]),
      color: baseColor,
      edgeColor
    }));
  }

  function makeOctahedronFaces(cx, cy, cz, rx, ry, rz, rotY, rotX, baseColor, edgeColor) {
    const raw = [
      { x: 0, y: ry, z: 0 },   // 0: top
      { x: 0, y: -ry, z: 0 },  // 1: bottom
      { x: rx, y: 0, z: 0 },   // 2: +X
      { x: 0, y: 0, z: rz },   // 3: +Z
      { x: -rx, y: 0, z: 0 },  // 4: -X
      { x: 0, y: 0, z: -rz }   // 5: -Z
    ];

    const transformed = raw.map((pt) => {
      let p = Vec3.rotateX(pt, rotX);
      p = Vec3.rotateY(p, rotY);
      return { x: p.x + cx, y: p.y + cy, z: p.z + cz };
    });

    // Outward-facing CCW triangles
    const tris = [
      [0, 3, 2],
      [0, 2, 5],
      [0, 5, 4],
      [0, 4, 3],
      [1, 2, 3],
      [1, 5, 2],
      [1, 4, 5],
      [1, 3, 4]
    ];

    return tris.map((tri) => ({
      verts: tri.map((idx) => transformed[idx]),
      color: baseColor,
      edgeColor
    }));
  }

  function shadeRgb(rgb, intensity) {
    const r = Math.min(255, Math.max(0, Math.round(rgb[0] * intensity)));
    const g = Math.min(255, Math.max(0, Math.round(rgb[1] * intensity)));
    const b = Math.min(255, Math.max(0, Math.round(rgb[2] * intensity)));
    return `rgb(${r}, ${g}, ${b})`;
  }

  class Renderer3D {
    constructor(canvas) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.lightDir = Vec3.normalize({ x: 0.45, y: 0.82, z: 0.55 });
      this.queue = [];
    }

    beginFrame(width, height) {
      this.width = width;
      this.height = height;
      this.queue.length = 0;
      this.ctx.clearRect(0, 0, width, height);
    }

    pushPolygon(camera, face, cullBackface = true) {
      const verts = face.verts;
      const e1 = Vec3.sub(verts[1], verts[0]);
      const e2 = Vec3.sub(verts[2], verts[0]);
      const normal = Vec3.normalize(Vec3.cross(e1, e2));

      // Compute centroid
      let cx = 0;
      let cy = 0;
      let cz = 0;
      for (let i = 0; i < verts.length; i++) {
        cx += verts[i].x;
        cy += verts[i].y;
        cz += verts[i].z;
      }
      const inv = 1 / verts.length;
      cx *= inv;
      cy *= inv;
      cz *= inv;

      if (cullBackface) {
        const camPos = camera.getPosition();
        const toCam = { x: camPos.x - cx, y: camPos.y - cy, z: camPos.z - cz };
        if (Vec3.dot(normal, toCam) <= 0) return;
      }

      const projected = [];
      let zSum = 0;
      for (let i = 0; i < verts.length; i++) {
        const p = camera.project(verts[i], this.width, this.height);
        if (!p) return;
        projected.push(p);
        zSum += p.z;
      }

      const diffuse = Math.max(0, Vec3.dot(normal, this.lightDir));
      const intensity = 0.28 + diffuse * 0.78;
      const fill = shadeRgb(face.color, intensity);

      this.queue.push({
        kind: 'poly',
        depth: zSum * inv,
        pts: projected,
        fill,
        stroke: face.edgeColor || null,
        lineWidth: face.lineWidth || 1.1
      });
    }

    pushLine(camera, a, b, stroke, lineWidth = 1, alpha = 1) {
      const pa = camera.project(a, this.width, this.height);
      const pb = camera.project(b, this.width, this.height);
      if (!pa || !pb) return;

      this.queue.push({
        kind: 'line',
        depth: (pa.z + pb.z) * 0.5,
        pa,
        pb,
        stroke,
        lineWidth,
        alpha
      });
    }

    pushPoint(camera, pos, radius, color, alpha = 1, glow = false) {
      const p = camera.project(pos, this.width, this.height);
      if (!p) return;
      const r = Math.max(0.7, radius * (p.scale / 85));
      this.queue.push({
        kind: 'point',
        depth: p.z,
        x: p.x,
        y: p.y,
        r,
        color,
        alpha,
        glow
      });
    }

    pushCustom(depth, drawFn) {
      this.queue.push({
        kind: 'custom',
        depth,
        drawFn
      });
    }

    flush() {
      const q = this.queue;
      q.sort((a, b) => b.depth - a.depth);
      const ctx = this.ctx;

      for (let i = 0; i < q.length; i++) {
        const item = q[i];
        if (item.kind === 'poly') {
          const pts = item.pts;
          ctx.beginPath();
          ctx.moveTo(pts[0].x, pts[0].y);
          for (let j = 1; j < pts.length; j++) {
            ctx.lineTo(pts[j].x, pts[j].y);
          }
          ctx.closePath();
          ctx.fillStyle = item.fill;
          ctx.fill();
          if (item.stroke) {
            ctx.strokeStyle = item.stroke;
            ctx.lineWidth = item.lineWidth;
            ctx.stroke();
          }
        } else if (item.kind === 'line') {
          ctx.save();
          ctx.globalAlpha = item.alpha;
          ctx.strokeStyle = item.stroke;
          ctx.lineWidth = item.lineWidth;
          ctx.beginPath();
          ctx.moveTo(item.pa.x, item.pa.y);
          ctx.lineTo(item.pb.x, item.pb.y);
          ctx.stroke();
          ctx.restore();
        } else if (item.kind === 'point') {
          ctx.save();
          ctx.globalAlpha = item.alpha;
          if (item.glow) {
            ctx.shadowColor = item.color;
            ctx.shadowBlur = item.r * 3;
          }
          ctx.fillStyle = item.color;
          ctx.beginPath();
          ctx.arc(item.x, item.y, item.r, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
        } else if (item.kind === 'custom') {
          item.drawFn(ctx);
        }
      }
    }
  }

  global.Engine3D = {
    Vec3,
    Camera3D,
    Renderer3D,
    makeBoxFaces,
    makeOctahedronFaces
  };
})(window);
