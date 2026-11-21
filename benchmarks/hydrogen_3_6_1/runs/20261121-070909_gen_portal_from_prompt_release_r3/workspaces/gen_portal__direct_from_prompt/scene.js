/**
 * Neon Portal 3D scene definition and frame renderer.
 * Geometry counts:
 *  - 6 boxes (two-tier platform, twin pillars, lintel, crown cap) = 36 box faces
 *  - 6 orbiting octahedral crystals = 48 triangles
 *  - 180 twinkling stars
 *  - 110 rising particles
 *  - Portal core + 2 counter-rotating rings + cyber grid floor
 */
(function (global) {
  'use strict';

  const {
    Vec3,
    createBoxMesh,
    createOctahedronFaces,
    rotatePointX,
    rotatePointY
  } = global.Engine3D;

  const STAR_COUNT = 180;
  const PARTICLE_COUNT = 110;
  const CRYSTAL_COUNT = 6;
  const PORTAL_CENTER = { x: 0, y: 2.35, z: 0 };

  class NeonPortalScene {
    constructor() {
      this.time = 0;
      this.boxFaces = this._buildArchitecture(); // 6 boxes * 6 faces = 36 faces
      this.octaBase = createOctahedronFaces(0.28, 1.55); // 8 triangles per crystal
      this.crystals = this._initCrystals(); // 6 * 8 = 48 triangles
      this.stars = this._initStars(); // 180 stars
      this.particles = this._initParticles(); // 110 particles
    }

    _buildArchitecture() {
      const darkStone = {
        baseColor: [24, 30, 62],
        portalGlowColor: [55, 220, 255],
        stroke: 'rgba(85, 225, 255, 0.42)',
        lineWidth: 1.1
      };
      const pillarStyle = {
        baseColor: [28, 24, 68],
        portalGlowColor: [140, 120, 255],
        stroke: 'rgba(185, 115, 255, 0.48)',
        lineWidth: 1.1
      };
      const crownStyle = {
        baseColor: [34, 28, 76],
        portalGlowColor: [90, 240, 255],
        stroke: 'rgba(94, 242, 255, 0.58)',
        lineWidth: 1.2
      };

      const boxes = [
        // 1. Lower platform tier
        ...createBoxMesh(0, 0.16, 0, 5.2, 0.32, 3.6, darkStone),
        // 2. Upper platform tier
        ...createBoxMesh(0, 0.44, 0, 3.8, 0.24, 2.5, darkStone),
        // 3. Left pillar
        ...createBoxMesh(-1.35, 2.26, 0, 0.56, 3.4, 0.56, pillarStyle),
        // 4. Right pillar
        ...createBoxMesh(1.35, 2.26, 0, 0.56, 3.4, 0.56, pillarStyle),
        // 5. Lintel
        ...createBoxMesh(0, 4.16, 0, 3.6, 0.42, 0.72, pillarStyle),
        // 6. Crown cap
        ...createBoxMesh(0, 4.54, 0, 2.5, 0.34, 0.52, crownStyle)
      ];

      return boxes; // 36 box faces
    }

    _initCrystals() {
      const crystals = [];
      const palettes = [
        { base: [50, 225, 255], stroke: 'rgba(150, 252, 255, 0.85)' },
        { base: [210, 85, 255], stroke: 'rgba(245, 165, 255, 0.85)' },
        { base: [85, 165, 255], stroke: 'rgba(170, 220, 255, 0.85)' }
      ];

      for (let i = 0; i < CRYSTAL_COUNT; i++) {
        const angle = (i / CRYSTAL_COUNT) * Math.PI * 2;
        crystals.push({
          baseAngle: angle,
          orbitRadius: 2.55 + (i % 2) * 0.45,
          baseY: 1.65 + (i % 3) * 0.65,
          orbitSpeed: 0.45 + (i % 2) * 0.12,
          spinSpeed: 1.3 + i * 0.2,
          bobPhase: i * 1.1,
          palette: palettes[i % palettes.length]
        });
      }
      return crystals;
    }

    _initStars() {
      const stars = [];
      for (let i = 0; i < STAR_COUNT; i++) {
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos(2 * Math.random() - 1);
        const r = 24 + Math.random() * 24;
        stars.push({
          pos: {
            x: r * Math.sin(phi) * Math.cos(theta),
            y: Math.abs(r * Math.cos(phi)) * 0.85 + 0.5,
            z: r * Math.sin(phi) * Math.sin(theta)
          },
          size: 0.8 + Math.random() * 1.7,
          phase: Math.random() * Math.PI * 2,
          speed: 1.4 + Math.random() * 2.8,
          hue: i % 5 === 0 ? '#d8a6ff' : i % 3 === 0 ? '#8ef5ff' : '#ffffff'
        });
      }
      return stars;
    }

    _initParticles() {
      const particles = [];
      for (let i = 0; i < PARTICLE_COUNT; i++) {
        particles.push(this._resetParticle({}, true));
      }
      return particles;
    }

    _resetParticle(p, randomHeight) {
      const angle = Math.random() * Math.PI * 2;
      const radius = 0.25 + Math.random() * 2.2;
      p.x = Math.cos(angle) * radius;
      p.z = Math.sin(angle) * radius * 0.75;
      p.y = randomHeight ? 0.35 + Math.random() * 4.8 : 0.3 + Math.random() * 0.35;
      p.vy = 0.55 + Math.random() * 1.05;
      p.swirl = (Math.random() - 0.5) * 0.9;
      p.size = 1.3 + Math.random() * 2.2;
      p.maxY = 4.8 + Math.random() * 1.4;
      p.color = Math.random() > 0.45 ? [88, 242, 255] : [215, 110, 255];
      return p;
    }

    update(dt) {
      this.time += dt;
      for (let i = 0; i < this.particles.length; i++) {
        const p = this.particles[i];
        p.y += p.vy * dt;
        const a = p.swirl * dt;
        const c = Math.cos(a);
        const s = Math.sin(a);
        const nx = p.x * c - p.z * s;
        const nz = p.x * s + p.z * c;
        p.x = nx;
        p.z = nz;
        if (p.y > p.maxY) {
          this._resetParticle(p, false);
        }
      }
    }

    render(renderer, camera) {
      const ctx = renderer.ctx;
      const portalScreen = camera.projectWorldPoint(PORTAL_CENTER, renderer.width, renderer.height);

      // 1. Dark radial-gradient space background
      renderer.drawSpaceBackground(portalScreen);

      // 2. 180 twinkling stars
      this._renderStars(renderer, camera);

      // 3. Cyber grid floor
      this._renderCyberGrid(renderer, camera);

      // 4. Collect 3D solid polygons (36 box faces + 48 crystal triangles = 84 polys)
      renderer.beginFrame();

      for (let i = 0; i < this.boxFaces.length; i++) {
        const face = this.boxFaces[i];
        renderer.submitPolygon(face.verts, camera, {
          ...face.style,
          portalCenter: PORTAL_CENTER,
          cullBackface: true
        });
      }

      for (let i = 0; i < this.crystals.length; i++) {
        const c = this.crystals[i];
        const orbitAngle = c.baseAngle + this.time * c.orbitSpeed;
        const cx = Math.cos(orbitAngle) * c.orbitRadius;
        const cz = Math.sin(orbitAngle) * c.orbitRadius;
        const cy = c.baseY + Math.sin(this.time * 1.8 + c.bobPhase) * 0.24;
        const spinY = this.time * c.spinSpeed;
        const tiltX = 0.28 * Math.sin(this.time * 0.9 + c.bobPhase);

        for (let t = 0; t < this.octaBase.length; t++) {
          const localTri = this.octaBase[t];
          const worldTri = localTri.map((v) => {
            const rx = rotatePointX(v, tiltX);
            const ry = rotatePointY(rx, spinY);
            return { x: ry.x + cx, y: ry.y + cy, z: ry.z + cz };
          });
          renderer.submitPolygon(worldTri, camera, {
            baseColor: c.palette.base,
            portalGlowColor: [180, 240, 255],
            stroke: c.palette.stroke,
            lineWidth: 1.0,
            ambient: 0.48,
            alpha: 0.92,
            portalCenter: PORTAL_CENTER,
            cullBackface: true
          });
        }
      }

      // Render portal core behind/within archway before foreground additive rings
      this._renderPortalCore(ctx, renderer, camera, portalScreen);

      // Flush depth-sorted solid faces
      renderer.flushPolygons();

      // 5. Counter-rotating 3D rings around the portal core
      this._renderPortalRings(ctx, renderer, camera);

      // 6. 110 rising particles
      this._renderParticles(ctx, renderer, camera);
    }

    _renderStars(renderer, camera) {
      const ctx = renderer.ctx;
      for (let i = 0; i < this.stars.length; i++) {
        const st = this.stars[i];
        const sp = camera.projectWorldPoint(st.pos, renderer.width, renderer.height);
        if (!sp) continue;
        if (sp.x < -10 || sp.x > renderer.width + 10 || sp.y < -10 || sp.y > renderer.height + 10) {
          continue;
        }
        const twinkle = 0.3 + 0.7 * (0.5 + 0.5 * Math.sin(this.time * st.speed + st.phase));
        ctx.globalAlpha = twinkle;
        ctx.fillStyle = st.hue;
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, st.size, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    }

    _renderCyberGrid(renderer, camera) {
      const extent = 12;
      const step = 1.5;
      for (let i = -extent; i <= extent; i += step) {
        const isMajor = Math.abs(i % 3) < 0.01;
        const color = isMajor ? 'rgba(0, 225, 255, 0.26)' : 'rgba(130, 80, 255, 0.14)';
        const lw = isMajor ? 1.2 : 0.8;
        renderer.drawLine3D({ x: i, y: 0, z: -extent }, { x: i, y: 0, z: extent }, camera, color, lw);
        renderer.drawLine3D({ x: -extent, y: 0, z: i }, { x: extent, y: 0, z: i }, camera, color, lw);
      }
    }

    _renderPortalCore(ctx, renderer, camera, portalScreen) {
      if (!portalScreen) return;
      const pulse = 1 + 0.06 * Math.sin(this.time * 3.4);
      const radiusX = 0.95 * portalScreen.scale * pulse;
      const radiusY = 1.48 * portalScreen.scale * pulse;
      if (radiusX <= 2 || radiusY <= 2) return;

      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      ctx.translate(portalScreen.x, portalScreen.y);

      // Aspect-aware elliptical portal energy core
      ctx.save();
      ctx.scale(1, radiusY / radiusX);

      const coreGrad = ctx.createRadialGradient(0, 0, 2, 0, 0, radiusX);
      coreGrad.addColorStop(0, 'rgba(240, 255, 255, 0.92)');
      coreGrad.addColorStop(0.25, 'rgba(72, 240, 255, 0.72)');
      coreGrad.addColorStop(0.62, 'rgba(175, 70, 255, 0.36)');
      coreGrad.addColorStop(1, 'rgba(40, 0, 110, 0)');

      ctx.fillStyle = coreGrad;
      ctx.beginPath();
      ctx.arc(0, 0, radiusX, 0, Math.PI * 2);
      ctx.fill();

      // Swirling energy filaments inside the core
      for (let k = 0; k < 3; k++) {
        const startA = this.time * (1.8 + k * 0.45) + k * ((Math.PI * 2) / 3);
        ctx.beginPath();
        ctx.arc(0, 0, radiusX * (0.42 + k * 0.16), startA, startA + Math.PI * 1.1);
        ctx.strokeStyle = k % 2 === 0 ? 'rgba(120, 250, 255, 0.55)' : 'rgba(225, 130, 255, 0.5)';
        ctx.lineWidth = Math.max(1.5, radiusX * 0.045);
        ctx.stroke();
      }

      ctx.restore();
      ctx.restore();
    }

    _renderPortalRings(ctx, renderer, camera) {
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';

      this._draw3DRing({
        renderer,
        camera,
        radius: 1.28,
        segments: 48,
        rotZ: this.time * 1.15,
        rotY: Math.sin(this.time * 0.5) * 0.25,
        rotX: 0.12,
        color: 'rgba(75, 245, 255, 0.85)',
        lineWidth: 2.4,
        dashedEvery: 4
      });

      this._draw3DRing({
        renderer,
        camera,
        radius: 1.56,
        segments: 56,
        rotZ: -this.time * 0.85,
        rotY: -Math.cos(this.time * 0.4) * 0.3,
        rotX: -0.18,
        color: 'rgba(215, 105, 255, 0.82)',
        lineWidth: 2.2,
        dashedEvery: 5
      });

      ctx.restore();
    }

    _draw3DRing(cfg) {
      const { renderer, camera, radius, segments, rotZ, rotY, rotX, color, lineWidth, dashedEvery } = cfg;
      const ctx = renderer.ctx;
      const pts = [];

      for (let i = 0; i <= segments; i++) {
        const a = (i / segments) * Math.PI * 2 + rotZ;
        let p = {
          x: Math.cos(a) * radius,
          y: Math.sin(a) * radius * 1.28,
          z: 0
        };
        p = rotatePointX(p, rotX);
        p = rotatePointY(p, rotY);
        p = Vec3.add(p, PORTAL_CENTER);
        pts.push(camera.projectWorldPoint(p, renderer.width, renderer.height));
      }

      ctx.strokeStyle = color;
      ctx.lineWidth = lineWidth;

      for (let i = 0; i < segments; i++) {
        if (dashedEvery && i % dashedEvery === 0) continue;
        const p1 = pts[i];
        const p2 = pts[i + 1];
        if (!p1 || !p2) continue;
        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.stroke();
      }
    }

    _renderParticles(ctx, renderer, camera) {
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';

      for (let i = 0; i < this.particles.length; i++) {
        const p = this.particles[i];
        const sp = camera.projectWorldPoint(p, renderer.width, renderer.height);
        if (!sp) continue;

        const life = Math.min(1, (p.y - 0.3) / 1.0) * Math.max(0, 1 - (p.y - (p.maxY - 1.2)) / 1.2);
        const alpha = Math.max(0, Math.min(0.95, life * 0.9));
        const r = Math.max(0.8, p.size * (sp.scale / 220));

        ctx.fillStyle = `rgba(${p.color[0]}, ${p.color[1]}, ${p.color[2]}, ${alpha})`;
        ctx.beginPath();
        ctx.arc(sp.x, sp.y, r, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.restore();
    }
  }

  global.NeonPortalScene = NeonPortalScene;
  global.SCENE_CONSTANTS = {
    STAR_COUNT,
    PARTICLE_COUNT,
    CRYSTAL_COUNT
  };
})(window);
