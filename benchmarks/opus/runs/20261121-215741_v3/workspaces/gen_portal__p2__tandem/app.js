// app.js - main application: canvas setup, render loop, HUD, controls
(function (global) {
  'use strict';
  var E = global.Engine3D;
  var S = global.Scene;

  var canvas = document.getElementById('c');
  var ctx = canvas.getContext('2d');

  var fpsEl = document.getElementById('fps');
  var polysEl = document.getElementById('polys');
  var partsEl = document.getElementById('parts');
  var pauseBtn = document.getElementById('pause');
  var orbitBtn = document.getElementById('orbit');
  var resetBtn = document.getElementById('reset');
  var speedEl = document.getElementById('speed');

  var scene = S.build();

  // ---- app state ----
  var app = {
    paused: false,
    orbit: true,
    speed: 1,
    time: 0,
    camAngle: 0,
    stars: scene.stars,
    particles: scene.particles,
    crystals: scene.crystals,
    boxFaces: scene.boxFaces,
    crystalTris: scene.crystalTris,
    polys: 0,
    fps: 0
  };
  global.app = app;

  // ---- canvas sizing with devicePixelRatio ----
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

  // ---- colours ----
  var BOX_BASE = [27, 16, 53];      // #1b1035
  var BOX_EDGE = [0, 240, 255];     // #00f0ff
  var GRID = [122, 0, 255];         // #7a00ff
  var PINK = [255, 43, 214];        // #ff2bd6
  var CYAN = [0, 240, 255];         // #00f0ff
  var PURPLE = [122, 0, 255];       // #7a00ff

  // ---- camera ----
  var CAM_RADIUS = 14;
  var TARGET = [0, 2.6, 0];
  function camera() {
    var a = app.camAngle;
    var bob = Math.sin(app.time * 0.6) * 0.35;
    var eye = [
      Math.sin(a) * CAM_RADIUS,
      3.2 + bob,
      Math.cos(a) * CAM_RADIUS
    ];
    return E.makeCamera(eye, TARGET, [0, 1, 0]);
  }
  function view() {
    return { cx: W / 2, cy: H / 2, focal: Math.min(W, H) * 1.15 };
  }

  // ---- background ----
  function drawBackground() {
    var g = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.72);
    g.addColorStop(0, '#1a0b2e');
    g.addColorStop(1, '#05010d');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  }

  // ---- stars ----
  function drawStars() {
    for (var i = 0; i < app.stars.length; i++) {
      var st = app.stars[i];
      var tw = 0.5 + 0.5 * Math.sin(app.time * st.speed + st.phase);
      var a = 0.15 + 0.85 * tw;
      ctx.globalAlpha = a;
      ctx.fillStyle = '#ffffff';
      ctx.beginPath();
      ctx.arc(st.x * W, st.y * H, st.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // ---- grid floor ----
  function drawGrid(cam, vw) {
    var N = 12;
    var span = 24;
    var y = -0.5;
    ctx.lineWidth = 1;
    for (var i = -N; i <= N; i++) {
      var off = i * (span / N);
      // lines along z
      var a1 = E.project([off, y, -span], cam, vw);
      var a2 = E.project([off, y, span], cam, vw);
      drawGridLine(a1, a2, y);
      // lines along x
      var b1 = E.project([-span, y, off], cam, vw);
      var b2 = E.project([span, y, off], cam, vw);
      drawGridLine(b1, b2, y);
    }
  }
  function drawGridLine(p1, p2, y) {
    var d1 = Math.max(0.001, p1.depth);
    var d2 = Math.max(0.001, p2.depth);
    var fade = Math.min(1, 14 / Math.max(d1, d2));
    var a = 0.05 + 0.5 * fade;
    ctx.strokeStyle = 'rgba(' + GRID[0] + ',' + GRID[1] + ',' + GRID[2] + ',' + a.toFixed(3) + ')';
    ctx.beginPath();
    ctx.moveTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
    ctx.stroke();
  }

  // ---- portal core ----
  function drawPortal(cam, vw) {
    var center = [0, 2.6, 0];
    var p = E.project(center, cam, vw);
    var f = vw.focal / Math.max(0.001, p.depth);
    var R = 1.9 * f;
    if (R <= 0) return;

    ctx.save();
    // glowing radial disc
    var g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, R);
    g.addColorStop(0, 'rgba(255,43,214,0.95)');
    g.addColorStop(0.55, 'rgba(122,0,255,0.55)');
    g.addColorStop(1, 'rgba(122,0,255,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(p.x, p.y, R, 0, Math.PI * 2);
    ctx.fill();

    // two concentric neon rings rotating in opposite directions
    ctx.shadowBlur = 18;
    // outer ring #00f0ff
    ctx.shadowColor = 'rgba(0,240,255,0.9)';
    ctx.strokeStyle = 'rgba(0,240,255,0.95)';
    ctx.lineWidth = 3;
    drawRing(p.x, p.y, R * 0.92, app.time * 0.8, 0.12, 10);
    // inner ring #ff2bd6
    ctx.shadowColor = 'rgba(255,43,214,0.9)';
    ctx.strokeStyle = 'rgba(255,43,214,0.95)';
    ctx.lineWidth = 2.5;
    drawRing(p.x, p.y, R * 0.62, -app.time * 1.1, 0.1, 8);
    ctx.restore();
  }
  function drawRing(cx, cy, r, rot, gap, segs) {
    ctx.beginPath();
    var start = rot;
    var end = rot + Math.PI * 2 * (1 - gap);
    ctx.arc(cx, cy, r, start, end);
    ctx.stroke();
  }

  // ---- boxes ----
  function drawBoxes(cam, vw) {
    var tris = [];
    for (var b = 0; b < scene.boxes.length; b++) {
      var box = scene.boxes[b];
      for (var f = 0; f < box.faces.length; f++) {
        var face = box.faces[f];
        var c = face.c;
        // two triangles per face
        addTri(tris, c[0], c[1], c[2], face.n, box);
        addTri(tris, c[0], c[2], c[3], face.n, box);
      }
    }
    E.sortTriangles(tris, cam);
    var drawn = 0;
    for (var i = 0; i < tris.length; i++) {
      var t = tris[i];
      if (!E.faceVisible(t.a, t.b, t.c, cam)) continue;
      var pa = E.project(t.a, cam, vw);
      var pb = E.project(t.b, cam, vw);
      var pc = E.project(t.c, cam, vw);
      var col = E.shade(t.n, BOX_BASE, [0, 0, 0]);
      ctx.fillStyle = E.rgb(col);
      ctx.beginPath();
      ctx.moveTo(pa.x, pa.y);
      ctx.lineTo(pb.x, pb.y);
      ctx.lineTo(pc.x, pc.y);
      ctx.closePath();
      ctx.fill();
      // neon edge lines
      ctx.strokeStyle = 'rgba(0,240,255,0.55)';
      ctx.lineWidth = 1;
      ctx.stroke();
      drawn++;
    }
    return drawn;
  }
  function addTri(tris, a, b, c, n, box) {
    tris.push({ a: a, b: b, c: c, n: n });
  }

  // ---- crystals ----
  function drawCrystals(cam, vw) {
    var tris = [];
    for (var i = 0; i < app.crystals.length; i++) {
      var cr = app.crystals[i];
      var ang = cr.angle + app.time * 0.5;
      var cx = Math.cos(ang) * cr.radius;
      var cz = Math.sin(ang) * cr.radius;
      var cy = cr.height + Math.sin(app.time * 0.8 + i) * 0.2;
      var spin = app.time * cr.spin;
      var s = cr.scale;
      var cosS = Math.cos(spin), sinS = Math.sin(spin);
      // octahedron vertices transformed
      var base = [
        [1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]
      ];
      var tv = [];
      for (var k = 0; k < 6; k++) {
        var p = base[k];
        var x = p[0] * s;
        var y = p[1] * s;
        var z = p[2] * s;
        // spin around Y
        var rx = x * cosS - z * sinS;
        var rz = x * sinS + z * cosS;
        tv.push([cx + rx, cy + y, cz + rz]);
      }
      var faces = [
        [2, 4, 0], [2, 1, 4], [2, 5, 1], [2, 0, 5],
        [3, 0, 4], [3, 4, 5], [3, 1, 4], [3, 5, 0]
      ];
      for (var f = 0; f < faces.length; f++) {
        var fc = faces[f];
        var a = tv[fc[0]], b = tv[fc[1]], c = tv[fc[2]];
        var n = E.normalize(E.cross(E.sub(b, a), E.sub(c, a)));
        tris.push({ a: a, b: b, c: c, n: n, color: cr.color });
      }
    }
    E.sortTriangles(tris, cam);
    var drawn = 0;
    for (var j = 0; j < tris.length; j++) {
      var t = tris[j];
      if (!E.faceVisible(t.a, t.b, t.c, cam)) continue;
      var pa = E.project(t.a, cam, vw);
      var pb = E.project(t.b, cam, vw);
      var pc = E.project(t.c, cam, vw);
      var col = E.shade(t.n, [10, 5, 20], t.color);
      ctx.fillStyle = E.rgb(col);
      ctx.beginPath();
      ctx.moveTo(pa.x, pa.y);
      ctx.lineTo(pb.x, pb.y);
      ctx.lineTo(pc.x, pc.y);
      ctx.closePath();
      ctx.fill();
      ctx.strokeStyle = 'rgba(255,255,255,0.35)';
      ctx.lineWidth = 0.8;
      ctx.stroke();
      drawn++;
    }
    return drawn;
  }

  // ---- particles ----
  function updateParticles(dt) {
    var maxH = 5.5;
    for (var i = 0; i < app.particles.length; i++) {
      var p = app.particles[i];
      p.y += p.vy * dt;
      if (p.y > maxH) {
        p.y = 0;
        p.x = (Math.random() - 0.5) * 8;
        p.z = (Math.random() - 0.5) * 8;
      }
    }
  }
  function drawParticles(cam, vw) {
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    for (var i = 0; i < app.particles.length; i++) {
      var p = app.particles[i];
      var pr = E.project([p.x, p.y, p.z], cam, vw);
      if (pr.depth <= 0.001) continue;
      var f = vw.focal / pr.depth;
      var r = Math.max(0.5, p.size * f * 0.05);
      var c = p.color;
      ctx.shadowBlur = 12;
      ctx.shadowColor = 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',0.9)';
      ctx.fillStyle = 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',0.85)';
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  // ---- HUD ----
  function updateHUD() {
    fpsEl.textContent = 'FPS: ' + Math.round(app.fps);
    polysEl.textContent = 'POLYS: ' + app.polys;
    partsEl.textContent = 'PARTS: ' + app.particles.length;
  }

  // ---- controls ----
  function syncButtons() {
    pauseBtn.textContent = app.paused ? 'Resume' : 'Pause';
    orbitBtn.textContent = app.orbit ? 'Orbit ON' : 'Orbit OFF';
  }
  pauseBtn.addEventListener('click', function () {
    app.paused = !app.paused;
    syncButtons();
  });
  orbitBtn.addEventListener('click', function () {
    app.orbit = !app.orbit;
    syncButtons();
  });
  resetBtn.addEventListener('click', function () {
    app.time = 0;
    app.camAngle = 0;
    app.speed = 1;
    app.paused = false;
    app.orbit = true;
    speedEl.value = '1';
    syncButtons();
  });
  speedEl.addEventListener('input', function () {
    app.speed = parseFloat(speedEl.value);
  });

  // ---- main loop ----
  var last = global.performance.now();
  var fpsAccum = 0, fpsFrames = 0, fpsTimer = 0;
  function frame(now) {
    var dt = (now - last) / 1000;
    last = now;
    if (dt > 0.1) dt = 0.1;

    // fps
    fpsFrames++;
    fpsTimer += dt;
    if (fpsTimer >= 0.5) {
      app.fps = fpsFrames / fpsTimer;
      fpsFrames = 0;
      fpsTimer = 0;
    }

    if (!app.paused) {
      app.time += dt * app.speed;
      if (app.orbit) {
        app.camAngle += dt * app.speed * 0.3;
      }
      updateParticles(dt * app.speed);
    }

    var cam = camera();
    var vw = view();

    drawBackground();
    drawStars();
    drawGrid(cam, vw);
    drawPortal(cam, vw);
    var boxCount = drawBoxes(cam, vw);
    var crysCount = drawCrystals(cam, vw);
    drawParticles(cam, vw);

    app.polys = boxCount + crysCount;
    updateHUD();

    global.requestAnimationFrame(frame);
  }
  global.requestAnimationFrame(frame);
})(window);
