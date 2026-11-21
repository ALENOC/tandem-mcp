(function (global) {
  "use strict";

  function vec3(x, y, z) {
    return { x: x || 0, y: y || 0, z: z || 0 };
  }

  function add(a, b) {
    return { x: a.x + b.x, y: a.y + b.y, z: a.z + b.z };
  }

  function sub(a, b) {
    return { x: a.x - b.x, y: a.y - b.y, z: a.z - b.z };
  }

  function scale(v, s) {
    return { x: v.x * s, y: v.y * s, z: v.z * s };
  }

  function dot(a, b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
  }

  function cross(a, b) {
    return {
      x: a.y * b.z - a.z * b.y,
      y: a.z * b.x - a.x * b.z,
      z: a.x * b.y - a.y * b.x,
    };
  }

  function normalize(v) {
    const len = Math.hypot(v.x, v.y, v.z) || 1;
    return { x: v.x / len, y: v.y / len, z: v.z / len };
  }

  function rotateX(v, a) {
    const c = Math.cos(a);
    const s = Math.sin(a);
    return { x: v.x, y: v.y * c - v.z * s, z: v.y * s + v.z * c };
  }

  function rotateY(v, a) {
    const c = Math.cos(a);
    const s = Math.sin(a);
    return { x: v.x * c + v.z * s, y: v.y, z: -v.x * s + v.z * c };
  }

  function rotateZ(v, a) {
    const c = Math.cos(a);
    const s = Math.sin(a);
    return { x: v.x * c - v.y * s, y: v.x * s + v.y * c, z: v.z };
  }

  function clamp(val, min, max) {
    return val < min ? min : val > max ? max : val;
  }

  function createCamera(yaw, pitch, distance, target) {
    const cosP = Math.cos(pitch);
    const pos = {
      x: target.x + Math.sin(yaw) * cosP * distance,
      y: target.y + Math.sin(pitch) * distance,
      z: target.z + Math.cos(yaw) * cosP * distance,
    };
    const forward = normalize(sub(target, pos));
    const worldUp = { x: 0, y: 1, z: 0 };
    const right = normalize(cross(forward, worldUp));
    const up = cross(right, forward);
    return { pos, forward, right, up, fov: 640, near: 0.25 };
  }

  function worldToCamera(p, cam) {
    const rel = sub(p, cam.pos);
    return {
      x: dot(rel, cam.right),
      y: dot(rel, cam.up),
      z: dot(rel, cam.forward),
    };
  }

  function projectPoint(camPt, cam, cx, cy) {
    if (camPt.z <= cam.near) return null;
    const invZ = cam.fov / camPt.z;
    return {
      x: cx + camPt.x * invZ,
      y: cy - camPt.y * invZ,
      z: camPt.z,
      scale: invZ,
    };
  }

  function createBoxFaces(cx, cy, cz, w, h, d, options) {
    const hx = w * 0.5;
    const hy = h * 0.5;
    const hz = d * 0.5;
    const v = [
      vec3(cx - hx, cy - hy, cz + hz), // 0: front-bottom-left
      vec3(cx + hx, cy - hy, cz + hz), // 1: front-bottom-right
      vec3(cx + hx, cy + hy, cz + hz), // 2: front-top-right
      vec3(cx - hx, cy + hy, cz + hz), // 3: front-top-left
      vec3(cx - hx, cy - hy, cz - hz), // 4: back-bottom-left
      vec3(cx + hx, cy - hy, cz - hz), // 5: back-bottom-right
      vec3(cx + hx, cy + hy, cz - hz), // 6: back-top-right
      vec3(cx - hx, cy + hy, cz - hz), // 7: back-top-left
    ];

    // Counter-clockwise winding when viewed from outside
    const faceIndices = [
      [0, 1, 2, 3], // front (+Z)
      [5, 4, 7, 6], // back (-Z)
      [4, 0, 3, 7], // left (-X)
      [1, 5, 6, 2], // right (+X)
      [3, 2, 6, 7], // top (+Y)
      [4, 5, 1, 0], // bottom (-Y)
    ];

    return faceIndices.map((idx) => ({
      verts: idx.map((i) => v[i]),
      baseColor: options.baseColor || [24, 30, 58],
      edgeColor: options.edgeColor || "rgba(94, 242, 255, 0.72)",
      emissive: options.emissive || 0.08,
      doubleSided: false,
      glow: !!options.glow,
    }));
  }

  function createOctahedronFaces(radius) {
    const r = radius;
    const top = vec3(0, r * 1.35, 0);
    const bot = vec3(0, -r * 1.35, 0);
    const px = vec3(r, 0, 0);
    const nx = vec3(-r, 0, 0);
    const pz = vec3(0, 0, r);
    const nz = vec3(0, 0, -r);

    // 8 triangles with outward CCW winding
    return [
      [top, pz, px],
      [top, px, nz],
      [top, nz, nx],
      [top, nx, pz],
      [bot, px, pz],
      [bot, nz, px],
      [bot, nx, nz],
      [bot, pz, nx],
    ];
  }

  function Renderer3D() {
    this.items = [];
    this.polyCount = 0;
  }

  Renderer3D.prototype.clear = function () {
    this.items.length = 0;
    this.polyCount = 0;
  };

  Renderer3D.prototype.addPoly = function (verts, style, cam, cx, cy, lightDir, portalCenter) {
    const camVerts = new Array(verts.length);
    let depthSum = 0;
    for (let i = 0; i < verts.length; i++) {
      const cv = worldToCamera(verts[i], cam);
      if (cv.z <= cam.near) return;
      camVerts[i] = cv;
      depthSum += cv.z;
    }

    // Backface culling in camera space (CCW outward -> camNormal.z > 0 faces camera)
    const e1 = sub(camVerts[1], camVerts[0]);
    const e2 = sub(camVerts[2], camVerts[0]);
    const camNormal = cross(e1, e2);
    if (!style.doubleSided && camNormal.z <= 0) return;

    const proj = new Array(verts.length);
    for (let i = 0; i < camVerts.length; i++) {
      const p = projectPoint(camVerts[i], cam, cx, cy);
      if (!p) return;
      proj[i] = p;
    }

    // World-space lighting
    const we1 = sub(verts[1], verts[0]);
    const we2 = sub(verts[2], verts[0]);
    const normal = normalize(cross(we1, we2));
    const centroid = {
      x: verts.reduce((s, v) => s + v.x, 0) / verts.length,
      y: verts.reduce((s, v) => s + v.y, 0) / verts.length,
      z: verts.reduce((s, v) => s + v.z, 0) / verts.length,
    };

    const keyDiff = Math.max(0, dot(normal, lightDir));
    let portalGlow = 0;
    if (portalCenter) {
      const toPortal = sub(portalCenter, centroid);
      const dist = Math.hypot(toPortal.x, toPortal.y, toPortal.z) || 1;
      const pDir = scale(toPortal, 1 / dist);
      const facingPortal = Math.max(0, dot(normal, pDir));
      portalGlow = (facingPortal * 2.4) / (1 + dist * 0.25);
    }

    const base = style.baseColor;
    const ambient = 0.28 + (style.emissive || 0);
    const shade = clamp(ambient + keyDiff * 0.58, 0.15, 1.35);

    const r = clamp(Math.round(base[0] * shade + portalGlow * 48), 0, 255);
    const g = clamp(Math.round(base[1] * shade + portalGlow * 145), 0, 255);
    const b = clamp(Math.round(base[2] * shade + portalGlow * 185), 0, 255);
    const alpha = style.alpha !== undefined ? style.alpha : 1;

    this.polyCount++;
    this.items.push({
      type: "poly",
      depth: depthSum / verts.length,
      proj,
      fillStyle: alpha < 1 ? `rgba(${r},${g},${b},${alpha})` : `rgb(${r},${g},${b})`,
      strokeStyle: style.edgeColor || null,
      lineWidth: style.lineWidth || 1,
      additive: !!style.additive,
    });
  };

  Renderer3D.prototype.addLine = function (a, b, color, lineWidth, cam, cx, cy, additive) {
    const ca = worldToCamera(a, cam);
    const cb = worldToCamera(b, cam);
    if (ca.z <= cam.near && cb.z <= cam.near) return;

    let pA = ca;
    let pB = cb;
    if (pA.z <= cam.near) {
      const t = (cam.near + 0.01 - pA.z) / (pB.z - pA.z);
      pA = {
        x: pA.x + (pB.x - pA.x) * t,
        y: pA.y + (pB.y - pA.y) * t,
        z: cam.near + 0.01,
      };
    } else if (pB.z <= cam.near) {
      const t = (cam.near + 0.01 - pB.z) / (pA.z - pB.z);
      pB = {
        x: pB.x + (pA.x - pB.x) * t,
        y: pB.y + (pA.y - pB.y) * t,
        z: cam.near + 0.01,
      };
    }

    const sa = projectPoint(pA, cam, cx, cy);
    const sb = projectPoint(pB, cam, cx, cy);
    if (!sa || !sb) return;

    this.items.push({
      type: "line",
      depth: (pA.z + pB.z) * 0.5,
      ax: sa.x,
      ay: sa.y,
      bx: sb.x,
      by: sb.y,
      color,
      lineWidth: lineWidth || 1,
      additive: !!additive,
    });
  };

  Renderer3D.prototype.addGlowSprite = function (pos, radiusWorld, colorCore, colorEdge, cam, cx, cy, depthBias) {
    const cp = worldToCamera(pos, cam);
    if (cp.z <= cam.near) return;
    const sp = projectPoint(cp, cam, cx, cy);
    if (!sp) return;
    const r = Math.max(1, radiusWorld * sp.scale);
    this.items.push({
      type: "glow",
      depth: cp.z + (depthBias || 0),
      x: sp.x,
      y: sp.y,
      r,
      colorCore,
      colorEdge,
    });
  };

  Renderer3D.prototype.flush = function (ctx) {
    this.items.sort((a, b) => b.depth - a.depth);
    for (let i = 0; i < this.items.length; i++) {
      const item = this.items[i];
      if (item.type === "poly") {
        if (item.additive) {
          ctx.save();
          ctx.globalCompositeOperation = "lighter";
        }
        ctx.beginPath();
        ctx.moveTo(item.proj[0].x, item.proj[0].y);
        for (let j = 1; j < item.proj.length; j++) {
          ctx.lineTo(item.proj[j].x, item.proj[j].y);
        }
        ctx.closePath();
        ctx.fillStyle = item.fillStyle;
        ctx.fill();
        if (item.strokeStyle) {
          ctx.strokeStyle = item.strokeStyle;
          ctx.lineWidth = item.lineWidth;
          ctx.stroke();
        }
        if (item.additive) {
          ctx.restore();
        }
      } else if (item.type === "line") {
        if (item.additive) {
          ctx.save();
          ctx.globalCompositeOperation = "lighter";
        }
        ctx.beginPath();
        ctx.moveTo(item.ax, item.ay);
        ctx.lineTo(item.bx, item.by);
        ctx.strokeStyle = item.color;
        ctx.lineWidth = item.lineWidth;
        ctx.stroke();
        if (item.additive) {
          ctx.restore();
        }
      } else if (item.type === "glow") {
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        const grad = ctx.createRadialGradient(item.x, item.y, 0, item.x, item.y, item.r);
        grad.addColorStop(0, item.colorCore);
        grad.addColorStop(1, item.colorEdge);
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(item.x, item.y, item.r, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    }
  };

  global.Engine3D = {
    vec3,
    add,
    sub,
    scale,
    normalize,
    rotateX,
    rotateY,
    rotateZ,
    clamp,
    createCamera,
    worldToCamera,
    projectPoint,
    createBoxFaces,
    createOctahedronFaces,
    Renderer3D,
  };
})(window);
