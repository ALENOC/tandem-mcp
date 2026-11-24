// app.js - application: canvas setup, camera, animation loop, HUD, window.app.
// Depends on window.Engine3D and window.Scene.

(function (global) {
  "use strict";
  var E = global.Engine3D;
  var S = global.Scene;

  var canvas = document.getElementById("c");
  var ctx = canvas.getContext("2d");

  // ---- HUD elements --------------------------------------------------------
  var fpsVal = document.getElementById("fpsVal");
  var polysVal = document.getElementById("polysVal");
  var partsVal = document.getElementById("partsVal");
  var pauseBtn = document.getElementById("pauseBtn");
  var orbitBtn = document.getElementById("orbitBtn");
  var resetBtn = document.getElementById("resetBtn");
  var speedInput = document.getElementById("speed");

  // ---- app state -----------------------------------------------------------
  var app = {
    paused: false,
    orbit: true,
    speed: 1,
    time: 0,
    camAngle: 0.6,
    stars: S.STARS,
    particles: S.PARTICLES,
    boxFaces: 36,
    crystalTris: 48,
    polys: 0,
    fps: 0
  };
  global.app = app;

  var DEFAULT_CAM_ANGLE = 0.6;
  var FOV = (55 * Math.PI) / 180;
  var LIGHT = E.v3norm(E.vec3(0.4, 0.9, 0.5));

  // ---- canvas sizing (devicePixelRatio aware) ------------------------------
  var W = 0, H = 0, DPR = 1;
  function resize() {
    DPR = global.devicePixelRatio || 1;
    W = global.innerWidth;
    H = global.innerHeight;
    // Keep the backing store at CSS pixel size so the harness can read it
    // with getImageData; the context is scaled by DPR for crisp rendering.
    canvas.width = W;
    canvas.height = H;
    canvas.style.width = W + "px";
    canvas.style.height = H + "px";
  }
  global.addEventListener("resize", resize);
  resize();

  // ---- camera --------------------------------------------------------------
  function camera() {
    var ang = app.camAngle;
    var dist = 9.5;
    var bob = Math.sin(app.time * 0.8) * 0.25;
    var eye = E.vec3(Math.sin(ang) * dist, 3.4 + bob, Math.cos(ang) * dist);
    var target = E.vec3(0, 2.0, 0);
    return E.makeCamera(eye, target, E.vec3(0, 1, 0));
  }

  // ---- background ----------------------------------------------------------
  function drawBackground() {
    var g = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.72);
    g.addColorStop(0, "#1a0b3a");
    g.addColorStop(1, "#05010f");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  }

  // ---- stars ---------------------------------------------------------------
  function drawStars() {
    for (var i = 0; i < app.stars.length; i++) {
      var st = app.stars[i];
      var a = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(app.time * st.speed + st.phase));
      ctx.globalAlpha = a;
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.arc(st.x * W, st.y * H, st.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // ---- grid floor ----------------------------------------------------------
  // Draw a world-space segment, clipped against the camera near plane.
  function gridSeg(p0, p1, cam) {
    var a = cam.toCamera(p0), b = cam.toCamera(p1), NEAR = 0.1;
    if (a.z < NEAR && b.z < NEAR) return;
    if (a.z < NEAR || b.z < NEAR) {
      var t = (NEAR - a.z) / (b.z - a.z);
      var q = E.vec3(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, NEAR);
      if (a.z < NEAR) a = q; else b = q;
    }
    var pa = E.project(a, cam, W, H, FOV), pb = E.project(b, cam, W, H, FOV);
    ctx.moveTo(pa.x, pa.y);
    ctx.lineTo(pb.x, pb.y);
  }

  function drawGrid(cam) {
    var ext = S.GRID.extent;
    var step = S.GRID.step;
    var off = (app.time * 0.4) % step;
    ctx.save();
    ctx.strokeStyle = S.GRID.color;
    ctx.globalAlpha = S.GRID.alpha;
    ctx.lineWidth = 1;
    ctx.shadowBlur = 6;
    ctx.shadowColor = S.GRID.color;
    var n = Math.floor(ext / step);
    var i, a, b;
    // lines along X (varying z)
    for (i = -n; i <= n; i++) {
      var z = i * step + off;
      if (z > ext) z -= ext * 2;
      ctx.beginPath();
      gridSeg(E.vec3(-ext, 0, z), E.vec3(ext, 0, z), cam);
      ctx.stroke();
    }
    // lines along Z (varying x)
    for (i = -n; i <= n; i++) {
      var x = i * step;
      ctx.beginPath();
      gridSeg(E.vec3(x, 0, -ext), E.vec3(x, 0, ext), cam);
      ctx.stroke();
    }
    ctx.restore();
  }

  // ---- boxes ---------------------------------------------------------------
  function drawBoxes(cam, polys) {
    for (var bi = 0; bi < S.BOXES.length; bi++) {
      var box = S.BOXES[bi];
      var faces = E.boxFaces(box.c[0], box.c[1], box.c[2], box.s[0], box.s[1], box.s[2]);
      for (var fi = 0; fi < faces.length; fi++) {
        var f = faces[fi];
        // backface culling: skip faces whose normal points away from camera
        var c0 = f.v[0];
        var toCam = E.v3sub(cam.eye, c0);
        if (E.v3dot(f.n, toCam) <= 0) continue;
        var pts = [];
        var depth = 0;
        for (var k = 0; k < f.v.length; k++) {
          var cp = cam.toCamera(f.v[k]);
          var sp = E.project(cp, cam, W, H, FOV);
          pts.push(sp);
          depth += cp.z;
        }
        depth /= f.v.length;
        var lam = E.lambert(f.n, LIGHT);
        var factor = 0.35 + 0.65 * lam;
        polys.push({
          pts: pts,
          z: depth,
          fill: E.shade(box.face, factor),
          stroke: box.edge,
          glow: 10,
          glowColor: box.edge,
          lw: 1.5
        });
      }
    }
  }

  // ---- crystals ------------------------------------------------------------
  function drawCrystals(cam, polys) {
    for (var i = 0; i < S.CRYSTALS.length; i++) {
      var cr = S.CRYSTALS[i];
      var ang = cr.baseAngle + app.time * 0.5;
      var cx = Math.cos(ang) * cr.radius;
      var cz = Math.sin(ang) * cr.radius;
      var cy = cr.y + Math.sin(app.time * 1.3 + i) * 0.15;
      var spin = app.time * cr.spin;
      var base = E.octaFaces(cr.size);
      for (var fi = 0; fi < base.length; fi++) {
        var tri = base[fi];
        var pts = [];
        var depth = 0;
        var nrm = E.v3norm(E.v3cross(E.v3sub(tri[1], tri[0]), E.v3sub(tri[2], tri[0])));
        for (var k = 0; k < 3; k++) {
          var v = tri[k];
          var rv = E.rotY(v, spin);
          rv = E.rotX(rv, spin * 0.7);
          var wp = E.vec3(rv.x + cx, rv.y + cy, rv.z + cz);
          var cp = cam.toCamera(wp);
          var sp = E.project(cp, cam, W, H, FOV);
          pts.push(sp);
          depth += cp.z;
        }
        depth /= 3;
        // backface cull using rotated normal
        var rn = E.rotY(nrm, spin);
        rn = E.rotX(rn, spin * 0.7);
        var toCam = E.v3sub(cam.eye, E.vec3(cx, cy, cz));
        if (E.v3dot(rn, toCam) <= 0) continue;
        var lam = E.lambert(rn, LIGHT);
        var factor = 0.4 + 0.6 * lam;
        polys.push({
          pts: pts,
          z: depth,
          fill: E.shade(cr.color, factor),
          stroke: cr.color,
          glow: 12,
          glowColor: cr.color,
          lw: 1.2
        });
      }
    }
  }

  // ---- portal core ---------------------------------------------------------
  function drawPortal(cam) {
    var p = S.PORTAL;
    var cp = cam.toCamera(E.vec3(p.x, p.y, p.z));
    var sp = E.project(cp, cam, W, H, FOV);
    var pulse = 0.75 + 0.25 * Math.sin(app.time * 2.2);
    var r = (p.radius * (H / 2) / Math.tan(FOV / 2)) / cp.z;
    var g = ctx.createRadialGradient(sp.x, sp.y, 0, sp.x, sp.y, r);
    g.addColorStop(0, "rgba(255,255,255," + (0.95 * pulse) + ")");
    g.addColorStop(0.45, "rgba(138,43,226," + (0.7 * pulse) + ")");
    g.addColorStop(1, "rgba(138,43,226,0)");
    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(sp.x, sp.y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  // ---- rings ---------------------------------------------------------------
  function drawRings(cam) {
    for (var ri = 0; ri < S.RINGS.length; ri++) {
      var ring = S.RINGS[ri];
      var rot = app.time * ring.speed;
      var seg = ring.segments;
      ctx.save();
      ctx.strokeStyle = ring.color;
      ctx.lineWidth = 2;
      ctx.shadowBlur = 14;
      ctx.shadowColor = ring.color;
      ctx.globalAlpha = 0.9;
      ctx.beginPath();
      var prev = null;
      for (var i = 0; i <= seg; i++) {
        var a = (i / seg) * Math.PI * 2 + rot;
        var wp = E.vec3(
          S.PORTAL.x + Math.cos(a) * ring.radius,
          S.PORTAL.y + Math.sin(a) * ring.radius,
          S.PORTAL.z
        );
        var cp = cam.toCamera(wp);
        var sp = E.project(cp, cam, W, H, FOV);
        if (prev) {
          ctx.moveTo(prev.x, prev.y);
          ctx.lineTo(sp.x, sp.y);
        }
        prev = sp;
      }
      ctx.stroke();
      ctx.restore();
    }
  }

  // ---- particles -----------------------------------------------------------
  function drawParticles(cam, dt) {
    for (var i = 0; i < app.particles.length; i++) {
      var pt = app.particles[i];
      if (!app.paused) {
        pt.y += pt.vy * dt;
        pt.life += dt * 0.35;
        if (pt.y > 4.2 || pt.life > 1) {
          var np = S.makeParticle(false);
          app.particles[i] = np;
          continue;
        }
      }
      var cp = cam.toCamera(E.vec3(pt.x, pt.y, pt.z));
      if (cp.z < 0.1) continue;
      var sp = E.project(cp, cam, W, H, FOV);
      var fade = 1 - pt.life;
      if (fade < 0) fade = 0;
      ctx.globalAlpha = fade;
      ctx.fillStyle = pt.hue;
      ctx.shadowBlur = 8;
      ctx.shadowColor = pt.hue;
      ctx.beginPath();
      ctx.arc(sp.x, sp.y, pt.size, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    ctx.shadowBlur = 0;
  }

  // ---- main frame ----------------------------------------------------------
  var lastT = global.performance.now();
  var fpsAccum = 0, fpsFrames = 0, fpsTimer = 0;

  function frame(now) {
    var rawDt = (now - lastT) / 1000;
    lastT = now;
    if (rawDt > 0.1) rawDt = 0.1;

    // FPS (measured on real frames)
    fpsFrames++;
    fpsTimer += rawDt;
    if (fpsTimer >= 0.5) {
      app.fps = Math.round(fpsFrames / fpsTimer);
      fpsFrames = 0;
      fpsTimer = 0;
    }

    if (!app.paused) {
      var dt = rawDt * app.speed;
      app.time += dt;
      if (app.orbit) {
        app.camAngle += dt * 0.35;
      }
    }

    render();

    // HUD
    fpsVal.textContent = String(app.fps);
    polysVal.textContent = String(app.polys);
    partsVal.textContent = String(app.particles.length);

    // While paused, render one frozen frame and stop scheduling so the page
    // goes idle (lets the harness capture a stable frame). Resume re-arms it.
    if (!app.paused) {
      global.requestAnimationFrame(frame);
    }
  }

  function render() {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    drawBackground();
    drawStars();

    var cam = camera();
    drawGrid(cam);

    var polys = [];
    drawBoxes(cam, polys);
    drawCrystals(cam, polys);
    E.drawPolys(ctx, polys);
    app.polys = polys.length;

    drawPortal(cam);
    drawRings(cam);
    drawParticles(cam, app.paused ? 0 : (1 / 60) * app.speed);
  }

  // ---- controls ------------------------------------------------------------
  pauseBtn.addEventListener("click", function () {
    app.paused = !app.paused;
    pauseBtn.textContent = app.paused ? "Resume" : "Pause";
    if (!app.paused) {
      lastT = 0;
      global.requestAnimationFrame(frame);
    }
  });
  orbitBtn.addEventListener("click", function () {
    app.orbit = !app.orbit;
    orbitBtn.textContent = app.orbit ? "Orbit ON" : "Orbit OFF";
  });
  resetBtn.addEventListener("click", function () {
    app.time = 0;
    app.camAngle = DEFAULT_CAM_ANGLE;
    app.speed = 1;
    speedInput.value = "1";
    app.paused = false;
    pauseBtn.textContent = "Pause";
    lastT = 0;
    global.requestAnimationFrame(frame);
  });
  speedInput.addEventListener("input", function () {
    app.speed = parseFloat(speedInput.value);
    if (isNaN(app.speed)) app.speed = 1;
  });

  global.requestAnimationFrame(frame);
})(window);
