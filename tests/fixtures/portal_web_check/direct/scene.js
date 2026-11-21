/**
 * scene.js - 3D Neon Portal scene definition, animation, and rendering.
 */
(function (global) {
  'use strict';

  const { Vec3, createBox, createOctahedron, prepareFace, drawFace } = global.Engine3D;

  const STAR_COUNT = 180;
  const PARTICLE_COUNT = 110;
  const CRYSTAL_COUNT = 6;

  class PortalScene {
    constructor() {
      this.time = 0;
      this.lightDir = Vec3.normalize({ x: 0.45, y: 0.85, z: 0.55 });
      this.portalCenter = { x: 0, y: 3.05, z: 0 };

      // 6 boxes = 36 box faces:
      // 1-2: Two-tier platform, 3-4: Twin pillars, 5: Lintel, 6: Crown cap
      this.boxFaces = [
        ...createBox(8.6, 0.45, 5.4, 0, 0.225, 0, {
          fill: [20, 26, 58],
          edge: '#00e5ff',
          emissive: 0.22,
          lineWidth: 1.3,
          glow: 8,
        }),
        ...createBox(6.4, 0.42, 4.0, 0, 0.66, 0, {
          fill: [28, 30, 72],
          edge: '#38bdf8',
          emissive: 0.26,
          lineWidth: 1.4,
          glow: 10,
        }),
        ...createBox(0.95, 4.3, 0.95, -2.15, 3.02, 0, {
          fill: [26, 22, 66],
          edge: '#00f5d4',
          emissive: 0.28,
          lineWidth: 1.4,
          glow: 10,
        }),
        ...createBox(0.95, 4.3, 0.95, 2.15, 3.02, 0, {
          fill: [26, 22, 66],
          edge: '#00f5d4',
          emissive: 0.28,
          lineWidth: 1.4,
          glow: 10,
        }),
        ...createBox(5.7, 0.72, 1.25, 0, 5.53, 0, {
          fill: [38, 22, 76],
          edge: '#f43f5e',
          emissive: 0.3,
          lineWidth: 1.5,
          glow: 12,
        }),
        ...createBox(3.6, 0.48, 0.9, 0, 6.13, 0, {
          fill: [52, 24, 92],
          edge: '#e879f9',
          emissive: 0.34,
          lineWidth: 1.5,
          glow: 14,
        }),
      ];

      // 6 orbiting octahedral crystals (6 * 8 = 48 triangles)
      this.octaGeo = createOctahedron(0.42, 1.45);
      const crystalPalettes = [
        { fill: [0, 230, 255], edge: '#a5f3fc' },
        { fill: [236, 72, 153], edge: '#fbcfe8' },
        { fill: [168, 85, 247], edge: '#e9d5ff' },
        { fill: [34, 211, 238], edge: '#cffafe' },
        { fill: [244, 63, 94], edge: '#fecdd3' },
        { fill: [56, 189, 248], edge: '#bae6fd' },
      ];
      this.crystals = Array.from({ length: CRYSTAL_COUNT }, (_, i) => ({
        angleOffset: (i / CRYSTAL_COUNT) * Math.PI * 2,
        orbitRadius: 4.35,
        bobPhase: i * 1.1,
        spinSpeed: 1.2 + (i % 3) * 0.45,
        fill: crystalPalettes[i].fill,
        edge: crystalPalettes[i].edge,
      }));

      // 180 twinkling stars
      this.stars = Array.from({ length: STAR_COUNT }, (_, i) => {
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos(2 * Math.random() - 1);
        const r = 55 + Math.random() * 35;
        const tints = ['#ffffff', '#bae6fd', '#e9d5ff', '#a5f3fc'];
        return {
          pos: {
            x: r * Math.sin(phi) * Math.cos(theta),
            y: Math.abs(r * Math.cos(phi)) * 0.85 + 2,
            z: r * Math.sin(phi) * Math.sin(theta),
          },
          size: 0.7 + Math.random() * 1.7,
          phase: Math.random() * Math.PI * 2,
          speed: 1.4 + Math.random() * 2.8,
          color: tints[i % tints.length],
        };
      });

      // 110 rising particles
      this.particles = Array.from({ length: PARTICLE_COUNT }, () =>
        this._spawnParticle(true)
      );
    }

    _spawnParticle(randomHeight = false) {
      const angle = Math.random() * Math.PI * 2;
      const radius = 0.25 + Math.random() * 2.7;
      const colors = ['#00f5d4', '#38bdf8', '#e879f9', '#f472b6', '#ffffff'];
      return {
        x: Math.cos(angle) * radius,
        y: randomHeight ? 0.5 + Math.random() * 6.5 : 0.4 + Math.random() * 0.7,
        z: Math.sin(angle) * radius * 0.7,
        vy: 0.75 + Math.random() * 1.35,
        swirlSpeed: (Math.random() - 0.5) * 1.8,
        swirlRadius: 0.15 + Math.random() * 0.35,
        phase: Math.random() * Math.PI * 2,
        size: 1.4 + Math.random() * 2.4,
        maxY: 6.8 + Math.random() * 1.8,
        color: colors[Math.floor(Math.random() * colors.length)],
      };
    }

    reset() {
      this.time = 0;
      this.particles = Array.from({ length: PARTICLE_COUNT }, () =>
        this._spawnParticle(true)
      );
    }

    update(dt, speed) {
      const step = dt * speed;
      this.time += step;

      for (let i = 0; i < this.particles.length; i++) {
        const p = this.particles[i];
        p.y += p.vy * step;
        p.phase += p.swirlSpeed * step;
        if (p.y >= p.maxY) {
          this.particles[i] = this._spawnParticle(false);
        }
      }
    }

    _drawBackground(ctx, w, h) {
      const cx = w * 0.5;
      const cy = h * 0.48;
      const radius = Math.max(w, h) * 0.75;
      const grad = ctx.createRadialGradient(cx, cy, 10, cx, cy, radius);
      grad.addColorStop(0, '#13163a');
      grad.addColorStop(0.42, '#0a0d24');
      grad.addColorStop(1, '#03040a');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);
    }

    _drawStars(ctx, camera, cx, cy, scale) {
      ctx.save();
      for (let i = 0; i < this.stars.length; i++) {
        const s = this.stars[i];
        const proj = camera.projectWorld(s.pos, cx, cy, scale);
        if (!proj) continue;
        const twinkle = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(this.time * s.speed + s.phase));
        ctx.globalAlpha = twinkle;
        ctx.fillStyle = s.color;
        ctx.beginPath();
        ctx.arc(proj.x, proj.y, s.size, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    }

    _drawCyberGrid(ctx, camera, cx, cy, scale) {
      const extent = 20;
      const step = 2;
      ctx.save();
      ctx.lineWidth = 1;

      for (let i = -extent; i <= extent; i += step) {
        const isMajor = i % 4 === 0;
        const alpha = isMajor ? 0.34 : 0.16;
        ctx.strokeStyle = isMajor ? `rgba(0, 229, 255, ${alpha})` : `rgba(139, 92, 246, ${alpha})`;

        // Line along Z
        const a1 = camera.projectWorld({ x: i, y: 0, z: -extent }, cx, cy, scale);
        const b1 = camera.projectWorld({ x: i, y: 0, z: extent }, cx, cy, scale);
        if (a1 && b1) {
          ctx.beginPath();
          ctx.moveTo(a1.x, a1.y);
          ctx.lineTo(b1.x, b1.y);
          ctx.stroke();
        }

        // Line along X
        const a2 = camera.projectWorld({ x: -extent, y: 0, z: i }, cx, cy, scale);
        const b2 = camera.projectWorld({ x: extent, y: 0, z: i }, cx, cy, scale);
        if (a2 && b2) {
          ctx.beginPath();
          ctx.moveTo(a2.x, a2.y);
          ctx.lineTo(b2.x, b2.y);
          ctx.stroke();
        }
      }
      ctx.restore();
    }

    _drawPortalCoreAndRings(ctx, camera, cx, cy, scale) {
      const center = this.portalCenter;
      const viewCenter = camera.worldToView(center);
      if (viewCenter.z <= camera.near) return;

      const projCenter = camera.projectView(viewCenter, cx, cy, scale);
      const coreRadius = 1.48 * projCenter.scale;

      // Glowing portal core
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';

      const outerGlow = ctx.createRadialGradient(
        projCenter.x, projCenter.y, coreRadius * 0.08,
        projCenter.x, projCenter.y, coreRadius * 1.45
      );
      outerGlow.addColorStop(0, 'rgba(255, 255, 255, 0.95)');
      outerGlow.addColorStop(0.28, 'rgba(0, 245, 212, 0.78)');
      outerGlow.addColorStop(0.58, 'rgba(168, 85, 247, 0.45)');
      outerGlow.addColorStop(1, 'rgba(168, 85, 247, 0)');

      ctx.fillStyle = outerGlow;
      ctx.beginPath();
      ctx.arc(projCenter.x, projCenter.y, coreRadius * 1.45, 0, Math.PI * 2);
      ctx.fill();

      // Inner pulsing vortex arcs
      const pulse = 0.9 + 0.1 * Math.sin(this.time * 3.2);
      ctx.strokeStyle = 'rgba(165, 243, 252, 0.7)';
      ctx.lineWidth = 2;
      for (let k = 0; k < 3; k++) {
        const startAngle = this.time * (1.6 + k * 0.5) + k * 2.1;
        ctx.beginPath();
        ctx.arc(
          projCenter.x,
          projCenter.y,
          coreRadius * (0.42 + k * 0.2) * pulse,
          startAngle,
          startAngle + Math.PI * 1.15
        );
        ctx.stroke();
      }
      ctx.restore();

      // Two counter-rotating 3D rings around portal core
      this._drawRing3D(ctx, camera, cx, cy, scale, {
        radius: 1.72,
        segments: 48,
        rotZ: this.time * 0.95,
        rotX: 0.25 * Math.sin(this.time * 0.6),
        rotY: 0.18,
        color: '#00f5d4',
        lineWidth: 2.4,
        dashEvery: 6,
      });

      this._drawRing3D(ctx, camera, cx, cy, scale, {
        radius: 1.38,
        segments: 40,
        rotZ: -this.time * 1.35,
        rotX: -0.35,
        rotY: 0.25 * Math.cos(this.time * 0.7),
        color: '#e879f9',
        lineWidth: 2.2,
        dashEvery: 5,
      });
    }

    _drawRing3D(ctx, camera, cx, cy, scale, opts) {
      const pts = [];
      for (let i = 0; i < opts.segments; i++) {
        const a = (i / opts.segments) * Math.PI * 2;
        let p = {
          x: Math.cos(a) * opts.radius,
          y: Math.sin(a) * opts.radius,
          z: 0,
        };
        p = Vec3.rotateZ(p, opts.rotZ);
        p = Vec3.rotateX(p, opts.rotX);
        p = Vec3.rotateY(p, opts.rotY);
        p = Vec3.add(p, this.portalCenter);
        pts.push(camera.projectWorld(p, cx, cy, scale));
      }

      ctx.save();
      ctx.strokeStyle = opts.color;
      ctx.shadowColor = opts.color;
      ctx.shadowBlur = 12;
      ctx.lineWidth = opts.lineWidth;

      for (let i = 0; i < opts.segments; i++) {
        if (i % opts.dashEvery === 0) continue; // segmented cyber-ring gap
        const p1 = pts[i];
        const p2 = pts[(i + 1) % opts.segments];
        if (!p1 || !p2) continue;
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
      }
      ctx.restore();
    }

    _drawParticles(ctx, camera, cx, cy, scale) {
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      for (let i = 0; i < this.particles.length; i++) {
        const p = this.particles[i];
        const worldPos = {
          x: p.x + Math.cos(p.phase) * p.swirlRadius,
          y: p.y,
          z: p.z + Math.sin(p.phase) * p.swirlRadius,
        };
        const proj = camera.projectWorld(worldPos, cx, cy, scale);
        if (!proj) continue;

        const life = (p.y - 0.4) / (p.maxY - 0.4);
        const alpha = Math.sin(Math.min(1, Math.max(0, life)) * Math.PI) * 0.9;
        const r = Math.max(1, (p.size * proj.scale) / 220);

        ctx.globalAlpha = alpha;
        ctx.fillStyle = p.color;
        ctx.shadowColor = p.color;
        ctx.shadowBlur = 8;
        ctx.beginPath();
        ctx.arc(proj.x, proj.y, r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();
    }

    render(ctx, width, height, camera) {
      const cx = width * 0.5;
      const cy = height * 0.54;
      const scale = Math.min(width, height) / 760;

      this._drawBackground(ctx, width, height);
      this._drawStars(ctx, camera, cx, cy, scale);
      this._drawCyberGrid(ctx, camera, cx, cy, scale);

      // Collect all 3D polygon faces (36 box faces + 48 crystal triangles = 84 polys)
      const renderFaces = [];

      for (let i = 0; i < this.boxFaces.length; i++) {
        const bf = this.boxFaces[i];
        const prepared = prepareFace(bf.pts, camera, cx, cy, scale, this.lightDir, bf);
        if (prepared) renderFaces.push(prepared);
      }

      for (let c = 0; c < this.crystals.length; c++) {
        const cr = this.crystals[c];
        const orbitAngle = this.time * 0.55 + cr.angleOffset;
        const worldCenter = {
          x: Math.cos(orbitAngle) * cr.orbitRadius,
          y: this.portalCenter.y + Math.sin(this.time * 1.8 + cr.bobPhase) * 0.42,
          z: Math.sin(orbitAngle) * cr.orbitRadius,
        };

        const spinY = this.time * cr.spinSpeed;
        const spinX = this.time * 0.7 + cr.bobPhase;
        const transformedVerts = this.octaGeo.verts.map((v) => {
          let p = Vec3.rotateX(v, spinX);
          p = Vec3.rotateY(p, spinY);
          return Vec3.add(p, worldCenter);
        });

        for (let t = 0; t < this.octaGeo.tris.length; t++) {
          const tri = this.octaGeo.tris[t];
          const pts = [
            transformedVerts[tri[0]],
            transformedVerts[tri[1]],
            transformedVerts[tri[2]],
          ];
          const prepared = prepareFace(pts, camera, cx, cy, scale, this.lightDir, {
            baseColor: cr.fill,
            edgeColor: cr.edge,
            emissive: 0.35,
            lineWidth: 1.25,
            glow: 10,
            alpha: 0.92,
          });
          if (prepared) renderFaces.push(prepared);
        }
      }

      // Painter's sort back-to-front
      renderFaces.sort((a, b) => b.depth - a.depth);

      // Draw portal core & rings around the archway depth
      const portalDepth = camera.worldToView(this.portalCenter).z;
      let portalDrawn = false;

      for (let i = 0; i < renderFaces.length; i++) {
        if (!portalDrawn && renderFaces[i].depth < portalDepth) {
          this._drawPortalCoreAndRings(ctx, camera, cx, cy, scale);
          portalDrawn = true;
        }
        drawFace(ctx, renderFaces[i]);
      }

      if (!portalDrawn) {
        this._drawPortalCoreAndRings(ctx, camera, cx, cy, scale);
      }

      this._drawParticles(ctx, camera, cx, cy, scale);

      return {
        polys: this.boxFaces.length + this.crystals.length * this.octaGeo.tris.length,
        parts: this.particles.length,
      };
    }
  }

  global.PortalScene = PortalScene;
})(window);
