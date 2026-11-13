(function () {
  var E = window.Engine3D;
  window.Engine3D.init(document.getElementById("c"));

  var btnPause = document.getElementById("btnPause");
  var btnOrbit = document.getElementById("btnOrbit");
  var btnReset = document.getElementById("btnReset");
  var speed = document.getElementById("speed");
  var spdVal = document.getElementById("spdVal");
  var fpsEl = document.getElementById("fps");
  var polysEl = document.getElementById("polys");
  var partsEl = document.getElementById("parts");

  btnPause.addEventListener("click", function () {
    var paused = E.togglePause();
    btnPause.textContent = paused ? "Play" : "Pause";
  });

  btnOrbit.addEventListener("click", function () {
    var orbit = E.toggleOrbit();
    btnOrbit.textContent = orbit ? "Orbit ON" : "Orbit OFF";
  });

  btnReset.addEventListener("click", function () {
    E.reset();
  });

  speed.addEventListener("input", function () {
    var v = parseFloat(speed.value);
    E.setSpeed(v);
    spdVal.textContent = v.toFixed(1) + "x";
  });

  setInterval(function () {
    var s = E.getStats();
    fpsEl.textContent = Math.round(s.fps);
    polysEl.textContent = s.polys;
    partsEl.textContent = s.parts;
  }, 500);
})();
