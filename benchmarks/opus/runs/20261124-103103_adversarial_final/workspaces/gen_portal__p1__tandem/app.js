/* app.js - wires the scene to the canvas, runs the requestAnimationFrame
 * loop, drives the orbiting camera, and exposes window.app plus the HUD.
 */
(function (global) {
  'use strict';
  var E = global.Engine3D;
  var scene = global.Scene;

  var canvas = document.getElementById('c');
  var ctx = canvas.getContext('2d');

  var fpsEl = document.getElementById('fps');
  var polysEl = document.getElementById('polys');
  var partsEl = document.getElementById('parts');
  var pauseBtn = document.getElementById('pause');
  var orbitBtn = document.getElementById('orbit');
  var resetBtn = document.getElementById('reset');
  var speedEl = document.getElementById('speed');

  // ---- build the scene once --------------------------------------------
  scene.buildStructure();
  scene.buildCrystals();
  scene.buildStars();
  scene.buildParticles();

  // ---- app state -------------------------------------------------------
  var app = {
    paused: false,
    orbit: true,
    speed: 1,
    time: 0,
    camAngle: 0,
    stars: scene.stars,
    particles: scene.particles,
    crystals: scene.crystals,
    boxFaces: scene.boxCount,   // 36
    crystalTris: scene.crystalTris, // 48
    polys: 0
  };
  global.app = app;

  // ---- canvas sizing (devicePixelRatio aware) --------------------------
  var W = 0, H = 0, DPR = 1;
  function resize() {
    DPR = global.devicePixelRatio || 1;
    W = global.innerWidth;
    H = global.innerHeight;
    canvas.width = Math.floor(W * DPR);
    canvas.height = Math.floor(H * DPR);
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  }
  global.addEventListener('resize', resize);
  resize();

  // ---- camera ----------------------------------------------------------
  var CAM_RADIUS = 13;
  var CAM_TARGET = [0, 3.2, 0];
  function camera() {
    var a = app.camAngle;
    var bob = Math.sin(app.time * 0.7) * 0.6;
    var eye = [
      Math.sin(a) * CAM_RADIUS,
      4.5 + bob,
      Math.cos(a) * CAM_RADIUS
    ];
    return E.makeCamera(eye, CAM_TARGET, [0, 1, 0], 0.9, W, H);
  }

  var LIGHT_DIR = E.normalize([0.4, 0.9, 0.5]);

  // ---- HUD -------------------------------------------------------------
  var fpsAccum = 0, fpsFrames = 0, fpsValue = 0;
  function updateHud(dt) {
    fpsAccum += dt;
    fpsFrames++;
    if (fpsAccum >= 0.5) {
      fpsValue = Math.round(fpsFrames / fpsAccum);
      fpsAccum = 0;
      fpsFrames = 0;
    }
    fpsEl.textContent = 'FPS: ' + fpsValue;
    polysEl.textContent = 'POLYS: ' + app.polys;
    partsEl.textContent = 'PARTS: ' + app.particles.length;
  }

  // ---- main loop -------------------------------------------------------
  var last = global.performance.now();
  function frame(now) {
    var rawDt = (now - last) / 1000;
    last = now;
    if (rawDt < 0) rawDt = 0;
    if (rawDt > 0.1) rawDt = 0.1;

    if (!app.paused) {
      var dt = rawDt * app.speed;
      app.time += dt;
      if (app.orbit) app.camAngle += dt * 0.35;
      scene.updateParticles(dt);
    }

    var cam = camera();

    scene.drawBackground(ctx, W, H);
    scene.drawStars(ctx, cam, app.time);
    scene.drawGrid(ctx, cam);

    // 3D geometry: static boxes + orbiting crystals, depth sorted together
    var polys = scene.boxFaces.slice();
    var cpolys = scene.crystalPolys(app.time);
    for (var i = 0; i < cpolys.length; i++) polys.push(cpolys[i]);
    app.polys = E.drawPolys(ctx, cam, polys, LIGHT_DIR);

    scene.drawPortal(ctx, cam, app.time);
    scene.drawParticles(ctx, cam, app.time);

    updateHud(rawDt);
    global.requestAnimationFrame(frame);
  }
  global.requestAnimationFrame(frame);

  // ---- controls --------------------------------------------------------
  pauseBtn.addEventListener('click', function () {
    app.paused = !app.paused;
    pauseBtn.textContent = app.paused ? 'Resume' : 'Pause';
  });

  orbitBtn.addEventListener('click', function () {
    app.orbit = !app.orbit;
    orbitBtn.textContent = app.orbit ? 'Orbit ON' : 'Orbit OFF';
  });

  resetBtn.addEventListener('click', function () {
    app.paused = false;
    app.orbit = true;
    app.speed = 1;
    app.time = 0;
    app.camAngle = 0;
    pauseBtn.textContent = 'Pause';
    orbitBtn.textContent = 'Orbit ON';
    speedEl.value = '1';
  });

  speedEl.addEventListener('input', function () {
    app.speed = parseFloat(speedEl.value);
    if (isNaN(app.speed)) app.speed = 1;
  });
})(window);
