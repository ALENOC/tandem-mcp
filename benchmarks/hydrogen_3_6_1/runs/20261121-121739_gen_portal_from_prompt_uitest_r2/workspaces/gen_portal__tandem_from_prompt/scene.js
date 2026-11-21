// scene.js - builds the neon portal scene geometry and dynamic elements.
// Exposes Scene.build() which returns boxes, crystals, stars, particles, grid.

(function (global) {
  "use strict";

  const Scene = {};
  const E = global.Engine;

  // Palette
  const CYAN = { r: 0, g: 245, b: 255 };
  const MAGENTA = { r: 255, g: 42, b: 230 };

  // --- Static boxes: two-tier platform, twin pillars, lintel, crown cap.
  // 6 boxes x 6 faces = 36 box faces.
  function buildBoxes() {
    const boxes = [];
    // Lower tier platform
    boxes.push(E.makeBox(0, -3.0, 0, 6.0, 0.4, 6.0, { r: 28, g: 38, b: 70 }));
    // Upper tier platform
    boxes.push(E.makeBox(0, -2.45, 0, 4.4, 0.4, 4.4, { r: 40, g: 55, b: 95 }));
    // Twin pillars
    boxes.push(E.makeBox(-3.6, 0.2, 0, 0.5, 3.6, 0.5, { r: 52, g: 68, b: 115 }));
    boxes.push(E.makeBox(3.6, 0.2, 0, 0.5, 3.6, 0.5, { r: 52, g: 68, b: 115 }));
    // Lintel spanning the pillars
    boxes.push(E.makeBox(0, 3.7, 0, 4.3, 0.5, 0.6, { r: 64, g: 84, b: 135 }));
    // Crown cap on top
    boxes.push(E.makeBox(0, 4.3, 0, 4.7, 0.35, 0.95, { r: 86, g: 116, b: 175 }));
    return boxes;
  }

  // --- Six orbiting octahedral crystals. 6 x 8 faces = 48 triangles.
  // Geometry is built at the origin; each crystal carries orbit params and
  // is translated to its current position at render time.
  function buildCrystals() {
    const crystals = [];
    const n = 6;
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2;
      const col = (i % 2 === 0) ? CYAN : MAGENTA;
      crystals.push({
        baseAngle: a,
        radius: 7.2,
        height: 0.6 + (i % 3) * 0.5,
        speed: 0.5 + (i % 3) * 0.15,
        bob: i * 0.9,
        faces: E.makeOctahedron(0, 0, 0, 0.7, col)
      });
    }
    return crystals;
  }

  // --- 180 twinkling stars on a distant dome.
  function buildStars() {
    const stars = [];
    const n = 180;
    for (let i = 0; i < n; i++) {
      // Random direction on a sphere, biased toward the upper hemisphere.
      const u = Math.random();
      const v = Math.random();
      const theta = u * Math.PI * 2;
      const phi = Math.acos(2 * v - 1);
      const R = 60;
      stars.push({
        x: R * Math.sin(phi) * Math.cos(theta),
        y: R * Math.cos(phi) * 0.6 + 8,
        z: R * Math.sin(phi) * Math.sin(theta),
        size: 0.6 + Math.random() * 1.6,
        phase: Math.random() * Math.PI * 2,
        tw: 1.5 + Math.random() * 2.5
      });
    }
    return stars;
  }

  // --- 110 rising neon particles.
  function buildParticles() {
    const parts = [];
    const n = 110;
    for (let i = 0; i < n; i++) {
      parts.push({
        x: (Math.random() - 0.5) * 16,
        y: -3 + Math.random() * 12,
        z: (Math.random() - 0.5) * 16,
        vy: 0.4 + Math.random() * 0.9,
        size: 1 + Math.random() * 2.2,
        cyan: Math.random() < 0.5,
        phase: Math.random() * Math.PI * 2
      });
    }
    return parts;
  }

  // --- Perspective cyber grid floor: radial + concentric lines.
  function buildGrid() {
    const grid = {
      extent: 22,
      step: 2,
      y: -3.4,
      rings: 8
    };
    return grid;
  }

  Scene.build = function () {
    return {
      boxes: buildBoxes(),
      crystals: buildCrystals(),
      stars: buildStars(),
      particles: buildParticles(),
      grid: buildGrid(),
      CYAN: CYAN,
      MAGENTA: MAGENTA
    };
  };

  global.Scene = Scene;
})(typeof window !== "undefined" ? window : this);
