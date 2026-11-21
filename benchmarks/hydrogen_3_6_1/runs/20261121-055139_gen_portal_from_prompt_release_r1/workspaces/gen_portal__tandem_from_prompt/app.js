// app.js - main loop, HUD, and controls.

(function (global) {
  "use strict";
  var E = global.Engine;

  function App() {
    this.canvas = document.getElementById("c");
    this.ren = new E.Renderer(this.canvas);
    this.scene = new Scene();
    this.cam = E.makeCamera();
    this.orbit = true;
    this.paused = false;
    this.speed = 1;
    this.last = 0;
    this.fps = 0;
    this.fpsAcc = 0;
    this.fpsFrames = 0;
    this.fpsTime = 0;
    this.polyCount = 0;
    this.bindUI();
    this.onResize = this.onResize.bind(this);
    window.addEventListener("resize", this.onResize);
    this.last = performance.now();
    var self = this;
    this.raf = requestAnimationFrame(function (t) { self.frame(t); });
  }

  App.prototype.onResize = function () {
    this.ren.resize();
  };

  App.prototype.bindUI = function () {
    var self = this;
    this.elFps = document.getElementById("fps");
    this.elPolys = document.getElementById("polys");
    this.elParts = document.getElementById("parts");
    this.btnPause = document.getElementById("btnPause");
    this.btnOrbit = document.getElementById("btnOrbit");
    this.btnReset = document.getElementById("btnReset");
    this.slider = document.getElementById("speed");

    this.btnPause.addEventListener("click", function () {
      self.paused = !self.paused;
      self.btnPause.textContent = self.paused ? "Resume" : "Pause";
      self.btnPause.classList.toggle("active", self.paused);
    });
    this.btnOrbit.addEventListener("click", function () {
      self.orbit = !self.orbit;
      self.btnOrbit.textContent = self.orbit ? "Orbit ON" : "Orbit OFF";
      self.btnOrbit.classList.toggle("active", self.orbit);
    });
    this.btnReset.addEventListener("click", function () {
      self.scene.reset();
      self.cam.angle = 0;
      self.speed = 1;
      self.slider.value = "1";
      self.paused = false;
      self.btnPause.textContent = "Pause";
      self.btnPause.classList.remove("active");
    });
    this.slider.addEventListener("input", function () {
      self.speed = parseFloat(self.slider.value);
    });
  };

  App.prototype.frame = function (now) {
    var self = this;
    var dt = (now - this.last) / 1000;
    this.last = now;
    if (dt > 0.1) dt = 0.1;

    // FPS
    this.fpsFrames++;
    this.fpsTime += dt;
    if (this.fpsTime >= 0.5) {
      this.fps = Math.round(this.fpsFrames / this.fpsTime);
      this.fpsFrames = 0;
      this.fpsTime = 0;
    }

    var sdt = dt * this.speed;
    if (!this.paused) {
      this.scene.update(sdt);
      if (this.orbit) E.updateCamera(this.cam, sdt);
    }

    var basis = E.cameraBasis(this.cam);
    var ctx = this.ren.ctx;
    // Clear with transparent so the CSS radial gradient shows through.
    ctx.clearRect(0, 0, this.ren.w, this.ren.h);
    this.polyCount = this.scene.render(this.ren, this.cam, basis);

    // HUD
    this.elFps.textContent = String(this.fps);
    this.elPolys.textContent = String(this.polyCount);
    this.elParts.textContent = String(this.scene.parts.length);

    this.raf = requestAnimationFrame(function (t) { self.frame(t); });
  };

  global.App = App;
  function start() {
    if (global.__appStarted) return;
    global.__appStarted = true;
    new App();
  }
  if (global.document) {
    if (global.document.readyState === "loading") {
      global.document.addEventListener("DOMContentLoaded", start);
    } else {
      start();
    }
  }
})(typeof window !== "undefined" ? window : this);
