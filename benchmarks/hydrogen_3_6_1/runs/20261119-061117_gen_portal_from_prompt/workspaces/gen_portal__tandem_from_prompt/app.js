/* app.js - bootstrap: canvas, renderer, scene, HUD, input, loop */
(function (global) {
  "use strict";

  const E = global.Engine3D;

  const canvas = document.getElementById("c");
  const R = new E.Renderer(canvas);
  const scene = new global.Scene();

  // HUD elements
  const elFps = document.getElementById("fps");
  const elPolys = document.getElementById("polys");
  const elParts = document.getElementById("parts");
  const btnPause = document.getElementById("btnPause");
  const btnOrbit = document.getElementById("btnOrbit");
  const btnReset = document.getElementById("btnReset");
  const speedInput = document.getElementById("speed");

  // ---- Resize handling ----
  function onResize() { R.resize(); }
  global.addEventListener("resize", onResize);
  onResize();

  // ---- Input: drag orbit + scroll zoom ----
  let dragging = false;
  let lastX = 0, lastY = 0;

  function pointerDown(x, y) { dragging = true; lastX = x; lastY = y; }
  function pointerMove(x, y) {
    if (!dragging) return;
    const dx = x - lastX, dy = y - lastY;
    lastX = x; lastY = y;
    scene.camYaw -= dx * 0.005;
    scene.camPitch += dy * 0.005;
    scene.camPitch = Math.max(-1.2, Math.min(1.2, scene.camPitch));
  }
  function pointerUp() { dragging = false; }

  canvas.addEventListener("mousedown", function (e) { pointerDown(e.clientX, e.clientY); });
  global.addEventListener("mousemove", function (e) { pointerMove(e.clientX, e.clientY); });
  global.addEventListener("mouseup", pointerUp);

  canvas.addEventListener("touchstart", function (e) {
    if (e.touches.length) { const t = e.touches[0]; pointerDown(t.clientX, t.clientY); }
  }, { passive: true });
  canvas.addEventListener("touchmove", function (e) {
    if (e.touches.length) { const t = e.touches[0]; pointerMove(t.clientX, t.clientY); }
  }, { passive: true });
  canvas.addEventListener("touchend", pointerUp);

  canvas.addEventListener("wheel", function (e) {
    e.preventDefault();
    scene.camDist += e.deltaY * 0.02;
    scene.camDist = Math.max(8, Math.min(60, scene.camDist));
  }, { passive: false });

  // ---- HUD buttons ----
  btnPause.addEventListener("click", function () {
    scene.paused = !scene.paused;
    btnPause.textContent = scene.paused ? "Resume" : "Pause";
    btnPause.classList.toggle("active", scene.paused);
  });
  btnOrbit.addEventListener("click", function () {
    scene.orbitOn = !scene.orbitOn;
    btnOrbit.textContent = scene.orbitOn ? "Orbit ON" : "Orbit OFF";
    btnOrbit.classList.toggle("active", scene.orbitOn);
  });
  btnReset.addEventListener("click", function () {
    scene.camYaw = 0.6;
    scene.camPitch = 0.32;
    scene.camDist = 26;
    scene.time = 0;
    scene.speed = 1;
    speedInput.value = "1";
  });
  speedInput.addEventListener("input", function () {
    scene.speed = parseFloat(speedInput.value);
  });

  // ---- Animation loop ----
  let last = global.performance.now();
  let fpsAccum = 0, fpsFrames = 0, fpsTimer = 0;

  function frame(now) {
    let dt = (now - last) / 1000;
    last = now;
    if (dt > 0.1) dt = 0.1; // clamp big gaps

    scene.update(dt);
    const polys = scene.render(R);

    // FPS counter (update ~2x/sec)
    fpsAccum += dt; fpsFrames++; fpsTimer += dt;
    if (fpsTimer >= 0.5) {
      const fps = Math.round(fpsFrames / fpsAccum);
      elFps.textContent = String(fps);
      elPolys.textContent = String(polys);
      elParts.textContent = String(scene.particles.length);
      fpsAccum = 0; fpsFrames = 0; fpsTimer = 0;
    }

    global.requestAnimationFrame(frame);
  }
  global.requestAnimationFrame(frame);

})(typeof window !== "undefined" ? window : globalThis);
