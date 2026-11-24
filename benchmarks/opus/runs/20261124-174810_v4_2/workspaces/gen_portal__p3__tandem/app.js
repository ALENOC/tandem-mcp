// app.js - main application: canvas, render loop, HUD, controls
(function (global) {
  "use strict";
  var E = global.Engine3D;
  var v3 = E.vec3;

  var canvas = document.getElementById("c");
  var ctx = canvas.getContext("2d");

  var elFps = document.getElementById("fps");
  var elPolys = document.getElementById("polys");
  var elParts = document.getElementById("parts");
  var btnPause = document.getElementById("btnPause");
  var btnOrbit = document.getElementById("btnOrbit");
  var btnReset = document.getElementById("btnReset");
  var speedInput = document.getElementById("speed");

  var scene = Scene.build();

  // ---- app state ----
  var app = {
    paused: false,
    orbit: true,
    speed: 1,
    camAngle: 0,
    stars: scene.stars,
    particles: scene.particles,
    crystals: scene.crystals,
    polyCount: 0,
    fps: 0
  };
  global.app = app;

  var W = 0, H = 0, DPR = 1;
  var FOV = 60 * Math.PI / 180;
  var CAM_RADIUS = 16;
  var CAM_HEIGHT = 6;
  var PORTAL = scene.portal;

  function resize() {
    DPR = global.devicePixelRatio || 1;
    W = global.innerWidth;
    H = global.innerHeight;
    canvas.width = Math.floor(W * DPR);
    canvas.height = Math.floor(H * DPR);
    canvas.style.width = W + "px";
    canvas.style.height = H + "px";
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  }
  global.addEventListener("resize", resize);
  resize();

  // ---- background: dark radial gradient space ----
  function drawBackground() {
    var g = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.75);
    g.addColorStop(0, "#1a0b3a");
    g.addColorStop(1, "#05020f");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  }

  // ---- stars: 180 twinkling ----
  function drawStars(t) {
    for (var i = 0; i < app.stars.length; i++) {
      var s = app.stars[i];
      var a = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * s.speed + s.phase));
      ctx.globalAlpha = a;
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.arc(s.x * W, s.y * H, s.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // ---- cyber grid floor ----
  function drawGrid(cam) {
    var N = 12;
    var span = 24;
    var step = span / N;
    var half = span / 2;
    ctx.lineWidth = 1;
    for (var i = 0; i <= N; i++) {
      var off = -half + i * step;
      // lines along x (varying z)
      drawGridLine(cam, v3(-half, 0, off), v3(half, 0, off), i);
      // lines along z (varying x)
      drawGridLine(cam, v3(off, 0, -half), v3(off, 0, half), i);
    }
  }
  function drawGridLine(cam, a, b, i) {
    var pa = E.project(cam, a, W, H, FOV);
    var pb = E.project(cam, b, W, H, FOV);
    var dist = (pa.z + pb.z) / 2;
    var fade = Math.max(0, 1 - dist / 34);
    if (fade <= 0) return;
    var col = (i % 2 === 0) ? "0,240,255" : "150,60,255";
    ctx.strokeStyle = "rgba(" + col + "," + (0.5 * fade).toFixed(3) + ")";
    ctx.beginPath();
    ctx.moveTo(pa.x, pa.y);
    ctx.lineTo(pb.x, pb.y);
    ctx.stroke();
  }

  // ---- portal core: glowing disc + two counter-rotating rings ----
  function drawPortalCore(cam, t) {
    var c = E.project(cam, v3(PORTAL.x, PORTAL.y, PORTAL.z), W, H, FOV);
    var base = (H / 2) / Math.tan(FOV / 2);
    var R = (2.4 / c.z) * base;
    if (R < 1) R = 1;

    // glowing center disc
    var g = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, R);
    g.addColorStop(0, "rgba(255,255,255,0.95)");
    g.addColorStop(0.4, "rgba(0,240,255,0.55)");
    g.addColorStop(1, "rgba(255,43,214,0.0)");
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(c.x, c.y, R, 0, Math.PI * 2);
    ctx.fill();

    // ring 1: cyan, rotating one way
    drawRing(c, R * 1.15, t * 0.8, "#00f0ff");
    // ring 2: magenta, rotating the other way
    drawRing(c, R * 1.45, -t * 0.6, "#ff2bd6");
  }
  function drawRing(c, R, rot, color) {
    var segs = 40;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.shadowColor = color;
    ctx.shadowBlur = 14;
    ctx.beginPath();
    for (var i = 0; i <= segs; i++) {
      var a = rot + (i / segs) * Math.PI * 2;
      var x = c.x + Math.cos(a) * R;
      var y = c.y + Math.sin(a) * R * 0.98;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.restore();
  }

  // ---- collect + draw all solid polygons (boxes + crystals) ----
  function drawSolids(cam, t) {
    var polys = [];
    var total = 0;

    // structure boxes
    for (var bi = 0; bi < scene.structure.length; bi++) {
      var box = scene.structure[bi];
      for (var fi = 0; fi < box.faces.length; fi++) {
        var wv = box.faces[fi];
        total++;
        if (!E.isFrontFace(cam, wv)) continue;
        var pv = [];
        for (var k = 0; k < wv.length; k++) pv.push(E.project(cam, wv[k], W, H, FOV));
        var n = E.v3norm(E.v3cross(E.v3sub(wv[1], wv[0]), E.v3sub(wv[2], wv[0])));
        var col = E.shade(box.base, n, E.LIGHT);
        polys.push({
          pts: pv,
          fill: "rgb(" + (col.r | 0) + "," + (col.g | 0) + "," + (col.b | 0) + ")",
          edge: box.edge
        });
      }
    }

    // crystals (orbiting + spinning octahedra)
    for (var ci = 0; ci < app.crystals.length; ci++) {
      var cr = app.crystals[ci];
      var ang = cr.angle + t * 0.5;
      var cx = Math.cos(ang) * cr.radius;
      var cz = Math.sin(ang) * cr.radius;
      var cy = cr.height + Math.sin(t * 1.3 + cr.spin) * 0.4;
      var oct = Scene.makeCrystal(cx, cy, cz, cr.size, cr.color);
      for (var ti = 0; ti < oct.tris.length; ti++) {
        var wv = oct.tris[ti];
        total++;
        if (!E.isFrontFace(cam, wv)) continue;
        var pv = [];
        for (var k = 0; k < wv.length; k++) pv.push(E.project(cam, wv[k], W, H, FOV));
        var n = E.v3norm(E.v3cross(E.v3sub(wv[1], wv[0]), E.v3sub(wv[2], wv[0])));
        var col = E.shade({ r: 120, g: 200, b: 255 }, n, E.LIGHT);
        polys.push({
          pts: pv,
          fill: "rgba(" + (col.r | 0) + "," + (col.g | 0) + "," + (col.b | 0) + ",0.85)",
          edge: cr.color
        });
      }
    }

    E.depthSort(polys, cam);
    for (var d = 0; d < polys.length; d++) {
      E.drawPoly(ctx, polys[d].pts, polys[d].fill, polys[d].edge, polys[d].edge);
    }
    app.polyCount = total;
  }

  // ---- particles: rising, respawn at bottom ----
  function updateParticles(dt) {
    for (var i = 0; i < app.particles.length; i++) {
      var p = app.particles[i];
      p.y += p.vy * dt;
      if (p.y >= p.max) {
        p.y = 0;
        p.x = (Math.random() - 0.5) * 6;
        p.z = (Math.random() - 0.5) * 4;
      }
    }
  }
  function drawParticles(cam) {
    for (var i = 0; i < app.particles.length; i++) {
      var p = app.particles[i];
      var pr = E.project(cam, v3(p.x, p.y, p.z), W, H, FOV);
      var size = Math.max(1, 2.5 / pr.z * 8);
      ctx.globalAlpha = 0.8;
      ctx.fillStyle = p.hue;
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, size, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // ---- main loop ----
  var last = global.performance.now();
  var fpsAccum = 0, fpsFrames = 0, fpsTimer = 0;

  function frame(now) {
    var rawDt = (now - last) / 1000;
    last = now;
    if (rawDt > 0.1) rawDt = 0.1;

    // fps
    fpsFrames++;
    fpsTimer += rawDt;
    if (fpsTimer >= 0.5) {
      app.fps = Math.round(fpsFrames / fpsTimer);
      fpsFrames = 0;
      fpsTimer = 0;
    }

    var dt = app.paused ? 0 : rawDt * app.speed;
    var t = now / 1000;

    if (!app.paused) {
      if (app.orbit) app.camAngle += dt * 0.4;
      updateParticles(dt);
    }

    // camera orbiting at constant radius, looking at portal center
    var eye = v3(
      Math.cos(app.camAngle) * CAM_RADIUS,
      CAM_HEIGHT,
      Math.sin(app.camAngle) * CAM_RADIUS
    );
    var cam = E.lookAt(eye, v3(PORTAL.x, PORTAL.y, PORTAL.z), v3(0, 1, 0));

    drawBackground();
    drawStars(t);
    drawGrid(cam);
    drawPortalCore(cam, t);
    drawSolids(cam, t);
    drawParticles(cam);

    // HUD
    elFps.textContent = app.fps;
    elPolys.textContent = app.polyCount;
    elParts.textContent = app.particles.length;

    global.requestAnimationFrame(frame);
  }

  // ---- controls ----
  btnPause.addEventListener("click", function () {
    app.paused = !app.paused;
    btnPause.textContent = app.paused ? "Resume" : "Pause";
  });
  btnOrbit.addEventListener("click", function () {
    app.orbit = !app.orbit;
    btnOrbit.textContent = app.orbit ? "Orbit ON" : "Orbit OFF";
  });
  btnReset.addEventListener("click", function () {
    app.camAngle = 0;
    app.paused = false;
    app.orbit = true;
    app.speed = 1;
    speedInput.value = "1";
    btnPause.textContent = "Pause";
    btnOrbit.textContent = "Orbit ON";
  });
  speedInput.addEventListener("input", function () {
    app.speed = parseFloat(speedInput.value);
  });

  global.requestAnimationFrame(frame);
})(window);
