(function () {
  'use strict';

  var canvas = document.getElementById('c');
  var btnPause = document.getElementById('btnPause');
  var btnWire = document.getElementById('btnWire');
  var btnReset = document.getElementById('btnReset');
  var speedInput = document.getElementById('speed');
  var stats = document.getElementById('stats');

  function init() {
    window.Engine3D.init(canvas);

    btnPause.addEventListener('click', function () {
      window.Engine3D.togglePause();
    });

    btnWire.addEventListener('click', function () {
      window.Engine3D.toggleWireframe();
    });

    btnReset.addEventListener('click', function () {
      window.Engine3D.reset();
    });

    speedInput.addEventListener('input', function () {
      window.Engine3D.setSpeed(parseFloat(speedInput.value));
    });

    setInterval(function () {
      var s = window.Engine3D.getStats();
      stats.textContent = s.fps + ' FPS | ' + s.polys + ' polys';
    }, 250);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
