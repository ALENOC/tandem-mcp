/**
 * Application controller: animation loop, camera orbit/drag/zoom, and HUD bindings.
 */
(function (global) {
  'use strict';

  const { Camera3D, SoftwareRenderer } = global.Engine3D;
  const { NeonPortalScene, SCENE_CONSTANTS } = global;

  const DEFAULTS = {
    yaw: 0.45,
    pitch: 0.24,
    distance: 11.5,
    speed: 1.0,
    paused: false,
    autoOrbit: true
  };

  const canvas = document.getElementById('c');
  const fpsEl = document.getElementById('fpsVal');
  const polysEl = document.getElementById('polysVal');
  const partsEl = document.getElementById('partsVal');
  const pauseBtn = document.getElementById('pauseBtn');
  const orbitBtn = document.getElementById('orbitBtn');
  const resetBtn = document.getElementById('resetBtn');
  const speedSlider = document.getElementById('speedSlider');
  const speedValEl = document.getElementById('speedVal');
  const statusDot = document.getElementById('statusDot');

  const renderer = new SoftwareRenderer(canvas);
  const scene = new NeonPortalScene();
  const camera = new Camera3D({
    target: { x: 0, y: 2.1, z: 0 },
    yaw: DEFAULTS.yaw,
    pitch: DEFAULTS.pitch,
    distance: DEFAULTS.distance,
    fov: 640
  });

  const state = {
    paused: DEFAULTS.paused,
    autoOrbit: DEFAULTS.autoOrbit,
    speed: DEFAULTS.speed,
    dragging: false,
    lastX: 0,
    lastY: 0
  };

  function syncHud() {
    pauseBtn.textContent = state.paused ? 'Resume' : 'Pause';
    pauseBtn.classList.toggle('active', state.paused);
    orbitBtn.textContent = state.autoOrbit ? 'Orbit ON' : 'Orbit OFF';
    orbitBtn.classList.toggle('active', state.autoOrbit);
    speedSlider.value = state.speed.toFixed(1);
    speedValEl.textContent = `${state.speed.toFixed(1)}x`;
    partsEl.textContent = String(SCENE_CONSTANTS.PARTICLE_COUNT);
    statusDot.style.opacity = state.paused ? '0.35' : '1';
  }

  function handleResize() {
    renderer.resize();
  }

  window.addEventListener('resize', handleResize);
  handleResize();

  // Pointer drag orbit
  canvas.addEventListener('pointerdown', (e) => {
    state.dragging = true;
    state.lastX = e.clientX;
    state.lastY = e.clientY;
    canvas.setPointerCapture(e.pointerId);
  });

  canvas.addEventListener('pointermove', (e) => {
    if (!state.dragging) return;
    const dx = e.clientX - state.lastX;
    const dy = e.clientY - state.lastY;
    state.lastX = e.clientX;
    state.lastY = e.clientY;

    camera.yaw -= dx * 0.0075;
    camera.pitch = Math.max(-0.25, Math.min(1.15, camera.pitch + dy * 0.0065));
  });

  function stopDrag() {
    state.dragging = false;
  }
  canvas.addEventListener('pointerup', stopDrag);
  canvas.addEventListener('pointercancel', stopDrag);

  // Mouse wheel zoom
  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    camera.distance = Math.max(5.5, Math.min(22, camera.distance + e.deltaY * 0.01));
  }, { passive: false });

  // HUD controls
  pauseBtn.addEventListener('click', () => {
    state.paused = !state.paused;
    syncHud();
  });

  orbitBtn.addEventListener('click', () => {
    state.autoOrbit = !state.autoOrbit;
    syncHud();
  });

  resetBtn.addEventListener('click', () => {
    state.paused = DEFAULTS.paused;
    state.autoOrbit = DEFAULTS.autoOrbit;
    state.speed = DEFAULTS.speed;
    camera.yaw = DEFAULTS.yaw;
    camera.pitch = DEFAULTS.pitch;
    camera.distance = DEFAULTS.distance;
    syncHud();
  });

  speedSlider.addEventListener('input', () => {
    state.speed = parseFloat(speedSlider.value) || 1.0;
    speedValEl.textContent = `${state.speed.toFixed(1)}x`;
  });

  syncHud();

  let lastTime = performance.now();
  let fpsFrames = 0;
  let fpsTimer = 0;

  function frame(now) {
    const rawDt = Math.min(0.05, (now - lastTime) / 1000);
    lastTime = now;

    if (!state.paused) {
      const simDt = rawDt * state.speed;
      scene.update(simDt);
      if (state.autoOrbit && !state.dragging) {
        camera.yaw += 0.28 * simDt;
      }
    }

    camera.updateBasis();
    scene.render(renderer, camera);

    polysEl.textContent = String(renderer.lastPolyCount);

    fpsFrames += 1;
    fpsTimer += rawDt;
    if (fpsTimer >= 0.4) {
      const fps = Math.round(fpsFrames / fpsTimer);
      fpsEl.textContent = String(fps);
      fpsFrames = 0;
      fpsTimer = 0;
    }

    requestAnimationFrame(frame);
  }

  requestAnimationFrame(frame);
})(window);
