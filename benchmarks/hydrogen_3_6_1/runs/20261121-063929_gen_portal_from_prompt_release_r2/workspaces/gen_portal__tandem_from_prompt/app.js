// app.js - Main application: canvas, loop, HUD, input
(function () {
  var canvas = document.getElementById('c');
  var renderer = new Renderer(canvas);
  var scene = new Scene();

  // --- HUD elements ---
  var hud = document.getElementById('hud');
  var fpsEl = document.getElementById('fps');
  var polysEl = document.getElementById('polys');
  var partsEl = document.getElementById('parts');
  var btnPause = document.getElementById('btnPause');
  var btnOrbit = document.getElementById('btnOrbit');
  var btnReset = document.getElementById('btnReset');
  var speedSlider = document.getElementById('speed');

  // --- Resize ---
  function resize() {
    renderer.resize(window.innerWidth, window.innerHeight);
  }
  window.addEventListener('resize', resize);
  resize();

  // --- FPS tracking ---
  var frameCount = 0;
  var lastFpsTime = performance.now();
  var fps = 0;

  // --- Mouse drag to rotate camera ---
  var dragging = false;
  var lastX = 0, lastY = 0;
  canvas.addEventListener('mousedown', function (e) {
    dragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
  });
  window.addEventListener('mousemove', function (e) {
    if (!dragging) return;
    var dx = e.clientX - lastX;
    var dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    renderer.camera.azimuth += dx * 0.005;
    renderer.camera.elevation = Math.max(0.05, Math.min(1.4, renderer.camera.elevation + dy * 0.005));
  });
  window.addEventListener('mouseup', function () { dragging = false; });

  // --- Buttons ---
  btnPause.addEventListener('click', function () {
    scene.paused = !scene.paused;
    btnPause.textContent = scene.paused ? 'Resume' : 'Pause';
  });
  btnOrbit.addEventListener('click', function () {
    scene.orbitOn = !scene.orbitOn;
    btnOrbit.textContent = scene.orbitOn ? 'Orbit ON' : 'Orbit OFF';
  });
  btnReset.addEventListener('click', function () {
    renderer.camera.azimuth = 0.6;
    renderer.camera.elevation = 0.35;
    renderer.camera.distance = 14;
    scene.time = 0;
    scene.speed = 1;
    scene.paused = false;
    scene.orbitOn = true;
    btnPause.textContent = 'Pause';
    btnOrbit.textContent = 'Orbit ON';
    speedSlider.value = 1;
  });
  speedSlider.addEventListener('input', function () {
    scene.speed = parseFloat(speedSlider.value);
  });

  // --- Animation loop ---
  var lastTime = performance.now();
  function loop(now) {
    var dt = Math.min((now - lastTime) / 1000, 0.1);
    lastTime = now;

    // FPS
    frameCount++;
    if (now - lastFpsTime >= 500) {
      fps = Math.round(frameCount / ((now - lastFpsTime) / 1000));
      frameCount = 0;
      lastFpsTime = now;
    }

    // Auto orbit
    if (scene.orbitOn && !scene.paused) {
      renderer.camera.azimuth += dt * 0.3 * scene.speed;
    }

    scene.update(dt);

    // Render
    renderer.beginFrame();
    scene.draw(renderer);

    // HUD
    fpsEl.textContent = fps;
    polysEl.textContent = renderer.polyCount;
    partsEl.textContent = scene.partCount;

    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
})();
