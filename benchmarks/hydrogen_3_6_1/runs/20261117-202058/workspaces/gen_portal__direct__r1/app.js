(function () {
  var canvas = document.getElementById('c');
  window.Engine3D.init(canvas);

  var btnPause = document.getElementById('btnPause');
  var btnOrbit = document.getElementById('btnOrbit');
  var btnReset = document.getElementById('btnReset');
  var speedEl = document.getElementById('speed');
  var spdVal = document.getElementById('spdVal');
  var fpsEl = document.getElementById('fps');
  var polysEl = document.getElementById('polys');
  var partsEl = document.getElementById('parts');

  btnPause.addEventListener('click', function () {
    var paused = window.Engine3D.togglePause();
    btnPause.textContent = paused ? 'Play' : 'Pause';
  });

  btnOrbit.addEventListener('click', function () {
    var orbit = window.Engine3D.toggleOrbit();
    btnOrbit.textContent = orbit ? 'Orbit ON' : 'Orbit OFF';
  });

  btnReset.addEventListener('click', function () {
    window.Engine3D.reset();
  });

  speedEl.addEventListener('input', function (e) {
    var val = parseFloat(e.target.value);
    window.Engine3D.setSpeed(val);
    spdVal.textContent = val.toFixed(1) + 'x';
  });

  function updateStats() {
    var st = window.Engine3D.getStats();
    fpsEl.textContent = Math.round(st.fps);
    polysEl.textContent = st.polys;
    partsEl.textContent = st.parts;
  }

  setInterval(updateStats, 500);
})();
