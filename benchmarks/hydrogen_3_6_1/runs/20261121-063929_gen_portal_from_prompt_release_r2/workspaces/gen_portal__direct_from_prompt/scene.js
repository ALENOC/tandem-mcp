(function (global) {
  "use strict";

  const E = global.Engine3D;

  function PortalScene() {
    this.time = 0;
    this.renderer = new E.Renderer3D();
    this.portalCenter = E.vec3(0, 2.35, 0);
    this.lightDir = E.normalize(E.vec3(0.55, 0.85, 0.65));

    // 1. Monument: Two-tier platform, twin pillars, lintel, crown cap (6 boxes * 6 faces = 36 box faces)
    this.boxFaces = [
      // Lower platform tier
      ...E.createBoxFaces(0, 0.16, 0, 5.2, 0.32, 3.2, {
        baseColor: [22, 28, 54],
        edgeColor: "rgba(94, 242, 255, 0.65)",
        emissive: 0.08,
      }),
      // Upper platform tier
      ...E.createBoxFaces(0, 0.44, 0, 3.8, 0.24, 2.2, {
        baseColor: [28, 34, 68],
        edgeColor: "rgba(94, 242, 255, 0.85)",
        emissive: 0.1,
      }),
      // Left pillar
      ...E.createBoxFaces(-1.35, 2.28, 0, 0.56, 3.44, 0.66, {
        baseColor: [24, 30, 62],
        edgeColor: "rgba(94, 242, 255, 0.82)",
        emissive: 0.1,
      }),
      // Right pillar
      ...E.createBoxFaces(1.35, 2.28, 0, 0.56, 3.44, 0.66, {
        baseColor: [24, 30, 62],
        edgeColor: "rgba(94, 242, 255, 0.82)",
        emissive: 0.1,
      }),
      // Lintel
      ...E.createBoxFaces(0, 4.24, 0, 3.7, 0.48, 0.84, {
        baseColor: [30, 34, 72],
        edgeColor: "rgba(255, 79, 216, 0.8)",
        emissive: 0.12,
      }),
      // Crown cap
      ...E.createBoxFaces(0, 4.64, 0, 2.25, 0.32, 0.62, {
        baseColor: [36, 38, 84],
        edgeColor: "rgba(94, 242, 255, 0.92)",
        emissive: 0.15,
      }),
    ];

    // 2. Six orbiting octahedral crystals (6 * 8 = 48 triangles)
    this.octaTemplate = E.createOctahedronFaces(0.24);
    this.crystals = [];
    for (let i = 0; i < 6; i++) {
      const isCyan = i % 2 === 0;
      this.crystals.push({
        angleOffset: (i / 6) * Math.PI * 2,
        orbitRadius: 2.7 + (i % 2) * 0.45,
        baseHeight: 1.7 + (i % 3) * 0.65,
        bobPhase: i * 1.1,
        spinSpeed: 1.2 + i * 0.18,
        baseColor: isCyan ? [45, 210, 255] : [255, 75, 215],
        edgeColor: isCyan ? "rgba(180, 252, 255, 0.92)" : "rgba(255, 180, 245, 0.92)",
      });
    }

    // 3. 180 twinkling stars
    this.stars = [];
    for (let i = 0; i < 180; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(Math.random() * 0.92 + 0.08); // mostly upper hemisphere & horizon
      const radius = 28 + Math.random() * 24;
      this.stars.push({
        pos: E.vec3(
          Math.sin(phi) * Math.cos(theta) * radius,
          Math.cos(phi) * radius - 2,
          Math.sin(phi) * Math.sin(theta) * radius
        ),
        size: 0.8 + Math.random() * 1.6,
        phase: Math.random() * Math.PI * 2,
        speed: 1.4 + Math.random() * 3.0,
        hue: Math.random() < 0.7 ? "210, 240, 255" : Math.random() < 0.5 ? "94, 242, 255" : "255, 130, 235",
      });
    }

    // 4. 110 rising particles
    this.particles = [];
    for (let i = 0; i < 110; i++) {
      this.particles.push(this.spawnParticle(true));
    }
  }

  PortalScene.prototype.spawnParticle = function (randomHeight) {
    const angle = Math.random() * Math.PI * 2;
    const rad = Math.random() * 2.1;
    return {
      x: Math.cos(angle) * rad,
      y: randomHeight ? 0.3 + Math.random() * 4.5 : 0.35 + Math.random() * 0.25,
      z: Math.sin(angle) * rad * 0.65,
      vy: 0.45 + Math.random() * 0.95,
      driftPhase: Math.random() * Math.PI * 2,
      driftAmp: 0.08 + Math.random() * 0.18,
      size: 0.03 + Math.random() * 0.055,
      maxY: 4.4 + Math.random() * 1.4,
      color: Math.random() < 0.55 ? "94, 242, 255" : "255, 79, 216",
    };
  };

  PortalScene.prototype.reset = function () {
    this.time = 0;
    this.particles.length = 0;
    for (let i = 0; i < 110; i++) {
      this.particles.push(this.spawnParticle(true));
    }
  };

  PortalScene.prototype.update = function (dt) {
    this.time += dt;
    for (let i = 0; i < this.particles.length; i++) {
      const p = this.particles[i];
      p.y += p.vy * dt;
      p.x += Math.sin(this.time * 2.1 + p.driftPhase) * p.driftAmp * dt;
      p.z += Math.cos(this.time * 1.7 + p.driftPhase) * p.driftAmp * dt;
      if (p.y > p.maxY) {
        this.particles[i] = this.spawnParticle(false);
      }
    }
  };

  PortalScene.prototype.drawBackground = function (ctx, w, h, cam, cx, cy) {
    const bg = ctx.createRadialGradient(cx, cy * 0.85, Math.min(w, h) * 0.05, cx, cy, Math.max(w, h) * 0.82);
    bg.addColorStop(0, "#120c33");
    bg.addColorStop(0.45, "#08051a");
    bg.addColorStop(1, "#020108");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, w, h);

    // Project 180 twinkling stars
    for (let i = 0; i < this.stars.length; i++) {
      const s = this.stars[i];
      const cs = E.worldToCamera(s.pos, cam);
      if (cs.z <= cam.near) continue;
      const ps = E.projectPoint(cs, cam, cx, cy);
      if (!ps || ps.x < -10 || ps.x > w + 10 || ps.y < -10 || ps.y > h + 10) continue;
      const twinkle = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(this.time * s.speed + s.phase));
      ctx.fillStyle = `rgba(${s.hue}, ${twinkle.toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(ps.x, ps.y, s.size, 0, Math.PI * 2);
      ctx.fill();
    }
  };

  PortalScene.prototype.addCyberGrid = function (cam, cx, cy) {
    const gridSize = 12;
    const step = 1.5;
    const y = 0;
    for (let i = -gridSize; i <= gridSize; i += step) {
      const edgeFade = 1 - Math.abs(i) / (gridSize + 2);
      const alpha = (0.14 + 0.22 * edgeFade).toFixed(3);
      const color = Math.abs(i) < 0.01 ? "rgba(255, 79, 216, 0.42)" : `rgba(94, 242, 255, ${alpha})`;
      this.renderer.addLine(E.vec3(i, y, -gridSize), E.vec3(i, y, gridSize), color, 1, cam, cx, cy, false);
      this.renderer.addLine(E.vec3(-gridSize, y, i), E.vec3(gridSize, y, i), color, 1, cam, cx, cy, false);
    }
  };

  PortalScene.prototype.addPortalCoreAndRings = function (cam, cx, cy) {
    const center = this.portalCenter;
    const pulse = 1 + 0.08 * Math.sin(this.time * 3.4);

    // Core volumetric glow layers
    this.renderer.addGlowSprite(
      center,
      1.65 * pulse,
      "rgba(120, 248, 255, 0.55)",
      "rgba(20, 90, 255, 0)",
      cam,
      cx,
      cy,
      0.1
    );
    this.renderer.addGlowSprite(
      center,
      0.95 * pulse,
      "rgba(255, 110, 235, 0.72)",
      "rgba(255, 79, 216, 0)",
      cam,
      cx,
      cy,
      0.05
    );
    this.renderer.addGlowSprite(
      center,
      0.42 * pulse,
      "rgba(255, 255, 255, 0.95)",
      "rgba(94, 242, 255, 0)",
      cam,
      cx,
      cy,
      0
    );

    // Swirling energy core facets (double-sided translucent portal disc)
    const segs = 16;
    const innerR = 0.86 * pulse;
    for (let i = 0; i < segs; i++) {
      const a0 = (i / segs) * Math.PI * 2 + this.time * 0.9;
      const a1 = ((i + 1) / segs) * Math.PI * 2 + this.time * 0.9;
      const p0 = center;
      const p1 = E.vec3(center.x + Math.cos(a0) * innerR, center.y + Math.sin(a0) * innerR, center.z);
      const p2 = E.vec3(center.x + Math.cos(a1) * innerR, center.y + Math.sin(a1) * innerR, center.z);
      const isEven = i % 2 === 0;
      this.renderer.addPoly(
        [p0, p1, p2],
        {
          baseColor: isEven ? [45, 225, 255] : [225, 65, 235],
          edgeColor: "rgba(255, 255, 255, 0.16)",
          emissive: 0.75,
          alpha: 0.28,
          doubleSided: true,
          additive: true,
        },
        cam,
        cx,
        cy,
        this.lightDir,
        null
      );
    }

    // Two counter-rotating 3D rings
    this.addRing(1.06, 0.075, 24, this.time * 1.25, 0.32, Math.sin(this.time * 0.8) * 0.25, [70, 245, 255], "rgba(190, 255, 255, 0.9)", cam, cx, cy);
    this.addRing(1.28, 0.065, 24, -this.time * 0.95, -0.38, Math.cos(this.time * 0.7) * 0.28, [255, 80, 220], "rgba(255, 195, 248, 0.9)", cam, cx, cy);
  };

  PortalScene.prototype.addRing = function (radius, thickness, segments, spinZ, tiltX, tiltY, baseColor, edgeColor, cam, cx, cy) {
    const c = this.portalCenter;
    for (let i = 0; i < segments; i++) {
      const a0 = (i / segments) * Math.PI * 2 + spinZ;
      const a1 = ((i + 1) / segments) * Math.PI * 2 + spinZ;
      const rIn = radius - thickness;
      const rOut = radius + thickness;

      const local = [
        E.vec3(Math.cos(a0) * rIn, Math.sin(a0) * rIn, 0),
        E.vec3(Math.cos(a0) * rOut, Math.sin(a0) * rOut, 0),
        E.vec3(Math.cos(a1) * rOut, Math.sin(a1) * rOut, 0),
        E.vec3(Math.cos(a1) * rIn, Math.sin(a1) * rIn, 0),
      ].map((v) => {
        let p = E.rotateX(v, tiltX);
        p = E.rotateY(p, tiltY);
        return E.add(p, c);
      });

      this.renderer.addPoly(
        local,
        {
          baseColor,
          edgeColor,
          emissive: 0.75,
          alpha: 0.88,
          doubleSided: true,
        },
        cam,
        cx,
        cy,
        this.lightDir,
        null
      );
    }
  };

  PortalScene.prototype.render = function (ctx, w, h, cam) {
    const cx = w * 0.5;
    const cy = h * 0.54;

    this.drawBackground(ctx, w, h, cam, cx, cy);
    this.renderer.clear();

    // Cyber grid floor
    this.addCyberGrid(cam, cx, cy);

    // Monument (36 box faces)
    for (let i = 0; i < this.boxFaces.length; i++) {
      const f = this.boxFaces[i];
      this.renderer.addPoly(f.verts, f, cam, cx, cy, this.lightDir, this.portalCenter);
    }

    // Portal core + 2 counter-rotating rings
    this.addPortalCoreAndRings(cam, cx, cy);

    // 6 orbiting octahedral crystals (48 triangles)
    for (let i = 0; i < this.crystals.length; i++) {
      const cr = this.crystals[i];
      const orbitAngle = this.time * 0.55 + cr.angleOffset;
      const pos = E.vec3(
        Math.cos(orbitAngle) * cr.orbitRadius,
        cr.baseHeight + Math.sin(this.time * 2.2 + cr.bobPhase) * 0.24,
        Math.sin(orbitAngle) * cr.orbitRadius
      );
      const spin = this.time * cr.spinSpeed;
      for (let t = 0; t < this.octaTemplate.length; t++) {
        const tri = this.octaTemplate[t].map((v) => {
          let p = E.rotateY(v, spin);
          p = E.rotateX(p, spin * 0.5);
          return E.add(p, pos);
        });
        this.renderer.addPoly(
          tri,
          {
            baseColor: cr.baseColor,
            edgeColor: cr.edgeColor,
            emissive: 0.45,
          },
          cam,
          cx,
          cy,
          this.lightDir,
          this.portalCenter
        );
      }
    }

    // 110 rising particles
    for (let i = 0; i < this.particles.length; i++) {
      const p = this.particles[i];
      const lifeFade = Math.sin(E.clamp((p.y - 0.3) / (p.maxY - 0.3), 0, 1) * Math.PI);
      const alpha = (0.35 + 0.65 * lifeFade).toFixed(3);
      this.renderer.addGlowSprite(
        E.vec3(p.x, p.y, p.z),
        p.size * 3.4,
        `rgba(${p.color}, ${alpha})`,
        `rgba(${p.color}, 0)`,
        cam,
        cx,
        cy,
        0
      );
    }

    this.renderer.flush(ctx);

    return {
      polys: this.renderer.polyCount,
      parts: this.particles.length,
    };
  };

  global.PortalScene = PortalScene;
})(window);
