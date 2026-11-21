// scene.js - builds the neon portal scene each frame
// Depends on Engine3D (Renderer, boxFaces, octaFaces, ringFaces, rotX/rotY/rotZ).

(function (global) {
  "use strict";

  const E = global.Engine3D;

  // Palette
  const SLATE = [26, 34, 52];
  const SLATE_RIM = [0, 240, 255];
  const CYAN = [0, 240, 255];
  const MAGENTA = [255, 42, 212];

  const STAR_COUNT = 180;
  const PARTICLE_COUNT = 110;
  const CRYSTAL_COUNT = 6;

  function Scene() {
    // ---- static monument geometry (6 boxes = 36 box faces) --------------
    // two-tier stepped platform, twin pillars, lintel beam, crown cap
    this.monument = [];
    this._addBox([0, 0.5, 0], 4.0, 0.5, 3.0);   // platform tier 1 (bottom)
    this._addBox([0, 1.5, 0], 3.0, 0.5, 2.0);   // platform tier 2 (top)
    this._addBox([-2.5, 4.0, 0], 0.5, 2.5, 0.5); // left pillar
    this._addBox([2.5, 4.0, 0], 0.5, 2.5, 0.5);  // right pillar
    this._addBox([0, 6.5, 0], 3.0, 0.5, 0.6);   // lintel beam
    this._addBox([0, 7.2, 0], 3.2, 0.4, 0.8);   // crown cap

    // ---- stars (180) ----------------------------------------------------
    this.stars = [];
    for (let i = 0; i < STAR_COUNT; i++) {
      // distribute on a large sphere shell
      const u = Math.random() * 2 - 1;
      const th = Math.random() * Math.PI * 2;
      const r = Math.sqrt(1 - u * u);
      const R = 90;
      this.stars.push({
        p: [r * Math.cos(th) * R, Math.abs(u) * R * 0.8 + 4, r * Math.sin(th) * R],
        ph: Math.random() * Math.PI * 2,
        sp: 1 + Math.random() * 3,
        sz: 0.6 + Math.random() * 1.6
      });
    }

    // ---- rising particles (110) -----------------------------------------
    this.parts = [];
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      this.parts.push(this._newParticle(true));
    }
  }

  Scene.prototype._addBox = function (c, hx, hy, hz) {
    const faces = E.boxFaces(c, hx, hy, hz);
    for (let i = 0; i < faces.length; i++) {
      this.monument.push({
        verts: faces[i],
        color: SLATE,
        rim: SLATE_RIM,
        glow: 0.15
      });
    }
  };

  Scene.prototype._newParticle = function (randomY) {
    const a = Math.random() * Math.PI * 2;
    const rad = Math.random() * 3.5;
    return {
      x: Math.cos(a) * rad,
      y: randomY ? Math.random() * 12 : -1,
      z: Math.sin(a) * rad,
      vy: 0.6 + Math.random() * 1.4,
      sway: Math.random() * Math.PI * 2,
      sz: 1.5 + Math.random() * 3,
      mag: Math.random() < 0.5
    };
  };

  // Build the full polygon list for this frame.
  // t = elapsed seconds, cam = { theta, dist, height }
  Scene.prototype.build = function (t, cam) {
    const polys = [];

    // --- monument (static) ---
    for (let i = 0; i < this.monument.length; i++) {
      polys.push(this.monument[i]);
    }

    // --- portal core: two counter-rotating rings + vortex ---
    const coreY = 4.0;
    const spin = t * 0.9;
    function xformRing(v, angleZ, tiltX) {
      let p = E.rotX(v, Math.PI / 2 + tiltX);
      p = E.rotZ(p, angleZ);
      return [p[0], p[1] + coreY, p[2]];
    }
    // outer cyan ring (rotates +), inner magenta ring (rotates -)
    const ringA = E.ringFaces([0, 0, 0], 1.65, 2.0, 28);
    const ringB = E.ringFaces([0, 0, 0], 1.25, 1.55, 28);
    for (let i = 0; i < ringA.length; i++) {
      const f = ringA[i].map((v) => xformRing(v, spin, 0.08 * Math.sin(t * 0.7)));
      polys.push({ verts: f, color: [0, 40, 60], rim: CYAN, glow: 0.9, noCull: true });
    }
    for (let i = 0; i < ringB.length; i++) {
      const f = ringB[i].map((v) => xformRing(v, -spin * 1.35, -0.08 * Math.cos(t * 0.7)));
      polys.push({ verts: f, color: [50, 0, 45], rim: MAGENTA, glow: 0.9, noCull: true });
    }
    // vortex energy disc (glowing radial core)
    const disc = E.ringFaces([0, 0, 0], 0.15, 1.18, 24);
    for (let i = 0; i < disc.length; i++) {
      const f = disc[i].map((v) => xformRing(v, spin * 0.5, 0));
      polys.push({ verts: f, color: [10, 20, 48], rim: CYAN, glow: 1.0, noCull: true });
    }

    // --- 6 orbiting octahedral crystals (48 triangles) ---
    for (let i = 0; i < CRYSTAL_COUNT; i++) {
      const a = (i / CRYSTAL_COUNT) * Math.PI * 2 + t * 0.6;
      const R = 5.2;
      const cx = Math.cos(a) * R;
      const cy = coreY + Math.sin(t * 1.2 + i) * 0.6;
      const cz = Math.sin(a) * R;
      const faces = E.octaFaces([cx, cy, cz], 0.55);
      const col = i % 2 === 0 ? CYAN : MAGENTA;
      for (let k = 0; k < faces.length; k++) {
        polys.push({ verts: faces[k], color: col, rim: col, glow: 0.8 });
      }
    }

    // --- cyber grid floor (perspective neon lines fading into distance) ---
    this._grid(polys, t);

    // --- stars (twinkling) ---
    for (let i = 0; i < this.stars.length; i++) {
      const s = this.stars[i];
      const tw = 0.4 + 0.6 * (0.5 + 0.5 * Math.sin(t * s.sp + s.ph));
      polys.push({
        verts: [s.p],
        color: [200, 230, 255],
        rim: [255, 255, 255],
        glow: tw,
        star: true,
        sz: s.sz * tw
      });
    }

    // --- rising particles ---
    for (let i = 0; i < this.parts.length; i++) {
      const p = this.parts[i];
      const col = p.mag ? MAGENTA : CYAN;
      polys.push({
        verts: [[p.x, p.y, p.z]],
        color: col,
        rim: [255, 255, 255],
        glow: 0.9,
        star: true,
        sz: p.sz
      });
    }

    return polys;
  };

  Scene.prototype._grid = function (polys, t) {
    const y = -0.02;
    const span = 40;
    const step = 2;
    const pulse = 0.5 + 0.5 * Math.sin(t * 1.5);
    for (let i = -span; i <= span; i += step) {
      // lines along Z
      polys.push({
        verts: [[i, y, -span], [i, y, span]],
        color: [0, 60, 90],
        rim: CYAN,
        glow: 0.3 + pulse * 0.4,
        line: true,
        lw: 1.5
      });
      // lines along X
      polys.push({
        verts: [[-span, y, i], [span, y, i]],
        color: [0, 60, 90],
        rim: CYAN,
        glow: 0.3 + pulse * 0.4,
        line: true,
        lw: 1.5
      });
    }
  };

  // Advance particle motion. dt in seconds, speed multiplier.
  Scene.prototype.update = function (dt, speed) {
    for (let i = 0; i < this.parts.length; i++) {
      const p = this.parts[i];
      p.y += p.vy * dt * speed;
      p.sway += dt * speed;
      p.x += Math.sin(p.sway) * 0.02;
      if (p.y > 12) {
        this.parts[i] = this._newParticle(false);
      }
    }
  };

  global.Scene = Scene;
})(typeof window !== "undefined" ? window : globalThis);
