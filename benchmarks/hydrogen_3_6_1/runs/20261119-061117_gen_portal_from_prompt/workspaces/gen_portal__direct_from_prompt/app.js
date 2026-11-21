/**
 * app.js - Main loop, camera controls, and glassmorphism HUD bindings.
 */
(function (global) {
  'use strict';

  const canvas = document.getElementById('c');
  const ctx = canvas.getContext('2d');

  const fpsEl = document.getElementById('stat-fps');
  const polysEl = document.getElementById('stat-polys');
  const partsEl = document.getElementById('stat-parts');

  const btnPause = document.getElementById('btn-pause');
  const btnOrbit = document.getElementById('btn-orbit');
  const btnReset = document.getElementById('btn-reset');
  const speedSlider = document.getElementById('speed-slider');
  const speedVal = document.getElementById('speed-val');

  const DEFAULT_CAM = { yaw: 0.45, pitch: 0.24, distance: 15.5 };
  const camera = new global.Engine3D.Camera(DEFAULT_CAM);
  const scene = new global.PortalScene();

  const state = {
    paused: false,
    orbit: true,
    speed: 1.0,
    width: window.innerWidth,
    height: window.innerHeight,
    dpr: Math.min(window.devicePixelRatio || 1, 2),
  };

  function resize() {
    state.width = window.innerWidth;
    state.height = window.innerHeight;
    state.dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.floor(state.width * state.dpr);
    canvas.height = Math.floor(state.height * state.dpr);
    ctx.setTransform(state.dpr, 0, 0, state.dpr, 0, 0);
  }
  window.addEventListener('resize', resize);
  resize();

  // Pointer drag & wheel camera controls
  let dragging = false;
  let lastX = 0;
  let lastY = 0;

  canvas.addEventListener('pointerdown', (e) => {
    dragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
    canvas.setPointerCapture(e.pointerId);
  });

  canvas.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    camera.yaw -= dx * 0.0065;
    camera.pitch = Math.max(-0.25, Math.min(1.15, camera.pitch + dy * 0.0055));
    camera.updateBasis();
  });

  canvas.addEventListener('pointerup', (e) => {
    dragging = false;
    if (canvas.hasPointerCapture(e.pointerId)) {
      canvas.releasePointerCapture(e.pointerId);
    }
  });

  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    camera.distance = Math.max(7.5, Math.min(28, camera.distance + e.deltaY * 0.012));
    camera.updateBasis();
  }, { passive: false });

  // HUD Controls
  btnPause.addEventListener('click', () => {
    state.paused = !state.paused;
    btnPause.textContent = state.paused ? 'Resume' : 'Pause';
    btnPause.classList.toggle('active', state.paused);
  });

  btnOrbit.addEventListener('click', () => {
    state.orbit = !state.orbit;
    btnOrbit.textContent = state.orbit ? 'Orbit ON' : 'Orbit OFF';
    btnOrbit.classList.toggle('active', state.orbit);
  });

  btnReset.addEventListener('click', () => {
    state.paused = false;
    state.orbit = true;
    state.speed = 1.0;
    speedSlider.value = '1.0';
    speedVal.textContent = '1.0x';
    btnPause.textContent = 'Pause';
    btnPause.classList.remove('active');
    btnOrbit.textContent = 'Orbit ON';
    btnOrbit.classList.add('active');

    camera.yaw = DEFAULT_CAM.yaw;
    camera.pitch = DEFAULT_CAM.pitch;
    camera.distance = DEFAULT_CAM.distance;
    camera.updateBasis();
    scene.reset();
  });

  speedSlider.addEventListener('input', () => {
    state.speed = parseFloat(speedSlider.value);
    speedVal.textContent = `${state.speed.toFixed(1)}x`;
  });

  // Main animation loop
  let lastTime = performance.now();
  let frameCount = 0;
  let fpsTimer = 0;

  function tick(now) {
    const rawDt = Math.min(0.05, (now - lastTime) / 1000);
    lastTime = now;

    if (!state.paused) {
      scene.update(rawDt, state.speed);
      if (state.orbit && !dragging) {
        camera.yaw += rawDt * 0.28 * state.speed;
        camera.updateBasis();
      }
    }

    const stats = scene.render(ctx, state.width, state.height, camera);
    polysEl.textContent = String(stats.polys);
    partsEl.textContent = String(stats.parts);

    frameCount++;
    fpsTimer += rawDt;
    if (fpsTimer >= 0.25) {
      const fps = Math.round(frameCount / fpsTimer);
      fpsEl.textContent = String(fps);
      frameCount = 0;
      fpsTimer = 0;
    }

    requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
})(window);
