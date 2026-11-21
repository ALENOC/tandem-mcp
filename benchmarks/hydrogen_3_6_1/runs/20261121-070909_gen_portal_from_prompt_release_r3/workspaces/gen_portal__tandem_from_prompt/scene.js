/* scene.js - builds the portal monument, crystals, rings, grid, stars, particles */
(function (global) {
  "use strict";
  var E = global.Engine;
  var TAU = E.TAU;

  // ---- static portal monument: 6 boxes = 36 faces ----
  // Two-tier platform (2), twin pillars (2), lintel (1), crown cap (1).
  function buildMonument() {
    var boxes = [];
    // lower platform tier
    boxes.push(E.makeBox(0, 0.25, 0, 3.4, 0.25, 3.4));
    // upper platform tier
    boxes.push(E.makeBox(0, 0.62, 0, 2.6, 0.22, 2.6));
    // twin pillars
    boxes.push(E.makeBox(-2.1, 2.4, 0, 0.35, 1.8, 0.35));
    boxes.push(E.makeBox(2.1, 2.4, 0, 0.35, 1.8, 0.35));
    // lintel across the top of the pillars
    boxes.push(E.makeBox(0, 4.35, 0, 2.5, 0.35, 0.5));
    // crown cap on top
    boxes.push(E.makeBox(0, 4.78, 0, 1.7, 0.28, 0.7));
    return boxes;
  }

  // ---- 6 orbiting octahedral crystals (each 8 faces = 48 total) ----
  function makeCrystals() {
    var arr = [];
    for (var i = 0; i < 6; i++) {
      arr.push({
        phase: (i / 6) * TAU,
        radius: 4.6,
        height: 2.6 + (i % 3) * 0.5,
        spin: 0.9 + i * 0.12,
        r: 0.42
      });
    }
    return arr;
  }

  // ---- two counter-rotating 3D rings built from small box segments ----
  function makeRings() {
    var rings = [];
    var SEG = 22;
    for (var i = 0; i < 2; i++) {
      var segs = [];
      for (var s = 0; s < SEG; s++) {
        segs.push((s / SEG) * TAU);
      }
      rings.push({
        segs: segs,
        radius: 1.5 + i * 0.35,
        tilt: i * 0.9,
        dir: i === 0 ? 1 : -1,
        speed: 1.1 + i * 0.4,
        cy: 2.6
      });
    }
    return rings;
  }

  // ---- 180 twinkling stars on a large sphere ----
  function makeStars() {
    var arr = [];
    for (var i = 0; i < 180; i++) {
      // random point on a sphere
      var u = Math.random() * 2 - 1;
      var th = Math.random() * TAU;
      var s = Math.sqrt(1 - u * u);
      var R = 70;
      arr.push({
        x: s * Math.cos(th) * R,
        y: u * R,
        z: s * Math.sin(th) * R,
        tw: Math.random() * TAU,
        sp: 1 + Math.random() * 3,
        sz: 0.6 + Math.random() * 1.6
      });
    }
    return arr;
  }

  // ---- 110 rising neon particles with lifecycle recycling ----
  function makeParticles() {
    var arr = [];
    for (var i = 0; i < 110; i++) {
      arr.push(spawnParticle(true));
    }
    return arr;
  }
  function spawnParticle(anywhere) {
    var a = Math.random() * TAU;
    var rr = Math.random() * 3.2;
    return {
      x: Math.cos(a) * rr,
      y: anywhere ? Math.random() * 6 : -0.2,
      z: Math.sin(a) * rr,
      vy: 0.4 + Math.random() * 0.9,
      life: anywhere ? Math.random() : 1,
      hue: Math.random() < 0.5 ? 0 : 1,
      sz: 1.5 + Math.random() * 2.5
    };
  }

  global.Scene = {
    buildMonument: buildMonument,
    makeCrystals: makeCrystals,
    makeRings: makeRings,
    makeStars: makeStars,
    makeParticles: makeParticles,
    spawnParticle: spawnParticle
  };
})(typeof window !== "undefined" ? window : this);
