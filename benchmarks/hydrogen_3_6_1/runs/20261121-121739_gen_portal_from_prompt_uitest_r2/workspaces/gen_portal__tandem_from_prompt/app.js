// app.js - main application: canvas setup, camera, render loop, HUD, controls.
(function (global) {
  "use strict";

  var canvas = document.getElementById("c");
  var ctx = canvas.getContext("2d");
  var W = 0, H = 0;

  var fpsEl = document.getElementById("fps");
  var polysEl = document.getElementById("polys");
  var partsEl = document.getElementById("parts");
  var btnPause = document.getElementById("btn-pause");
  var btnOrbit = document.getElementById("btn-orbit");
  var btnReset = document.getElementById("btn-reset");
  var speedEl = document.getElementById("speed");
  var speedVal = document.getElementById("speed-val");

  var scene = Scene.build();
  var cam = Engine.makeCamera();

  var DEFAULT = { yaw: 0.6, pitch: -0.35, dist: 14 };

  var state = {
    running: true,
    orbit: true,
    speed: 1,
    t: 0,
    last: performance.now(),
    fpsAcc: 0,
    fpsFrames: 0,
    fps: 0
  };

  function resize() {
    W = window.innerWidth;
    H = window.innerHeight;
    canvas.width = W;
    canvas.height = H;
  }
  window.addEventListener("resize", resize);
  resize();

  // --- Pointer drag to orbit the camera -----------------------------------
  var dragging = false, lastX = 0, lastY = 0;
  canvas.addEventListener("pointerdown", function (e) {
    dragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
  });
  window.addEventListener("pointermove", function (e) {
    if (!dragging) return;
    var dx = e.clientX - lastX;
    var dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    cam.yaw += dx * 0.005;
    cam.pitch -= dy * 0.005;
    if (cam.pitch > 1.2) cam.pitch = 1.2;
    if (cam.pitch < -1.2) cam.pitch = -1.2;
  });
  window.addEventListener("pointerup", function () { dragging = false; });

  // --- HUD controls -------------------------------------------------------
  btnPause.addEventListener("click", function () {
    state.running = !state.running;
    btnPause.textContent = state.running ? "Pause" : "Resume";
  });
  btnOrbit.addEventListener("click", function () {
    state.orbit = !state.orbit;
    btnOrbit.textContent = state.orbit ? "Orbit ON" : "Orbit OFF";
  });
  btnReset.addEventListener("click", function () {
    cam.yaw = DEFAULT.yaw;
    cam.pitch = DEFAULT.pitch;
    cam.dist = DEFAULT.dist;
    state.speed = 1;
    speedEl.value = "1";
    speedVal.textContent = "1.0";
    state.orbit = true;
    btnOrbit.textContent = "Orbit ON";
    state.running = true;
    btnPause.textContent = "Pause";
  });
  speedEl.addEventListener("input", function () {
    state.speed = parseFloat(speedEl.value);
    speedVal.textContent = state.speed.toFixed(1);
  });

  // --- Background: dark radial-gradient space -----------------------------
  function drawBackground() {
    var g = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.75);
    g.addColorStop(0, "#060318");
    g.addColorStop(1, "#010108");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  }

  // --- Stars: 180 twinkling points ----------------------------------------
  function drawStars() {
    for (var i = 0; i < scene.stars.length; i++) {
      var s = scene.stars[i];
      var p = Engine.project(s, cam, W, H);
      if (!p) continue;
      var tw = 0.4 + 0.6 * (0.5 + 0.5 * Math.sin(state.t * s.tw + s.phase));
      ctx.globalAlpha = tw;
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.arc(p.x, p.y, s.size, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // --- Cyber grid floor ---------------------------------------------------
  function drawGrid() {
    var g = scene.grid;
    var e = g.extent, step = g.step, y = g.y;
    ctx.strokeStyle = "rgba(0,245,255,0.35)";
    ctx.lineWidth = 1;
    // Radial lines
    for (var i = -e; i <= e; i += step) {
      var a = Engine.project({ x: i, y: y, z: -e }, cam, W, H);
      var b = Engine.project({ x: i, y: y, z: e }, cam, W, H);
      if (a && b) { ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }
      var c = Engine.project({ x: -e, y: y, z: i }, cam, W, H);
      var d = Engine.project({ x: e, y: y, z: i }, cam, W, H);
      if (c && d) { ctx.beginPath(); ctx.moveTo(c.x, c.y); ctx.lineTo(d.x, d.y); ctx.stroke(); }
    }
  }

  // --- Portal core: glowing center + two counter-rotating neon rings ------
  function drawPortalCore() {
    var cx = W / 2, cy = H / 2 - 20;
    var R = Math.min(W, H) * 0.16;
    // Glowing center
    var glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.4);
    glow.addColorStop(0, "rgba(255,255,255,0.9)");
    glow.addColorStop(0.3, "rgba(0,245,255,0.5)");
    glow.addColorStop(1, "rgba(0,245,255,0)");
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(cx, cy, R * 1.4, 0, Math.PI * 2);
    ctx.fill();

    // Ring 1: cyan, rotating one way
    drawRing(cx, cy, R, state.t * 0.8, "#00f5ff");
    // Ring 2: magenta, counter-rotating
    drawRing(cx, cy, R * 0.72, -state.t * 1.1, "#ff2ae6");
  }

  function drawRing(cx, cy, R, angle, color) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(angle);
    ctx.strokeStyle = color;
    ctx.lineWidth = 10;
    ctx.shadowColor = color;
    ctx.shadowBlur = 24;
    ctx.beginPath();
    // Dashed arc for a segmented neon look
    var segs = 24;
    for (var i = 0; i < segs; i++) {
      var a0 = (i / segs) * Math.PI * 2;
      var a1 = ((i + 0.9) / segs) * Math.PI * 2;
      ctx.moveTo(Math.cos(a0) * R, Math.sin(a0) * R);
      ctx.arc(0, 0, R, a0, a1);
    }
    ctx.stroke();
    ctx.restore();
    ctx.shadowBlur = 0;
  }

  // --- Crystals: translate orbiting octahedra to their current position ---
  function drawCrystals() {
    var all = [];
    for (var i = 0; i < scene.crystals.length; i++) {
      var c = scene.crystals[i];
      var a = c.baseAngle + state.t * c.speed;
      var ox = Math.cos(a) * c.radius;
      var oz = Math.sin(a) * c.radius;
      var oy = c.height + Math.sin(state.t * 1.3 + c.bob) * 0.4;
      var faces = c.faces;
      for (var j = 0; j < faces.length; j++) {
        var f = faces[j];
        var verts = [];
        for (var k = 0; k < f.verts.length; k++) {
          var v = f.verts[k];
          verts.push({ x: v.x + ox, y: v.y + oy, z: v.z + oz });
        }
        all.push({ verts: verts, color: f.color, normal: f.normal });
      }
    }
    return all;
  }

  // --- Particles: 110 rising neon motes -----------------------------------
  function drawParticles() {
    for (var i = 0; i < scene.particles.length; i++) {
      var p = scene.particles[i];
      var proj = Engine.project(p, cam, W, H);
      if (!proj) continue;
      var col = p.cyan ? "0,245,255" : "255,42,230";
      var a = 0.5 + 0.5 * Math.sin(state.t * 2 + p.phase);
      ctx.fillStyle = "rgba(" + col + "," + (0.3 + 0.5 * a).toFixed(2) + ")";
      ctx.beginPath();
      ctx.arc(proj.x, proj.y, p.size, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function updateParticles(dt) {
    for (var i = 0; i < scene.particles.length; i++) {
      var p = scene.particles[i];
      p.y += p.vy * dt;
      if (p.y > 9) {
        p.y = -3;
        p.x = (Math.random() - 0.5) * 16;
        p.z = (Math.random() - 0.5) * 16;
      }
    }
  }

  // --- Main loop ----------------------------------------------------------
  function frame(now) {
    var dt = (now - state.last) / 1000;
    state.last = now;
    if (dt > 0.1) dt = 0.1;

    // FPS
    state.fpsAcc += dt;
    state.fpsFrames++;
    if (state.fpsAcc >= 0.5) {
      state.fps = Math.round(state.fpsFrames / state.fpsAcc);
      state.fpsAcc = 0;
      state.fpsFrames = 0;
    }

    if (state.running) {
      state.t += dt * state.speed;
      if (state.orbit) {
        cam.yaw += dt * 0.25 * state.speed;
      }
      updateParticles(dt * state.speed);
    }

    drawBackground();
    drawStars();
    drawGrid();

    // Static boxes (36 faces)
    var boxFaces = [];
    for (var i = 0; i < scene.boxes.length; i++) {
      for (var j = 0; j < scene.boxes[i].length; j++) {
        boxFaces.push(scene.boxes[i][j]);
      }
    }
    var nPolys = Engine.renderFaces(ctx, boxFaces, cam, W, H);

    // Crystals (48 triangles)
    var crystalFaces = drawCrystals();
    nPolys += Engine.renderFaces(ctx, crystalFaces, cam, W, H);

    drawPortalCore();
    drawParticles();

    // HUD counters
    fpsEl.textContent = String(state.fps);
    polysEl.textContent = String(nPolys);
    partsEl.textContent = String(scene.particles.length);

    requestAnimationFrame(frame);
  }

  requestAnimationFrame(frame);
})(window);
