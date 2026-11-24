// scene.js
// Builds the neon portal scene: two-tier platform, twin pillars, lintel,
// crown cap (6 boxes), six orbiting octahedral crystals, portal core,
// cyber grid floor, twinkling stars and rising particles.

(function (global) {
  'use strict';

  const E = global.Engine3D;

  // ---------- constants ----------
  const BOX_COUNT = 6;          // 6 boxes x 6 faces = 36 box faces
  const CRYSTAL_COUNT = 6;      // 6 crystals x 8 tris = 48 crystal tris
  const STAR_COUNT = 180;
  const PARTICLE_COUNT = 110;

  // Portal center (between the pillars, above the platform).
  const PORTAL = { x: 0, y: 3.2, z: 0 };

  // ---------- boxes ----------
  // Each box: { faces (6 quads), base color, edge color }.
  function buildBoxes() {
    const boxes = [];
    const add = function (cx, cy, cz, hx, hy, hz, base, edge) {
      const faces = E.makeBox(cx, cy, cz, hx, hy, hz);
      boxes.push({ faces: faces, base: base, edge: edge });
    };

    // 1) Lower wide platform box.
    add(0, 0.4, 0, 4.2, 0.4, 4.2, { r: 40, g: 30, b: 90 }, 'rgba(120,80,255,0.9)');
    // 2) Upper narrower platform box.
    add(0, 1.0, 0, 2.6, 0.35, 2.6, { r: 55, g: 40, b: 120 }, 'rgba(150,100,255,0.9)');
    // 3) Left pillar.
    add(-2.2, 2.6, 0, 0.35, 1.6, 0.35, { r: 45, g: 35, b: 100 }, 'rgba(0,240,255,0.9)');
    // 4) Right pillar.
    add(2.2, 2.6, 0, 0.35, 1.6, 0.35, { r: 45, g: 35, b: 100 }, 'rgba(0,240,255,0.9)');
    // 5) Lintel across the pillar tops (sits on top of pillars at y=4.2).
    add(0, 4.5, 0, 2.6, 0.3, 0.4, { r: 50, g: 40, b: 110 }, 'rgba(255,43,214,0.9)');
    // 6) Crown cap on the lintel (sits on top of lintel at y=4.8).
    add(0, 4.95, 0, 1.4, 0.25, 0.5, { r: 60, g: 45, b: 130 }, 'rgba(255,43,214,0.9)');

    return boxes;
  }

  // ---------- crystals ----------
  // Six octahedra orbiting the portal. Each spins on its own axis and bobs.
  function buildCrystals() {
    const crystals = [];
    const base = E.makeOctahedron(0.55);
    for (let i = 0; i < CRYSTAL_COUNT; i++) {
      crystals.push({
        base: base,
        orbitRadius: 3.4,
        orbitSpeed: 0.6 + i * 0.05,
        orbitPhase: (i / CRYSTAL_COUNT) * Math.PI * 2,
        spinAxis: { x: Math.sin(i), y: 1, z: Math.cos(i * 1.3) },
        spinSpeed: 1.2 + i * 0.2,
        bobPhase: i * 0.9,
        bobAmp: 0.35,
        baseColor: { r: 120, g: 60, b: 220 },
        edge: 'rgba(0,240,255,0.95)'
      });
    }
    return crystals;
  }

  // ---------- stars ----------
  // 180 twinkling stars on a large sphere shell behind the scene.
  function buildStars() {
    const stars = [];
    for (let i = 0; i < STAR_COUNT; i++) {
      // Fibonacci-ish spread on a sphere.
      const t = i / STAR_COUNT;
      const phi = Math.acos(1 - 2 * (i + 0.5) / STAR_COUNT);
      const theta = Math.PI * (1 + Math.sqrt(5)) * i;
      const R = 60;
      stars.push({
        x: R * Math.sin(phi) * Math.cos(theta),
        y: R * Math.cos(phi) * 0.6 + 8,
        z: R * Math.sin(phi) * Math.sin(theta),
        phase: i * 0.7,
        size: 0.6 + (i % 3) * 0.4
      });
    }
    return stars;
  }

  // ---------- particles ----------
  // 110 rising particles from the portal/platform.
  function buildParticles() {
    const particles = [];
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      particles.push({
        x: (Math.random() - 0.5) * 5,
        y: Math.random() * 4,
        z: (Math.random() - 0.5) * 5,
        vy: 0.4 + Math.random() * 0.8,
        life: Math.random(),
        hue: Math.random() < 0.5 ? 'cyan' : 'magenta'
      });
    }
    return particles;
  }

  // ---------- grid ----------
  // Cyber grid floor: neon cyan lines on the ground plane.
  function buildGrid() {
    const grid = {
      size: 24,      // half-extent of the grid
      step: 1.2,
      y: 0.02
    };
    return grid;
  }

  // ---------- scene factory ----------
  function createScene() {
    return {
      boxes: buildBoxes(),
      crystals: buildCrystals(),
      stars: buildStars(),
      particles: buildParticles(),
      grid: buildGrid(),
      portal: {
        center: { x: PORTAL.x, y: PORTAL.y, z: PORTAL.z },
        radius: 1.5,
        ringSegments: 48
      },
      counts: {
        boxFaces: BOX_COUNT * 6,
        crystalTris: CRYSTAL_COUNT * 8,
        stars: STAR_COUNT,
        particles: PARTICLE_COUNT
      }
    };
  }

  global.Scene = {
    createScene: createScene,
    PORTAL: PORTAL,
    STAR_COUNT: STAR_COUNT,
    PARTICLE_COUNT: PARTICLE_COUNT
  };
})(window);
