(function () {
  const canvas = document.getElementById('c');
  window.Engine3D.init(canvas);

  const btnPause = document.getElementById('btnPause');
  const btnOrbit = document.getElementById('btnOrbit');
  const btnReset = document.getElementById('btnReset');
  const speedInput = document.getElementById('speed');
  const spdVal = document.getElementById('spdVal');
  const fpsEl = document.getElementById('fps');
  const polysEl = document.getElementById('polys');
  const partsEl = document.getElementById('parts');

  btnPause.addEventListener('click', function () {
    const paused = window.Engine3D.togglePause();
    btnPause.textContent = paused ? 'Play' : 'Pause';
  });

  btnOrbit.addEventListener('click', function () {
    const on = window.Engine3D.toggleOrbit();
    btnOrbit.textContent = on ? 'Orbit ON' : 'Orbit OFF';
  });

  btnReset.addEventListener('click', function () {
    window.Engine3D.reset();
  });

  speedInput.addEventListener('input', function () {
    const val = parseFloat(speedInput.value);
    window.Engine3D.setSpeed(val);
    spdVal.textContent = val.toFixed(1) + 'x';
  });

  setInterval(function () {
    const stats = window.Engine3D.getStats();
    fpsEl.textContent = Math.round(stats.fps);
    polysEl.textContent = stats.polys;
    partsEl.textContent = stats.parts;
  }, 500);
})();
