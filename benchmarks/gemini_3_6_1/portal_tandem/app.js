// app.js : wires the HUD controls to window.Engine3D.

(function () {
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
    var paused = window.Engine3D.togglePause();
    btnPause.textContent = paused ? "Play" : "Pause";
  });

  btnOrbit.addEventListener("click", function () {
    var orbit = window.Engine3D.toggleOrbit();
    btnOrbit.textContent = orbit ? "Orbit ON" : "Orbit OFF";
  });

  btnReset.addEventListener("click", function () {
    window.Engine3D.reset();
  });

  speed.addEventListener("input", function () {
    var v = parseFloat(speed.value);
    window.Engine3D.setSpeed(v);
    spdVal.textContent = v.toFixed(1) + "x";
  });

  setInterval(function () {
    var s = window.Engine3D.getStats();
    fpsEl.textContent = Math.round(s.fps);
    polysEl.textContent = s.polys;
    partsEl.textContent = s.parts;
  }, 500);
})();
