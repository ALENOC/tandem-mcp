// scene.js - scene content: boxes, crystals, portal, grid, stars, particles.
// Depends on window.Engine3D.

(function (global) {
  "use strict";
  var E = global.Engine3D;

  // ---- static box definitions ----------------------------------------------
  // Each box: center (cx,cy,cz), size (sx,sy,sz), face color, edge color.
  // 6 boxes total -> 36 box faces.
  var BOXES = [
    // two-tier platform
    { c: [0, 0.2, 0], s: [6, 0.4, 4], face: "#0b1030", edge: "#00e5ff" },   // lower wide
    { c: [0, 0.6, 0], s: [4.4, 0.4, 2.8], face: "#0b1030", edge: "#00e5ff" }, // upper
    // twin pillars standing on the upper tier (top of upper tier at y=0.8)
    { c: [-1.6, 2.0, 0], s: [0.5, 2.4, 0.5], face: "#0b1030", edge: "#ff2bd6" }, // left
    { c: [1.6, 2.0, 0], s: [0.5, 2.4, 0.5], face: "#0b1030", edge: "#ff2bd6" },  // right
    // lintel spanning across the top of both pillars (pillar top at y=3.2)
    { c: [0, 3.4, 0], s: [4.0, 0.5, 0.6], face: "#0b1030", edge: "#ff2bd6" },
    // crown cap on top of the lintel (lintel top at y=3.65)
    { c: [0, 3.85, 0], s: [2.6, 0.4, 0.5], face: "#0b1030", edge: "#ff2bd6" }
  ];

  // ---- crystals ------------------------------------------------------------
  // Six octahedral crystals orbiting the portal on a circle.
  var CRYSTAL_COLORS = ["#00e5ff", "#ff2bd6", "#ffe600"];
  var CRYSTALS = [];
  for (var i = 0; i < 6; i++) {
    CRYSTALS.push({
      baseAngle: (i / 6) * Math.PI * 2,
      radius: 2.6,
      y: 2.0,
      spin: 1.2 + i * 0.15,
      size: 0.32,
      color: CRYSTAL_COLORS[i % 3]
    });
  }

  // ---- stars ---------------------------------------------------------------
  // Exactly 180 twinkling stars with random screen positions and phases.
  var STARS = [];
  for (var s = 0; s < 180; s++) {
    STARS.push({
      x: Math.random(),
      y: Math.random(),
      r: 0.5 + Math.random() * 1.4,
      phase: Math.random() * Math.PI * 2,
      speed: 0.6 + Math.random() * 1.6
    });
  }

  // ---- particles -----------------------------------------------------------
  // Exactly 110 rising particles around the portal.
  var PARTICLES = [];
  for (var p = 0; p < 110; p++) {
    PARTICLES.push(makeParticle(true));
  }
  function makeParticle(randomY) {
    var ang = Math.random() * Math.PI * 2;
    var rad = 0.4 + Math.random() * 1.6;
    return {
      x: Math.cos(ang) * rad,
      y: randomY ? 0.8 + Math.random() * 3.0 : 0.8,
      z: Math.sin(ang) * rad,
      vy: 0.4 + Math.random() * 0.7,
      life: randomY ? Math.random() : 0,
      size: 1.5 + Math.random() * 2.5,
      hue: Math.random() < 0.5 ? "#00e5ff" : "#ff2bd6"
    };
  }

  // ---- grid ----------------------------------------------------------------
  // Cyber grid floor on the y=0 plane below the platform.
  var GRID = {
    extent: 22,      // half-extent in world units
    step: 1.0,       // spacing between lines
    color: "#7a2cff",
    alpha: 0.5,
    scroll: 0.0
  };

  // ---- portal core ---------------------------------------------------------
  var PORTAL = {
    x: 0, y: 2.0, z: 0,
    radius: 1.15
  };

  // ---- rings ---------------------------------------------------------------
  // Two concentric rings around the portal core, counter-rotating.
  var RINGS = [
    { radius: 1.5, segments: 48, speed: 0.9, color: "#00e5ff", tilt: 0.0 },
    { radius: 1.9, segments: 48, speed: -0.6, color: "#ff2bd6", tilt: 0.0 }
  ];

  global.Scene = {
    BOXES: BOXES,
    CRYSTALS: CRYSTALS,
    STARS: STARS,
    PARTICLES: PARTICLES,
    GRID: GRID,
    PORTAL: PORTAL,
    RINGS: RINGS,
    makeParticle: makeParticle
  };
})(window);
