(function () {
  'use strict';

  var canvas = document.getElementById('c');
  var btnPause = document.getElementById('btnPause');
  var btnOrbit = document.getElementById('btnOrbit');
  var btnReset = document.getElementById('btnReset');
  var speedInput = document.getElementById('speed');
  var spdVal = document.getElementById('spdVal');
  var fpsEl = document.getElementById('fps');
  var polysEl = document.getElementById('polys');
  var partsEl = document.getElementById('parts');

  function init() {
    window.Engine3D.init(canvas);

    btnPause.addEventListener('click', function () {
      window.Engine3D.togglePause();
    });

    btnOrbit.addEventListener('click', function () {
      window.Engine3D.toggleOrbit();
    });

    btnReset.addEventListener('click', function () {
      window.Engine3D.reset();
    });

    speedInput.addEventListener('input', function () {
      var v = parseFloat(speedInput.value);
      window.Engine3D.setSpeed(v);
      spdVal.textContent = v.toFixed(1) + 'x';
    });

    setInterval(function () {
      var s = window.Engine3D.getStats();
      fpsEl.textContent = s.fps;
      polysEl.textContent = s.polys;
      partsEl.textContent = s.parts;
    }, 200);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
