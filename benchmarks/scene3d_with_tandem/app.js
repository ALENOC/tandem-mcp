(function () {
  'use strict';

  var canvas = document.getElementById('c');
  var engine = new window.PortalEngine(canvas);

  var playBtn = document.getElementById('playBtn');
  var orbitBtn = document.getElementById('orbitBtn');
  var resetBtn = document.getElementById('resetBtn');
  var spd = document.getElementById('spd');
  var spdVal = document.getElementById('spdVal');
  var fpsEl = document.getElementById('fps');
  var polysEl = document.getElementById('polys');
  var partsEl = document.getElementById('parts');

  var playing = true;
  var autoOrbit = true;
  var speed = parseFloat(spd.value) || 1;

  playBtn.addEventListener('click', function () {
    playing = !playing;
    playBtn.textContent = playing ? 'Pause' : 'Play';
  });

  orbitBtn.addEventListener('click', function () {
    autoOrbit = !autoOrbit;
    engine.setAutoOrbit(autoOrbit);
    orbitBtn.textContent = 'Orbit: ' + (autoOrbit ? 'ON' : 'OFF');
  });

  resetBtn.addEventListener('click', function () {
    engine.resetCamera();
  });

  spd.addEventListener('input', function () {
    speed = parseFloat(spd.value) || 1;
    engine.setSpeed(speed);
    spdVal.textContent = speed.toFixed(1) + 'x';
  });

  window.addEventListener('resize', function () {
    engine.resize();
  });

  var last = performance.now();
  var fpsAcc = 0;
  var fpsFrames = 0;

  function frame(now) {
    var dt = (now - last) / 1000;
    if (dt < 0) dt = 0;
    if (dt > 0.05) dt = 0.05;
    last = now;

    if (playing) {
      engine.step(dt, speed, autoOrbit);
    }

    var stats = engine.render(now);

    fpsAcc += dt;
    fpsFrames += 1;
    if (fpsAcc >= 0.5) {
      fpsEl.textContent = Math.round(fpsFrames / fpsAcc);
      fpsAcc = 0;
      fpsFrames = 0;
    }
    polysEl.textContent = stats.polys;
    partsEl.textContent = stats.particles;

    requestAnimationFrame(frame);
  }

  requestAnimationFrame(frame);
})();
