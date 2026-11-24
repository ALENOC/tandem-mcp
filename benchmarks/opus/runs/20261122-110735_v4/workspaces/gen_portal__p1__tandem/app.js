// app.js - main loop, camera, HUD, and window.app API
(function (global) {
  'use strict';
  var E = global.Engine3D;
  var S = global.Scene;
  var v3 = E.v3;

  var canvas = document.getElementById('c');
  var ctx = canvas.getContext('2d');

  var el = {
    fps: document.getElementById('fps'),
    polys: document.getElementById('polys'),
    parts: document.getElementById('parts'),
    pause: document.getElementById('pause'),
    orbit: document.getElementById('orbit'),
    reset: document.getElementById('reset'),
    speed: document.getElementById('speed'),
    speedval: document.getElementById('speedval')
  };

  // ---- state ----
  var state = {
    paused: false,
    orbit: true,
    speed: 1,
    time: 0,
    camAngle: 0,
    lastPolys: 0
  };

  // ---- static geometry ----
  var boxFaces = S.buildBoxes();
  var stars = S.buildStars();
  var particles = S.buildParticles();

  // ---- canvas sizing (DPR capped at 2) ----
  var W = 0, H = 0, DPR = 1;
  function resize() {
    DPR = Math.min(2, global.devicePixelRatio || 1);
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

  // ---- background radial gradient ----
  function drawBackground() {
    var cx = W / 2, cy = H / 2;
    var outer = Math.max(W, H) * 0.75;
    var g = ctx.createRadialGradient(cx, cy, 0, cx, cy, outer);
    g.addColorStop(0, '#1a0b3d');
    g.addColorStop(0.5, '#0a0420');
    g.addColorStop(1, '#020008');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  }

  // ---- camera ----
  function makeCam(t) {
    var ang = state.camAngle;
    var r = 10;
    var h = 4.2 + 0.6 * Math.sin(t * 0.3);
    var eye = v3(Math.sin(ang) * r, h, Math.cos(ang) * r);
    var target = v3(0, 2.0, 0);
    return E.makeCamera(eye, target, v3(0, 1, 0));
  }

  // ---- stars ----
  function drawStars(cam, t) {
    for (var i = 0; i < stars.length; i++) {
      var st = stars[i];
      var p = v3(st.dir.x * 60, st.dir.y * 60, st.dir.z * 60);
      var vp = cam.toView(p);
      var pr = E.project(vp, W, H);
      if (!pr) continue;
      var tw = 0.3 + 0.7 * (0.5 + 0.5 * Math.sin(t * st.speed + st.phase));
      var c = E.hexToRgb(st.tint);
      ctx.globalAlpha = tw;
      ctx.fillStyle = E.rgba(c.r, c.g, c.b, 1);
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, st.size, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // ---- grid floor ----
  function drawGrid(cam, t) {
    var off = (t * 0.5) % 1;
    ctx.lineWidth = 1;
    // lines along x (varying z)
    for (var i = -12; i <= 12; i++) {
      var z = i + off;
      if (z > 12) continue;
      drawGridLine(cam, v3(-12, 0, z), v3(12, 0, z));
    }
    // lines along z (varying x)
    for (var j = -12; j <= 12; j++) {
      drawGridLine(cam, v3(j, 0, -12), v3(j, 0, 12));
    }
  }
  function drawGridLine(cam, a, b) {
    var pa = cam.toView(a);
    var pb = cam.toView(b);
    var A = E.project(pa, W, H);
    var B = E.project(pb, W, H);
    if (!A || !B) return;
    // alpha fades with distance from origin (use midpoint world distance)
    var mx = (a.x + b.x) / 2, mz = (a.z + b.z) / 2;
    var d = Math.sqrt(mx * mx + mz * mz);
    var alpha = 0.55 * (1 - Math.min(1, d / 12));
    if (alpha <= 0.01) return;
    ctx.strokeStyle = E.rgba(255, 43, 214, alpha);
    ctx.beginPath();
    ctx.moveTo(A.x, A.y);
    ctx.lineTo(B.x, B.y);
    ctx.stroke();
  }

  // ---- portal core disc ----
  function drawPortalCore(cam, t) {
    var c = cam.toView(v3(0, 2.4, 0));
    var pr = E.project(c, W, H);
    if (!pr) return;
    var pulse = 1 + 0.06 * Math.sin(2 * Math.PI * t / 1.6);
    var baseR = 1.1 * pulse;
    // screen radius: project a point offset by baseR in view space
    var edge = cam.toView(v3(0, 2.4 + baseR, 0));
    var pe = E.project(edge, W, H);
    var r = pe ? Math.abs(pe.y - pr.y) : baseR * 40;
    var g = ctx.createRadialGradient(pr.x, pr.y, 0, pr.x, pr.y, r);
    g.addColorStop(0, 'rgba(255,255,255,0.9)');
    g.addColorStop(0.5, 'rgba(0,240,255,0.55)');
    g.addColorStop(1, 'rgba(0,240,255,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(pr.x, pr.y, r, 0, Math.PI * 2);
    ctx.fill();
  }

  // ---- rings ----
  function drawRings(cam, t) {
    drawRing(cam, t, 1.25, '#00f0ff', 1.2, 0.35);
    drawRing(cam, t, 1.4, '#ff2bd6', -0.9, -0.35);
  }
  function drawRing(cam, t, radius, color, rotSpeed, tilt) {
    var rot = t * rotSpeed;
    var N = 48;
    var pts = [];
    for (var i = 0; i < N; i++) {
      var a = (i / N) * Math.PI * 2;
      // ring in local XY plane
      var lx = Math.cos(a) * radius;
      var ly = Math.sin(a) * radius;
      // rotate about Z by rot
      var rx = lx * Math.cos(rot) - ly * Math.sin(rot);
      var ry = lx * Math.sin(rot) + ly * Math.cos(rot);
      // tilt about X
      var ry2 = ry * Math.cos(tilt);
      var rz = ry * Math.sin(tilt);
      // world position at portal center
      var wp = v3(rx, 2.4 + ry2, rz);
      var vp = cam.toView(wp);
      pts.push(E.project(vp, W, H));
    }
    var c = E.hexToRgb(color);
    ctx.save();
    ctx.lineWidth = 2.5;
    ctx.strokeStyle = E.rgba(c.r, c.g, c.b, 0.9);
    ctx.shadowBlur = 18;
    ctx.shadowColor = E.rgba(c.r, c.g, c.b, 1);
    ctx.setLineDash([12, 8]);
    ctx.beginPath();
    var started = false;
    for (var k = 0; k < pts.length; k++) {
      var p = pts[k];
      if (!p) { started = false; continue; }
      if (!started) { ctx.moveTo(p.x, p.y); started = true; }
      else ctx.lineTo(p.x, p.y);
    }
    ctx.stroke();
    ctx.restore();
  }

  // ---- particles ----
  function updateParticles(dt) {
    for (var i = 0; i < particles.length; i++) {
      var p = particles[i];
      p.age += dt;
      if (p.age >= p.life) {
        S.spawnParticle(p);
        continue;
      }
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.z += p.vz * dt;
    }
  }
  function drawParticles(cam) {
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    for (var i = 0; i < particles.length; i++) {
      var p = particles[i];
      var vp = cam.toView(v3(p.x, p.y, p.z));
      var pr = E.project(vp, W, H);
      if (!pr) continue;
      var alpha = 1 - p.age / p.life;
      if (alpha <= 0) continue;
      // perspective scale: closer (more negative z) => bigger
      var scale = Math.max(0.3, Math.min(3, 2 / (-vp.z) * 4));
      var r = p.r * scale;
      var col = p.cyan ? [0, 240, 255] : [255, 43, 214];
      ctx.fillStyle = E.rgba(col[0], col[1], col[2], alpha);
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  // ---- crystals ----
  function drawCrystals(cam, t) {
    var faces = [];
    for (var i = 0; i < 6; i++) {
      var ang = (i / 6) * Math.PI * 2 + t * 0.6;
      var bob = 0.25 * Math.sin((2 * Math.PI / 3) * t + i * (Math.PI / 3));
      var cx = Math.cos(ang) * 3.2;
      var cz = Math.sin(ang) * 3.2;
      var cy = 2.4 + bob;
      var color = S.CRYSTAL_COLORS[i];
      // spin about Y: rotate the 4 equator points
      var spin = t * 1.5;
      var r = 0.28, h = 0.45;
      var top = v3(cx, cy + h, cz);
      var bot = v3(cx, cy - h, cz);
      var eq = [];
      for (var k = 0; k < 4; k++) {
        var a = k * (Math.PI / 2) + spin;
        eq.push(v3(cx + Math.cos(a) * r, cy, cz + Math.sin(a) * r));
      }
      for (var m = 0; m < 4; m++) {
        var a = eq[m], b = eq[(m + 1) % 4];
        faces.push({ verts: [top, a, b], color: color, edge: color });
        faces.push({ verts: [bot, b, a], color: color, edge: color });
      }
    }
    return E.renderFaces(ctx, cam, faces, W, H);
  }

  // ---- HUD ----
  var fpsFrames = 0, fpsLast = global.performance.now();
  function updateHUD() {
    var now = global.performance.now();
    fpsFrames++;
    if (now - fpsLast >= 500) {
      var fps = Math.round(fpsFrames * 1000 / (now - fpsLast));
      el.fps.textContent = 'FPS: ' + fps;
      fpsFrames = 0;
      fpsLast = now;
    }
    el.polys.textContent = 'POLYS: ' + state.lastPolys;
    el.parts.textContent = 'PARTS: ' + particles.length;
  }

  // ---- main loop ----
  var lastNow = global.performance.now();
  function frame() {
    var now = global.performance.now();
    var dtReal = (now - lastNow) / 1000;
    lastNow = now;
    if (dtReal > 0.1) dtReal = 0.1;

    if (!state.paused) {
      var dt = dtReal * state.speed;
      state.time += dt;
      if (state.orbit) state.camAngle += 0.25 * dt;
      updateParticles(dt);
    }

    var t = state.time;
    var cam = makeCam(t);

    drawBackground();
    drawStars(cam, t);
    drawGrid(cam, t);

    // draw order: grid (done), boxes, portal core, rings, crystals, particles
    var boxCount = E.renderFaces(ctx, cam, boxFaces, W, H);
    drawPortalCore(cam, t);
    drawRings(cam, t);
    var crysCount = drawCrystals(cam, t);
    drawParticles(cam);

    state.lastPolys = boxCount + crysCount;
    updateHUD();

    global.requestAnimationFrame(frame);
  }

  // ---- controls ----
  el.pause.addEventListener('click', function () {
    state.paused = !state.paused;
    el.pause.textContent = state.paused ? 'Resume' : 'Pause';
  });
  el.orbit.addEventListener('click', function () {
    state.orbit = !state.orbit;
    el.orbit.textContent = state.orbit ? 'Orbit ON' : 'Orbit OFF';
  });
  el.speed.addEventListener('input', function () {
    state.speed = parseFloat(el.speed.value);
    el.speedval.textContent = state.speed.toFixed(1) + 'x';
  });
  function doReset() {
    state.paused = false;
    state.orbit = true;
    state.speed = 1;
    state.time = 0;
    state.camAngle = 0;
    el.pause.textContent = 'Pause';
    el.orbit.textContent = 'Orbit ON';
    el.speed.value = '1';
    el.speedval.textContent = '1.0x';
  }
  el.reset.addEventListener('click', doReset);

  // ---- public API ----
  global.app = {
    get paused() { return state.paused; },
    get orbit() { return state.orbit; },
    get speed() { return state.speed; },
    get time() { return state.time; },
    get camAngle() { return state.camAngle; },
    stars: stars,
    particles: particles,
    boxFaces: boxFaces.length,
    crystalTris: 48,
    rings: 2,
    lastPolys: 0,
    reset: doReset
  };
  // keep lastPolys live
  Object.defineProperty(global.app, 'lastPolys', {
    get: function () { return state.lastPolys; }
  });

  global.requestAnimationFrame(frame);
})(window);
