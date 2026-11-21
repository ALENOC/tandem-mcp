(function () {
  'use strict';

  const canvas = document.getElementById('c');
  const fpsVal = document.getElementById('fpsVal');
  const polysVal = document.getElementById('polysVal');
  const partsVal = document.getElementById('partsVal');
  const pauseBtn = document.getElementById('pauseBtn');
  const orbitBtn = document.getElementById('orbitBtn');
  const resetBtn = document.getElementById('resetBtn');
  const speedSlider = document.getElementById('speedSlider');
  const speedValue = document.getElementById('speedValue');
  const statusDot = document.getElementById('statusDot');

  const camera = new window.Engine3D.Camera3D();
  const renderer = new window.Engine3D.Renderer3D(canvas);
  const scene = new window.NeonPortalScene();

  let width = window.innerWidth;
  let height = window.innerHeight;
  let paused = false;
  let autoOrbit = true;
  let speed = 1.0;

  let isDragging = false;
  let lastX = 0;
  let lastY = 0;

  let lastTime = performance.now();
  let fpsAccum = 0;
  let fpsFrames = 0;
  let displayedFps = 60;

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    renderer.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function updateHudButtons() {
    pauseBtn.textContent = paused ? 'Resume' : 'Pause';
    pauseBtn.classList.toggle('active', paused);
    statusDot.classList.toggle('paused', paused);

    orbitBtn.textContent = autoOrbit ? 'Orbit ON' : 'Orbit OFF';
    orbitBtn.classList.toggle('active', autoOrbit);

    speedValue.textContent = `${speed.toFixed(1)}x`;
  }

  pauseBtn.addEventListener('click', () => {
    paused = !paused;
    updateHudButtons();
  });

  orbitBtn.addEventListener('click', () => {
    autoOrbit = !autoOrbit;
    updateHudButtons();
  });

  resetBtn.addEventListener('click', () => {
    camera.reset();
    speed = 1.0;
    speedSlider.value = '1.0';
    paused = false;
    autoOrbit = true;
    updateHudButtons();
  });

  speedSlider.addEventListener('input', (e) => {
    speed = parseFloat(e.target.value);
    updateHudButtons();
  });

  canvas.addEventListener('pointerdown', (e) => {
    isDragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
    canvas.setPointerCapture(e.pointerId);
  });

  canvas.addEventListener('pointermove', (e) => {
    if (!isDragging) return;
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    camera.yaw -= dx * 0.0075;
    camera.pitch = Math.max(-0.25, Math.min(1.25, camera.pitch + dy * 0.0065));
  });

  canvas.addEventListener('pointerup', (e) => {
    isDragging = false;
    canvas.releasePointerCapture(e.pointerId);
  });

  canvas.addEventListener('pointercancel', () => {
    isDragging = false;
  });

  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    camera.distance = Math.max(4.5, Math.min(18, camera.distance + e.deltaY * 0.008));
  }, { passive: false });

  window.addEventListener('resize', resize);

  function frame(now) {
    const dt = Math.min(0.05, (now - lastTime) / 1000);
    lastTime = now;

    if (!paused) {
      scene.update(dt, speed);
      if (autoOrbit && !isDragging) {
        camera.yaw += 0.28 * speed * dt;
      }
    }

    scene.render(renderer, camera, width, height);

    fpsAccum += dt;
    fpsFrames++;
    if (fpsAccum >= 0.25) {
      displayedFps = Math.round(fpsFrames / fpsAccum);
      fpsAccum = 0;
      fpsFrames = 0;
      fpsVal.textContent = String(displayedFps);
    }

    polysVal.textContent = String(scene.polyCount);
    partsVal.textContent = String(scene.partCount);

    requestAnimationFrame(frame);
  }

  resize();
  updateHudButtons();
  requestAnimationFrame(frame);
})();
