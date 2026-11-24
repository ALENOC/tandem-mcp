// app.js - main loop, HUD, controls, rendering
(function (global) {
  'use strict';
  var E = global.Engine3D;
  var v3 = E.vec3;

  var canvas = document.getElementById('c');
  var ctx = canvas.getContext('2d');
  var el = {
    title: document.getElementById('title'),
    fps: document.getElementById('fps'),
    polys: document.getElementById('polys'),
    parts: document.getElementById('parts'),
    pauseBtn: document.getElementById('pauseBtn'),
    orbitBtn: document.getElementById('orbitBtn'),
    resetBtn: document.getElementById('resetBtn'),
    speed: document.getElementById('speed')
  };

  var scene = global.Scene.makeScene();
  var cam = E.makeCamera();
  var DEF = { pitch: 0.32, dist: 16 };

  var app = {
    boxFaces: scene.boxFaces,
    crystals: scene.crystals,
    crystalTris: scene.crystalTris,
    stars: scene.stars,
    particles: scene.particles,
    rings: scene.rings,
    camera: cam,
    paused: false,
    orbit: true,
    speed: 1,
    time: 0
  };
  global.app = app;

  var W = 0, H = 0, DPR = 1;
  function resize() {
    DPR = global.devicePixelRatio || 1;
    W = global.innerWidth;
    H = global.innerHeight;
    canvas.width = Math.round(W * DPR);
    canvas.height = Math.round(H * DPR);
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  }
  global.addEventListener('resize', resize);
  resize();

  // ---- background ----
  function drawBackground() {
    var g = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.72);
    g.addColorStop(0, '#1a0b3d');
    g.addColorStop(1, '#05010f');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  }

  function drawStars() {
    for (var i = 0; i < app.stars.length; i++) {
      var s = app.stars[i];
      var a = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(app.time * s.sp + s.tw));
      ctx.globalAlpha = a;
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(s.x * W, s.y * H * 0.9, s.size, s.size);
    }
    ctx.globalAlpha = 1;
  }

  // ---- grid floor ----
  function drawGrid() {
    var span = 24, step = 1.2;
    var off = (app.time * 0.6) % step;
    ctx.lineWidth = 1;
    for (var i = -span; i <= span; i += step) {
      var z1 = i - off, z2 = i + step - off;
      drawGridLine(v3(-span, 0, z1), v3(span, 0, z1));
      drawGridLine(v3(-span, 0, z2), v3(span, 0, z2));
      var x1 = i - off, x2 = i + step - off;
      drawGridLine(v3(x1, 0, -span), v3(x2, 0, -span));
      drawGridLine(v3(x1, 0, span), v3(x2, 0, span));
    }
  }
  function drawGridLine(a, b) {
    var ca = cam.toCam(a), cb = cam.toCam(b);
    if (ca.z <= 0.05 || cb.z <= 0.05) return;
    var pa = cam.project(ca, W, H), pb = cam.project(cb, W, H);
    if (!pa || !pb) return;
    var d = (ca.z + cb.z) / 2;
    var alpha = Math.max(0, 1 - d / 34);
    ctx.globalAlpha = alpha * 0.8;
    ctx.strokeStyle = '#ff2bd6';
    ctx.beginPath();
    ctx.moveTo(pa.x, pa.y);
    ctx.lineTo(pb.x, pb.y);
    ctx.stroke();
    ctx.globalAlpha = 1;
  }

  // ---- portal core ----
  function drawPortalCore() {
    var c = cam.toCam(v3(0, 3.4, 0));
    if (c.z <= 0.05) return;
    var p = cam.project(c, W, H);
    if (!p) return;
    var f = (H * 0.5) / Math.tan(cam.fov * 0.5);
    var r = (2.4 * f) / c.z;
    var g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, r);
    g.addColorStop(0, 'rgba(0,240,255,0.95)');
    g.addColorStop(0.5, 'rgba(120,80,255,0.55)');
    g.addColorStop(1, 'rgba(138,43,226,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.fill();
  }

  // ---- rings: projected 3D circles of points ----
  function drawRings() {
    for (var i = 0; i < app.rings.length; i++) {
      var ring = app.rings[i];
      var N = 48, pts = [];
      for (var k = 0; k < N; k++) {
        var a = ring.angle + (k / N) * Math.PI * 2;
        var w = v3(Math.cos(a) * ring.radius, ring.y + Math.sin(a) * ring.radius * 0.15, Math.sin(a) * ring.radius);
        var cp = cam.toCam(w);
        if (cp.z <= 0.05) { pts.push(null); continue; }
        pts.push(cam.project(cp, W, H));
      }
      ctx.save();
      ctx.shadowColor = 'rgb(' + ring.color[0] + ',' + ring.color[1] + ',' + ring.color[2] + ')';
      ctx.shadowBlur = 18;
      ctx.strokeStyle = 'rgb(' + ring.color[0] + ',' + ring.color[1] + ',' + ring.color[2] + ')';
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      var started = false;
      for (var j = 0; j < N; j++) {
        var p = pts[j];
        if (!p) { started = false; continue; }
        if (!started) { ctx.moveTo(p.x, p.y); started = true; }
        else ctx.lineTo(p.x, p.y);
      }
      ctx.stroke();
      ctx.restore();
    }
  }

  // ---- particles ----
  function drawParticles() {
    for (var i = 0; i < app.particles.length; i++) {
      var p = app.particles[i];
      var w = v3(p.x, p.y, p.z);
      var cp = cam.toCam(w);
      if (cp.z <= 0.05) continue;
      var pr = cam.project(cp, W, H);
      if (!pr) continue;
      var a = Math.max(0, 1 - p.life / p.max);
      ctx.globalAlpha = a * 0.9;
      ctx.fillStyle = '#00f0ff';
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, 2.2, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // ---- update ----
  function update(dt) {
    if (app.orbit) cam.yaw += 0.25 * dt;
    for (var i = 0; i < app.rings.length; i++) {
      app.rings[i].angle += app.rings[i].dir * 0.9 * dt;
    }
    for (var p = 0; p < app.particles.length; p++) {
      var pt = app.particles[p];
      pt.y += pt.vy * dt;
      pt.life += dt;
      if (pt.life >= pt.max || pt.y > 5.5) {
        pt.x = (Math.random() - 0.5) * 3.4;
        pt.z = (Math.random() - 0.5) * 3.4;
        pt.y = 0.2;
        pt.life = 0;
        pt.max = 3 + Math.random() * 2;
      }
    }
  }

  // ---- render ----
  var lastPolys = 0;
  function render() {
    cam.update();
    drawBackground();
    drawStars();
    drawGrid();
    drawPortalCore();

    var polys = [];
    var i, b, f;
    for (i = 0; i < scene.boxes.length; i++) {
      b = scene.boxes[i];
      for (f = 0; f < b.faces.length; f++) {
        polys.push({ pts: b.faces[f], color: b.color, edge: b.edge, glow: b.glow });
      }
    }
    for (i = 0; i < scene.crystals.length; i++) {
      var cr = scene.crystals[i];
      var ang = app.time * 0.5 + cr.phase;
      var cx = Math.cos(ang) * cr.radius;
      var cz = Math.sin(ang) * cr.radius;
      var cy = cr.height + Math.sin(app.time * cr.bob + cr.phase) * 0.4;
      var spin = app.time * cr.spin;
      var faces = global.Scene.octaFaces(0, 0, 0, 0.55, 0.85, 0.55);
      for (f = 0; f < faces.length; f++) {
        var tri = faces[f];
        var wpts = [];
        for (var t = 0; t < tri.length; t++) {
          var q = tri[t];
          var rx = E.rotateY(q, spin);
          var ry = E.rotateX(rx, spin * 0.7);
          wpts.push(v3(ry.x + cx, ry.y + cy, ry.z + cz));
        }
        polys.push({ pts: wpts, color: cr.color, edge: cr.edge, glow: cr.glow });
      }
    }
    var built = E.buildPolys(cam, polys, W, H);
    E.drawPolys(ctx, built);
    lastPolys = built.length;

    drawRings();
    drawParticles();
  }

  // ---- HUD ----
  var fpsAcc = 0, fpsCount = 0, fpsVal = 0, fpsTimer = 0;
  function updateHUD(dt) {
    fpsAcc += dt; fpsCount++;
    fpsTimer += dt;
    if (fpsTimer >= 0.5) {
      fpsVal = Math.round(fpsCount / fpsAcc);
      fpsAcc = 0; fpsCount = 0; fpsTimer = 0;
    }
    el.fps.textContent = 'FPS: ' + fpsVal;
    el.polys.textContent = 'POLYS: ' + lastPolys;
    el.parts.textContent = 'PARTS: ' + app.particles.length;
  }

  // ---- controls ----
  el.pauseBtn.addEventListener('click', function () {
    app.paused = !app.paused;
    el.pauseBtn.textContent = app.paused ? 'Resume' : 'Pause';
  });
  el.orbitBtn.addEventListener('click', function () {
    app.orbit = !app.orbit;
    el.orbitBtn.textContent = app.orbit ? 'Orbit ON' : 'Orbit OFF';
  });
  el.resetBtn.addEventListener('click', function () {
    cam.yaw = 0;
    cam.pitch = DEF.pitch;
    cam.dist = DEF.dist;
    app.speed = 1;
    el.speed.value = '1';
    app.paused = false;
    el.pauseBtn.textContent = 'Pause';
  });
  el.speed.addEventListener('input', function () {
    app.speed = parseFloat(el.speed.value);
  });

  // ---- main loop ----
  var last = global.performance.now();
  function frame(now) {
    var raw = (now - last) / 1000;
    last = now;
    if (raw > 0.1) raw = 0.1;
    if (!app.paused) {
      var dt = raw * app.speed;
      app.time += dt;
      update(dt);
    }
    render();
    updateHUD(raw);
    global.requestAnimationFrame(frame);
  }
  global.requestAnimationFrame(frame);
})(window);
