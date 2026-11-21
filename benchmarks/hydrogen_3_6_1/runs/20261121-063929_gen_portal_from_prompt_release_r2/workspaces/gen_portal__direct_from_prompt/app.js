(function () {
  "use strict";

  const canvas = document.getElementById("c");
  const ctx = canvas.getContext("2d");

  const elFps = document.getElementById("stat-fps");
  const elPolys = document.getElementById("stat-polys");
  const elParts = document.getElementById("stat-parts");
  const btnPause = document.getElementById("btn-pause");
  const btnOrbit = document.getElementById("btn-orbit");
  const btnReset = document.getElementById("btn-reset");
  const speedSlider = document.getElementById("speed-slider");
  const speedVal = document.getElementById("speed-val");

  const scene = new window.PortalScene();

  const defaultCam = {
    yaw: 0.42,
    pitch: 0.28,
    distance: 8.8,
    target: window.Engine3D.vec3(0, 2.2, 0),
  };

  const state = {
    paused: false,
    autoOrbit: true,
    speed: 1.0,
    yaw: defaultCam.yaw,
    pitch: defaultCam.pitch,
    distance: defaultCam.distance,
    dragging: false,
    lastX: 0,
    lastY: 0,
  };

  let width = 0;
  let height = 0;

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  window.addEventListener("resize", resize);
  resize();

  // Pointer orbit & wheel zoom
  canvas.addEventListener("pointerdown", (e) => {
    state.dragging = true;
    state.lastX = e.clientX;
    state.lastY = e.clientY;
    canvas.setPointerCapture(e.pointerId);
  });

  canvas.addEventListener("pointermove", (e) => {
    if (!state.dragging) return;
    const dx = e.clientX - state.lastX;
    const dy = e.clientY - state.lastY;
    state.lastX = e.clientX;
    state.lastY = e.clientY;
    state.yaw -= dx * 0.0065;
    state.pitch = window.Engine3D.clamp(state.pitch + dy * 0.0055, -0.2, 1.15);
  });

  canvas.addEventListener("pointerup", (e) => {
    state.dragging = false;
    if (canvas.hasPointerCapture(e.pointerId)) {
      canvas.releasePointerCapture(e.pointerId);
    }
  });

  canvas.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      state.distance = window.Engine3D.clamp(state.distance + e.deltaY * 0.006, 4.5, 16.5);
    },
    { passive: false }
  );

  // HUD controls
  btnPause.addEventListener("click", () => {
    state.paused = !state.paused;
    btnPause.textContent = state.paused ? "Resume" : "Pause";
    btnPause.classList.toggle("active", state.paused);
  });

  btnOrbit.addEventListener("click", () => {
    state.autoOrbit = !state.autoOrbit;
    btnOrbit.textContent = state.autoOrbit ? "Orbit ON" : "Orbit OFF";
    btnOrbit.classList.toggle("active", state.autoOrbit);
  });

  btnReset.addEventListener("click", () => {
    state.paused = false;
    state.autoOrbit = true;
    state.speed = 1.0;
    state.yaw = defaultCam.yaw;
    state.pitch = defaultCam.pitch;
    state.distance = defaultCam.distance;

    speedSlider.value = "1.0";
    speedVal.textContent = "1.0x";
    btnPause.textContent = "Pause";
    btnPause.classList.remove("active");
    btnOrbit.textContent = "Orbit ON";
    btnOrbit.classList.add("active");
    scene.reset();
  });

  speedSlider.addEventListener("input", () => {
    state.speed = parseFloat(speedSlider.value);
    speedVal.textContent = `${state.speed.toFixed(1)}x`;
  });

  let lastTime = performance.now();
  let fpsFrames = 0;
  let fpsTimer = 0;

  function tick(now) {
    const rawDt = Math.min((now - lastTime) / 1000, 0.05);
    lastTime = now;

    if (!state.paused) {
      const dt = rawDt * state.speed;
      scene.update(dt);
      if (state.autoOrbit && !state.dragging) {
        state.yaw += dt * 0.28;
      }
    }

    const cam = window.Engine3D.createCamera(
      state.yaw,
      state.pitch,
      state.distance,
      defaultCam.target
    );
    const stats = scene.render(ctx, width, height, cam);

    elPolys.textContent = String(stats.polys);
    elParts.textContent = String(stats.parts);

    fpsFrames++;
    fpsTimer += rawDt;
    if (fpsTimer >= 0.35) {
      elFps.textContent = String(Math.round(fpsFrames / fpsTimer));
      fpsFrames = 0;
      fpsTimer = 0;
    }

    requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
})();
