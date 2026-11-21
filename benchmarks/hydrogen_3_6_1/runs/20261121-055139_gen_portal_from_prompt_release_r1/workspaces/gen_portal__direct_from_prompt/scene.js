(function (global) {
  'use strict';

  const { makeBoxFaces, makeOctahedronFaces } = global.Engine3D;

  const STAR_COUNT = 180;
  const PARTICLE_COUNT = 110;
  const CRYSTAL_COUNT = 6;
  const FLOOR_Y = -2.0;

  class NeonPortalScene {
    constructor() {
      this.time = 0;
      this.stars = this.createStars();
      this.particles = this.createParticles();
      this.monumentFaces = this.createMonumentBoxes();
      this.polyCount = 0;
      this.partCount = PARTICLE_COUNT;
    }

    createStars() {
      const stars = [];
      for (let i = 0; i < STAR_COUNT; i++) {
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos(2 * Math.random() - 1);
        const radius = 24 + Math.random() * 20;
        stars.push({
          x: radius * Math.sin(phi) * Math.cos(theta),
          y: Math.abs(radius * Math.cos(phi)) * 0.85 - 1.5,
          z: radius * Math.sin(phi) * Math.sin(theta),
          size: 0.8 + Math.random() * 1.6,
          phase: Math.random() * Math.PI * 2,
          speed: 1.2 + Math.random() * 2.5,
          color: i % 5 === 0 ? '#7df3ff' : i % 7 === 0 ? '#e396ff' : '#ffffff'
        });
      }
      return stars;
    }

    createParticles() {
      const parts = [];
      for (let i = 0; i < PARTICLE_COUNT; i++) {
        parts.push(this.spawnParticle(true));
      }
      return parts;
    }

    spawnParticle(randomHeight = false) {
      const angle = Math.random() * Math.PI * 2;
      const dist = 0.25 + Math.random() * 2.6;
      return {
        x: Math.cos(angle) * dist,
        y: randomHeight ? FLOOR_Y + Math.random() * 5.2 : FLOOR_Y + Math.random() * 0.3,
        z: Math.sin(angle) * dist,
        vy: 0.45 + Math.random() * 0.85,
        swirl: (Math.random() - 0.5) * 0.9,
        size: 1.0 + Math.random() * 1.8,
        color: Math.random() > 0.45 ? '#5ef2ff' : '#e066ff'
      };
    }

    createMonumentBoxes() {
      // 6 boxes * 6 faces = 36 box faces
      const slate = [34, 42, 78];
      const darkSlate = [24, 30, 58];
      const cyanEdge = 'rgba(94, 242, 255, 0.72)';
      const violetEdge = 'rgba(199, 125, 255, 0.78)';

      const boxes = [
        // 1. Lower platform tier
        ...makeBoxFaces(0, -1.82, 0, 5.2, 0.36, 3.8, darkSlate, cyanEdge),
        // 2. Upper platform tier
        ...makeBoxFaces(0, -1.48, 0, 4.1, 0.32, 2.7, slate, cyanEdge),
        // 3. Left pillar
        ...makeBoxFaces(-1.45, 0.33, 0, 0.56, 3.3, 0.62, slate, cyanEdge),
        // 4. Right pillar
        ...makeBoxFaces(1.45, 0.33, 0, 0.56, 3.3, 0.62, slate, cyanEdge),
        // 5. Lintel
        ...makeBoxFaces(0, 2.18, 0, 3.86, 0.44, 0.82, darkSlate, violetEdge),
        // 6. Crown cap
        ...makeBoxFaces(0, 2.54, 0, 2.3, 0.28, 0.6, slate, cyanEdge)
      ];

      return boxes;
    }

    update(dt, speed) {
      const scaledDt = dt * speed;
      this.time += scaledDt;

      for (let i = 0; i < this.particles.length; i++) {
        const p = this.particles[i];
        p.y += p.vy * scaledDt;
        const angle = p.swirl * scaledDt;
        const c = Math.cos(angle);
        const s = Math.sin(angle);
        const nx = p.x * c - p.z * s;
        const nz = p.x * s + p.z * c;
        p.x = nx;
        p.z = nz;

        if (p.y > 3.2) {
          this.particles[i] = this.spawnParticle(false);
        }
      }
    }

    render(renderer, camera, width, height) {
      renderer.beginFrame(width, height);

      // 1. 180 twinkling stars (background)
      const ctx = renderer.ctx;
      for (let i = 0; i < this.stars.length; i++) {
        const s = this.stars[i];
        const proj = camera.project(s, width, height);
        if (!proj) continue;
        const twinkle = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(this.time * s.speed + s.phase));
        ctx.save();
        ctx.globalAlpha = twinkle;
        ctx.fillStyle = s.color;
        ctx.beginPath();
        ctx.arc(proj.x, proj.y, s.size, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }

      // 2. Cyber grid floor
      const gridExtent = 9;
      const gridStep = 1;
      for (let i = -gridExtent; i <= gridExtent; i += gridStep) {
        const isMajor = i % 3 === 0;
        const color = isMajor ? '#3fe6ff' : '#2a4678';
        const alpha = isMajor ? 0.38 : 0.2;
        renderer.pushLine(
          camera,
          { x: i, y: FLOOR_Y, z: -gridExtent },
          { x: i, y: FLOOR_Y, z: gridExtent },
          color,
          isMajor ? 1.2 : 0.8,
          alpha
        );
        renderer.pushLine(
          camera,
          { x: -gridExtent, y: FLOOR_Y, z: i },
          { x: gridExtent, y: FLOOR_Y, z: i },
          color,
          isMajor ? 1.2 : 0.8,
          alpha
        );
      }

      // 3. Portal core (glowing energy disc)
      const coreCenter = { x: 0, y: 0.35, z: 0 };
      const coreProj = camera.project(coreCenter, width, height);
      if (coreProj) {
        const pulse = 1 + 0.06 * Math.sin(this.time * 3.1);
        const rx = 1.05 * coreProj.scale * pulse;
        const ry = 1.48 * coreProj.scale * pulse;
        renderer.pushCustom(coreProj.z + 0.05, (c) => {
          c.save();
          c.translate(coreProj.x, coreProj.y);
          c.scale(1, ry / Math.max(1, rx));
          const grad = c.createRadialGradient(0, 0, rx * 0.08, 0, 0, rx);
          grad.addColorStop(0, 'rgba(235, 252, 255, 0.92)');
          grad.addColorStop(0.32, 'rgba(94, 242, 255, 0.65)');
          grad.addColorStop(0.68, 'rgba(182, 84, 255, 0.35)');
          grad.addColorStop(1, 'rgba(94, 242, 255, 0)');
          c.fillStyle = grad;
          c.beginPath();
          c.arc(0, 0, rx, 0, Math.PI * 2);
          c.fill();
          c.restore();
        });
      }

      // 4. Two counter-rotating portal rings
      this.pushPortalRing(renderer, camera, 1.02, this.time * 1.4, 0.25, '#5ef2ff', 2.2);
      this.pushPortalRing(renderer, camera, 0.78, -this.time * 2.1, -0.35, '#e066ff', 1.9);

      // 5. Monument boxes (36 box faces)
      let polyCount = 0;
      for (let i = 0; i < this.monumentFaces.length; i++) {
        renderer.pushPolygon(camera, this.monumentFaces[i], true);
        polyCount++;
      }

      // 6. Six orbiting octahedral crystals (48 triangles)
      for (let i = 0; i < CRYSTAL_COUNT; i++) {
        const orbitAngle = (i / CRYSTAL_COUNT) * Math.PI * 2 + this.time * 0.65;
        const orbitRadius = 3.05;
        const cx = Math.cos(orbitAngle) * orbitRadius;
        const cz = Math.sin(orbitAngle) * orbitRadius;
        const cy = 0.45 + Math.sin(this.time * 2.2 + i * 1.1) * 0.32;

        const isCyan = i % 2 === 0;
        const color = isCyan ? [60, 225, 255] : [205, 95, 255];
        const edge = isCyan ? 'rgba(170, 250, 255, 0.9)' : 'rgba(240, 175, 255, 0.9)';

        const crystalFaces = makeOctahedronFaces(
          cx,
          cy,
          cz,
          0.24,
          0.42,
          0.24,
          this.time * 1.5 + i,
          Math.sin(this.time + i) * 0.3,
          color,
          edge
        );
        for (let f = 0; f < crystalFaces.length; f++) {
          renderer.pushPolygon(camera, crystalFaces[f], true);
          polyCount++;
        }
      }

      // 7. 110 rising particles
      for (let i = 0; i < this.particles.length; i++) {
        const p = this.particles[i];
        const fade = Math.max(0, Math.min(1, 1 - (p.y - FLOOR_Y) / 5.2));
        renderer.pushPoint(camera, p, p.size, p.color, fade * 0.85, false);
      }

      renderer.flush();
      this.polyCount = polyCount;
    }

    pushPortalRing(renderer, camera, radius, spinZ, tiltY, color, lineWidth) {
      const segments = 28;
      const cy = 0.35;
      const cosT = Math.cos(tiltY);
      const sinT = Math.sin(tiltY);

      let prev = null;
      let first = null;
      for (let i = 0; i < segments; i++) {
        const a = (i / segments) * Math.PI * 2 + spinZ;
        const lx = Math.cos(a) * radius;
        const ly = Math.sin(a) * radius * 1.25;
        const pt = {
          x: lx * cosT,
          y: cy + ly,
          z: lx * sinT
        };
        if (prev) {
          renderer.pushLine(camera, prev, pt, color, lineWidth, 0.9);
        } else {
          first = pt;
        }
        prev = pt;
      }
      if (prev && first) {
        renderer.pushLine(camera, prev, first, color, lineWidth, 0.9);
      }
    }
  }

  global.NeonPortalScene = NeonPortalScene;
})(window);
