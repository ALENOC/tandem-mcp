/* scene.js - scene graph: monument, crystals, portal core, grid, stars, particles */
(function (global) {
  "use strict";

  const E = global.Engine3D;

  // ---- Color helpers ----
  function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function shade(base, light) {
    // base = [r,g,b], light in [0,1]
    const r = clamp(Math.round(base[0] * light), 0, 255);
    const g = clamp(Math.round(base[1] * light), 0, 255);
    const b = clamp(Math.round(base[2] * light), 0, 255);
    return "rgb(" + r + "," + g + "," + b + ")";
  }
  function rgba(r, g, b, a) { return "rgba(" + r + "," + g + "," + b + "," + a + ")"; }

  // ---- Scene state ----
  function Scene() {
    this.time = 0;
    this.speed = 1;
    this.paused = false;
    this.orbitOn = true;

    // camera
    this.camYaw = 0.6;
    this.camPitch = 0.32;
    this.camDist = 26;
    this.target = [0, 3.2, 0];

    // build static geometry
    this.monument = buildMonument();
    this.crystals = buildCrystals();
    this.stars = buildStars(180);
    this.particles = buildParticles(110);
    this.grid = buildGrid();
  }

  // ---- Monument: 6 boxes = 36 faces ----
  function buildMonument() {
    const boxes = [];
    // two-tier platform
    boxes.push({ c: [0, 0.35, 0], h: [5.2, 0.35, 5.2], base: [40, 46, 92], edge: [90, 200, 255] });   // lower tier
    boxes.push({ c: [0, 1.05, 0], h: [4.0, 0.35, 4.0], base: [52, 58, 110], edge: [120, 220, 255] }); // upper tier
    // twin pillars
    boxes.push({ c: [-3.0, 3.6, 0], h: [0.55, 2.55, 0.55], base: [60, 66, 128], edge: [150, 120, 255] });
    boxes.push({ c: [3.0, 3.6, 0], h: [0.55, 2.55, 0.55], base: [60, 66, 128], edge: [150, 120, 255] });
    // lintel (arch beam)
    boxes.push({ c: [0, 6.35, 0], h: [3.7, 0.5, 0.7], base: [70, 78, 140], edge: [255, 120, 220] });
    // crown cap
    boxes.push({ c: [0, 7.05, 0], h: [1.1, 0.4, 1.1], base: [90, 96, 170], edge: [255, 180, 120] });
    // precompute faces
    for (const b of boxes) {
      b.faces = E.buildBox(b.c[0], b.c[1], b.c[2], b.h[0], b.h[1], b.h[2]);
    }
    return boxes;
  }

  // ---- Crystals: 6 orbiting octahedra (8 tris each = 48) ----
  function buildCrystals() {
    const arr = [];
    for (let i = 0; i < 6; i++) {
      arr.push({
        phase: (i / 6) * Math.PI * 2,
        radius: 6.4,
        height: 3.6 + Math.sin(i * 1.7) * 1.4,
        spin: 0.6 + i * 0.13,
        r: 0.55 + (i % 3) * 0.12,
        hue: [185, 265, 320, 160, 210, 290][i]
      });
    }
    return arr;
  }

  // ---- Stars: 180 twinkling background stars on a far sphere ----
  function buildStars(n) {
    const arr = [];
    for (let i = 0; i < n; i++) {
      // fibonacci-ish sphere distribution
      const y = 1 - (i / (n - 1)) * 2;
      const rad = Math.sqrt(Math.max(0, 1 - y * y));
      const th = i * 2.399963;
      arr.push({
        x: Math.cos(th) * rad * 120,
        y: y * 120 + 20,
        z: Math.sin(th) * rad * 120,
        tw: Math.random() * Math.PI * 2,
        s: 0.6 + Math.random() * 1.4
      });
    }
    return arr;
  }

  // ---- Particles: 110 rising neon particles ----
  function buildParticles(n) {
    const arr = [];
    const hues = [185, 265, 320, 160];
    for (let i = 0; i < n; i++) {
      arr.push({
        x: (Math.random() - 0.5) * 22,
        y: Math.random() * 14,
        z: (Math.random() - 0.5) * 22,
        vy: 0.6 + Math.random() * 1.4,
        hue: hues[i % hues.length],
        size: 0.05 + Math.random() * 0.12,
        life: Math.random()
      });
    }
    return arr;
  }

  // ---- Grid floor ----
  function buildGrid() {
    const lines = [];
    const ext = 30;
    const step = 2;
    for (let i = -ext; i <= ext; i += step) {
      lines.push([i, 0, -ext, i, 0, ext]);   // along z
      lines.push([-ext, 0, i, ext, 0, i]);   // along x
    }
    return lines;
  }

  // ---- Update ----
  Scene.prototype.update = function (dt) {
    if (this.paused) return;
    const s = dt * this.speed;
    this.time += s;
    if (this.orbitOn) this.camYaw += 0.25 * s;
    // particles rise and wrap
    for (const p of this.particles) {
      p.y += p.vy * s;
      p.life += s * 0.5;
      if (p.y > 14) { p.y = 0; p.x = (Math.random() - 0.5) * 22; p.z = (Math.random() - 0.5) * 22; }
    }
  };

  // ---- Render ----
  Scene.prototype.render = function (R) {
    const ctx = R.ctx;
    const W = R.width, H = R.height;
    const t = this.time;
    let polys = 0;

    // background radial gradient (space)
    const bg = ctx.createRadialGradient(W * 0.5, H * 0.42, 0, W * 0.5, H * 0.42, Math.max(W, H) * 0.75);
    bg.addColorStop(0, "#14102e");
    bg.addColorStop(0.45, "#0a0720");
    bg.addColorStop(1, "#04030a");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, W, H);

    // camera
    R.setCamera(this.camYaw, this.camPitch, this.camDist, this.target);
    const cyw = Math.cos(this.camYaw), syw = Math.sin(this.camYaw);
    const cp = Math.cos(this.camPitch), sp = Math.sin(this.camPitch);
    this.camPos = [
      this.target[0] + this.camDist * cp * syw,
      this.target[1] + this.camDist * sp,
      this.target[2] + this.camDist * cp * cyw
    ];

    // ---- Stars (twinkling) ----
    ctx.globalCompositeOperation = "lighter";
    for (const st of this.stars) {
      const p = R.project([st.x, st.y, st.z]);
      if (!p) continue;
      const tw = 0.4 + 0.6 * (0.5 + 0.5 * Math.sin(t * 2 + st.tw));
      const r = st.s * tw;
      ctx.fillStyle = rgba(200, 230, 255, 0.5 * tw);
      ctx.beginPath();
      ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";

    // ---- Grid floor ----
    this.renderGrid(R, t);

    // ---- Collect drawable faces for painter's algorithm ----
    const drawList = [];

    // monument boxes
    for (const box of this.monument) {
      for (const f of box.faces) {
        const pts = f.pts;
        // world normal (axis aligned, already unit)
        const n = f.normal;
        // face center
        const cx = (pts[0][0] + pts[2][0]) / 2;
        const cy = (pts[0][1] + pts[2][1]) / 2;
        const cz = (pts[0][2] + pts[2][2]) / 2;
        // view vector from face to camera (approx using target->cam)
        const camPos = this.camPos;
        const vx = camPos[0] - cx, vy = camPos[1] - cy, vz = camPos[2] - cz;
        const vl = Math.hypot(vx, vy, vz) || 1;
        const dot = (n[0] * vx + n[1] * vy + n[2] * vz) / vl;
        if (dot <= 0.02) continue; // backface cull
        // project
        const proj = [R.project(pts[0]), R.project(pts[1]), R.project(pts[2]), R.project(pts[3])];
        if (proj.some(p => !p)) continue;
        // lighting: key light from upper front + ambient
        const light = clamp(0.35 + 0.65 * dot, 0, 1);
        const depth = (proj[0].depth + proj[2].depth) / 2;
        drawList.push({
          type: "quad", depth: depth,
          pts: proj,
          fill: shade(box.base, light),
          stroke: rgba(box.edge[0], box.edge[1], box.edge[2], 0.55 + 0.4 * light),
          lw: 1.2
        });
        polys++;
      }
    }

    // crystals (octahedra)
    for (const cr of this.crystals) {
      const ang = cr.phase + t * 0.5;
      const cx = Math.cos(ang) * cr.radius;
      const cy = cr.height + Math.sin(t * 1.3 + cr.phase) * 0.4;
      const cz = Math.sin(ang) * cr.radius;
      const tris = E.buildOctahedron(cx, cy, cz, cr.r);
      for (const tri of tris) {
        const a = tri[0], b = tri[1], c = tri[2];
        // face normal via cross
        const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
        const wx = c[0] - a[0], wy = c[1] - a[1], wz = c[2] - a[2];
        let nx = uy * wz - uz * wy;
        let ny = uz * wx - ux * wz;
        let nz = ux * wy - uy * wx;
        const nl = Math.hypot(nx, ny, nz) || 1;
        nx /= nl; ny /= nl; nz /= nl;
        const camPos = this.camPos;
        const vx = camPos[0] - cx, vy = camPos[1] - cy, vz = camPos[2] - cz;
        const vl = Math.hypot(vx, vy, vz) || 1;
        const dot = (nx * vx + ny * vy + nz * vz) / vl;
        if (dot <= 0.02) continue;
        const pa = R.project(a), pb = R.project(b), pc = R.project(c);
        if (!pa || !pb || !pc) continue;
        const light = clamp(0.3 + 0.7 * dot, 0, 1);
        const depth = (pa.depth + pb.depth + pc.depth) / 3;
        const h = cr.hue;
        drawList.push({
          type: "tri", depth: depth,
          pts: [pa, pb, pc],
          fill: shade([120 + 60 * light, 120 + 40 * light, 255], 0.5 + 0.5 * light),
          stroke: rgba(180, 120, 255, 0.5 + 0.5 * light),
          lw: 1
        });
        polys++;
      }
    }

    // sort far -> near (painter's algorithm)
    drawList.sort((a, b) => b.depth - a.depth);
    for (const d of drawList) {
      if (d.type === "quad") {
        R.fillQuad(d.pts[0], d.pts[1], d.pts[2], d.pts[3], d.fill, d.stroke, d.lw);
      } else {
        R.fillTriangle(d.pts[0], d.pts[1], d.pts[2], d.fill, d.stroke, d.lw);
      }
    }

    // ---- Portal core (inside arch) ----
    this.renderPortal(R, t);

    // ---- Rising particles (additive glow) ----
    ctx.globalCompositeOperation = "lighter";
    for (const p of this.particles) {
      const pr = R.project([p.x, p.y, p.z]);
      if (!pr) continue;
      const a = 0.35 + 0.4 * (0.5 + 0.5 * Math.sin(p.life * 3));
      const rad = p.size * 60;
      const g = ctx.createRadialGradient(pr.x, pr.y, 0, pr.x, pr.y, rad);
      g.addColorStop(0, rgba(255, 255, 255, a));
      g.addColorStop(0.4, hsla(p.hue, 100, 70, a * 0.8));
      g.addColorStop(1, hsla(p.hue, 100, 60, 0));
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, rad, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";

    return polys;
  };

  Scene.prototype.renderGrid = function (R, t) {
    const ctx = R.ctx;
    ctx.globalCompositeOperation = "lighter";
    ctx.lineWidth = 1;
    for (const L of this.grid.lines) {
      const a = R.project([L[0], L[1], L[2]]);
      const b = R.project([L[3], L[4], L[5]]);
      if (!a || !b) continue;
      const pulse = 0.15 + 0.1 * Math.sin(t * 1.5);
      ctx.strokeStyle = rgba(60, 200, 255, pulse);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
    ctx.globalCompositeOperation = "source-over";
  };

  Scene.prototype.renderPortal = function (R, t) {
    const ctx = R.ctx;
    const cx = 0, cy = 3.6, cz = 0;
    const c = R.project([cx, cy, cz]);
    if (!c) return;
    const baseR = R.focal * 0.05;

    // radial energy glow
    ctx.globalCompositeOperation = "lighter";
    const glow = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, baseR * 3.2);
    glow.addColorStop(0, rgba(255, 255, 255, 0.9));
    glow.addColorStop(0.25, rgba(140, 220, 255, 0.55));
    glow.addColorStop(0.6, rgba(150, 100, 255, 0.25));
    glow.addColorStop(1, rgba(120, 80, 255, 0));
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(c.x, c.y, baseR * 3.2, 0, Math.PI * 2);
    ctx.fill();

    // two counter-rotating concentric rings
    const rings = [
      { r: baseR * 1.6, dir: 1, hue: 190, seg: 40 },
      { r: baseR * 2.3, dir: -1, hue: 280, seg: 56 }
    ];
    for (const ring of rings) {
      const rot = t * 0.8 * ring.dir;
      ctx.strokeStyle = hsla(ring.hue, 100, 70, 0.85);
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      for (let i = 0; i <= ring.seg; i++) {
        const a = (i / ring.seg) * Math.PI * 2 + rot;
        const wob = 1 + 0.06 * Math.sin(a * 6 + t * 3);
        const x = c.x + Math.cos(a) * ring.r * wob;
        const y = c.y + Math.sin(a) * ring.r * wob;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.stroke();
    }
    ctx.globalCompositeOperation = "source-over";
  };

  // ---- hsla helper ----
  function hsla(h, s, l, a) { return "hsla(" + h + "," + s + "%," + l + "%," + a + ")"; }

  global.Scene = Scene;
})(typeof window !== "undefined" ? window : globalThis);
