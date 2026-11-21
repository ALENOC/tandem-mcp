// app.js - animation loop, camera controls, HUD wiring
(function (global) {
  "use strict";

  var canvas = document.getElementById("c");
  var renderer = new global.Engine3D.Renderer(canvas);
  var scene = new global.Scene();

  // HUD elements
  var elFps = document.getElementById("fps");
  var elPolys = document.getElementById("polys");
  var elParts = document.getElementById("parts");
  var btnPause = document.getElementById("btn-pause");
  var btnOrbit = document.getElementById("btn-orbit");
  var btnReset = document.getElementById("btn-reset");
  var speedEl = document.getElementById("speed");

  // Camera orbit state
  var DEF = { theta: 0.7, dist: 17, height: 6.5, target: [0, 3, 0] };
  var cam = {
    theta: DEF.theta,
    dist: DEF.dist,
    height: DEF.height,
    target: DEF.target.slice()
  };

  var paused = false;
  var autoOrbit = true;
  var speed = 1;
  var t = 0;
  var last = performance.now();
  var fps = 0;
  var fpsAcc = 0;
  var fpsFrames = 0;
  var fpsTimer = 0;

  function applyCamera() {
    var tx = cam.target[0], ty = cam.target[1], tz = cam.target[2];
    var x = tx + Math.sin(cam.theta) * cam.dist;
    var z = tz + Math.cos(cam.theta) * cam.dist;
    var y = cam.height;
    renderer.camPos = [x, y, z];
    renderer.camTarget = [tx, ty, tz];
  }

  function frame(now) {
    var dt = (now - last) / 1000;
    last = now;
    if (dt > 0.1) dt = 0.1;

    // fps
    fpsFrames++;
    fpsTimer += dt;
    if (fpsTimer >= 0.5) {
      fps = Math.round(fpsFrames / fpsTimer);
      fpsFrames = 0;
      fpsTimer = 0;
    }

    if (!paused) {
      t += dt * speed;
      if (autoOrbit) {
        cam.theta += dt * 0.25 * speed;
      }
      scene.update(dt, speed);
    }

    applyCamera();
    var polys = scene.build(t, cam);
    renderer.draw(polys);

    // HUD
    elFps.textContent = String(fps);
    elPolys.textContent = String(renderer.polys);
    elParts.textContent = String(scene.parts.length);

    requestAnimationFrame(frame);
  }

  // ---- controls ----------------------------------------------------------
  btnPause.addEventListener("click", function () {
    paused = !paused;
    btnPause.textContent = paused ? "Resume" : "Pause";
  });

  btnOrbit.addEventListener("click", function () {
    autoOrbit = !autoOrbit;
    btnOrbit.textContent = autoOrbit ? "Orbit ON" : "Orbit OFF";
  });

  btnReset.addEventListener("click", function () {
    cam.theta = DEF.theta;
    cam.dist = DEF.dist;
    cam.height = DEF.height;
    cam.target = DEF.target.slice();
    speed = 1;
    speedEl.value = "1";
    paused = false;
    btnPause.textContent = "Pause";
    autoOrbit = true;
    btnOrbit.textContent = "Orbit ON";
  });

  speedEl.addEventListener("input", function () {
    speed = parseFloat(speedEl.value) || 1;
  });

  // pointer drag orbit
  var dragging = false;
  var lastX = 0, lastY = 0;
  canvas.addEventListener("pointerdown", function (e) {
    dragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointermove", function (e) {
    if (!dragging) return;
    var dx = e.clientX - lastX;
    var dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    cam.theta -= dx * 0.005;
    cam.height = Math.max(1, Math.min(20, cam.height - dy * 0.05));
  });
  canvas.addEventListener("pointerup", function (e) {
    dragging = false;
    try { canvas.releasePointerCapture(e.pointerId); } catch (err) {}
  });

  // wheel zoom
  canvas.addEventListener("wheel", function (e) {
    e.preventDefault();
    cam.dist = Math.max(6, Math.min(40, cam.dist + e.deltaY * 0.01));
  }, { passive: false });

  // resize
  window.addEventListener("resize", function () {
    renderer._resize();
  });

  // start
  applyCamera();
  requestAnimationFrame(frame);

})(typeof window !== "undefined" ? window : globalThis);
