/* app.js - render loop, orbiting camera, input, HUD wiring */
(function (global) {
  "use strict";
  var E = global.Engine;
  var S = global.Scene;
  var TAU = E.TAU;

  var canvas = document.getElementById("c");
  var ctx = canvas.getContext("2d");

  var elFps = document.getElementById("fps");
  var elPolys = document.getElementById("polys");
  var elParts = document.getElementById("parts");
  var btnPause = document.getElementById("btnPause");
  var btnOrbit = document.getElementById("btnOrbit");
  var btnReset = document.getElementById("btnReset");
  var speedEl = document.getElementById("speed");

  // ---- state ----
  var state = {
    paused: false,
    orbit: true,
    speed: 1,
    time: 0,
    last: 0,
    fps: 0,
    fpsAcc: 0,
    fpsN: 0,
    fpsT: 0
  };

  var cam = E.makeCamera();
  var camHome = { yaw: 0.6, pitch: 0.32, dist: 11 };

  // ---- scene data ----
  var monument = S.buildMonument();
  var crystals = S.makeCrystals();
  var rings = S.makeRings();
  var stars = S.makeStars();
  var particles = S.makeParticles();

  var LIGHT = E.norm(E.v3(-0.5, 0.9, 0.6));

  // ---- sizing ----
  var W = 0, H = 0, DPR = 1;
  function resize() {
    DPR = Math.min(2, global.devicePixelRatio || 1);
    W = global.innerWidth;
    H = global.innerHeight;
    canvas.width = Math.round(W * DPR);
    canvas.height = Math.round(H * DPR);
    canvas.style.width = W + "px";
    canvas.style.height = H + "px";
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  }
  global.addEventListener("resize", resize);
  resize();

  // ---- input: drag orbit + wheel zoom ----
  var dragging = false, lastX = 0, lastY = 0;
  function onDown(x, y) {
    dragging = true;
    lastX = x; lastY = y;
    canvas.classList.add("dragging");
  }
  function onMove(x, y) {
    if (!dragging) return;
    var dx = x - lastX, dy = y - lastY;
    lastX = x; lastY = y;
    cam.yaw += dx * 0.005;
    cam.pitch += dy * 0.005;
    if (cam.pitch < 0.05) cam.pitch = 0.05;
    if (cam.pitch > 1.35) cam.pitch = 1.35;
  }
  function onUp() {
    dragging = false;
    canvas.classList.remove("dragging");
  }
  canvas.addEventListener("mousedown", function (e) { onDown(e.clientX, e.clientY); });
  global.addEventListener("mousemove", function (e) { onMove(e.clientX, e.clientY); });
  global.addEventListener("mouseup", onUp);
  canvas.addEventListener("touchstart", function (e) {
    var t = e.touches[0]; onDown(t.clientX, t.clientY);
  }, { passive: true });
  canvas.addEventListener("touchmove", function (e) {
    var t = e.touches[0]; onMove(t.clientX, t.clientY);
    e.preventDefault();
  }, { passive: false });
  canvas.addEventListener("touchend", onUp);
  canvas.addEventListener("wheel", function (e) {
    e.preventDefault();
    cam.dist += e.deltaY * 0.01;
    if (cam.dist < 5) cam.dist = 5;
    if (cam.dist > 26) cam.dist = 26;
  }, { passive: false });

  // ---- HUD buttons ----
  btnPause.addEventListener("click", function () {
    state.paused = !state.paused;
    btnPause.textContent = state.paused ? "Resume" : "Pause";
    btnPause.classList.toggle("active", state.paused);
  });
  btnOrbit.addEventListener("click", function () {
    state.orbit = !state.orbit;
    btnOrbit.textContent = state.orbit ? "Orbit ON" : "Orbit OFF";
    btnOrbit.classList.toggle("active", state.orbit);
  });
  btnReset.addEventListener("click", function () {
    cam.yaw = camHome.yaw;
    cam.pitch = camHome.pitch;
    cam.dist = camHome.dist;
    state.time = 0;
    state.speed = 1;
    speedEl.value = "1";
  });
  speedEl.addEventListener("input", function () {
    state.speed = parseFloat(speedEl.value);
  });

  // ---- background: dark radial-gradient space ----
  function drawBackground() {
    var g = ctx.createRadialGradient(W / 2, H * 0.42, 40, W / 2, H / 2, Math.max(W, H) * 0.75);
    g.addColorStop(0, "#0b1230");
    g.addColorStop(0.45, "#070b1e");
    g.addColorStop(1, "#02030a");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  }

  // ---- stars (twinkling, drawn in screen space from projected positions) ----
  function drawStars() {
    for (var i = 0; i < stars.length; i++) {
      var st = stars[i];
      var cs = E.toCamera(E.v3(st.x, st.y, st.z), cam);
      if (cs.z < 1) continue;
      var p = E.project(cs, cam, W, H);
      if (p.x < -20 || p.x > W + 20 || p.y < -20 || p.y > H + 20) continue;
      var tw = 0.4 + 0.6 * (0.5 + 0.5 * Math.sin(state.time * st.sp + st.tw));
      var r = st.sz * tw;
      ctx.globalAlpha = tw;
      ctx.fillStyle = "#cfeeff";
      ctx.beginPath();
      ctx.arc(p.x, p.y, r, 0, TAU);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // ---- perspective cyber grid floor ----
  function drawGrid() {
    var N = 12, span = 24, step = span / N;
    var half = span / 2;
    ctx.lineWidth = 1;
    for (var i = 0; i <= N; i++) {
      var a = -half + i * step;
      // lines along X (varying z)
      drawGridLine(E.v3(-half, 0, a), E.v3(half, 0, a), i);
      // lines along Z (varying x)
      drawGridLine(E.v3(a, 0, -half), E.v3(a, 0, half), i);
    }
  }
  function drawGridLine(p0, p1, i) {
    var c0 = E.toCamera(p0, cam);
    var c1 = E.toCamera(p1, cam);
    if (c0.z < 0.2 || c1.z < 0.2) return;
    var s0 = E.project(c0, cam, W, H);
    var s1 = E.project(c1, cam, W, H);
    var t = (i % 4 === 0) ? 0.55 : 0.22;
    ctx.strokeStyle = "rgba(34,230,255," + t + ")";
    ctx.beginPath();
    ctx.moveTo(s0.x, s0.y);
    ctx.lineTo(s1.x, s1.y);
    ctx.stroke();
  }

  // ---- portal core: swirling energy glow + 2 counter-rotating rings ----
  function drawPortalCore() {
    var cy = 2.6;
    var center = E.toCamera(E.v3(0, cy, 0), cam);
    var p = E.project(center, cam, W, H);
    var baseR = (cam.fov / center.z) * 1.4;

    // swirling energy glow (concentric pulsing rings)
    var t = state.time;
    for (var k = 0; k < 5; k++) {
      var ph = (t * 0.8 + k * 0.2) % 1;
      var rr = baseR * (0.2 + 0.8 * ph);
      var alpha = (1 - ph) * 0.5;
      var hue = (t * 40 + k * 30) % 360;
      ctx.strokeStyle = "hsla(" + hue + ",100%,65%," + alpha + ")";
      ctx.lineWidth = 2 + (1 - ph) * 3;
      ctx.beginPath();
      ctx.arc(p.x, p.y, rr, 0, TAU);
      ctx.stroke();
    }
    // bright core
    var cg = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, baseR * 0.5);
    cg.addColorStop(0, "rgba(255,255,255,0.9)");
    cg.addColorStop(0.5, "rgba(120,220,255,0.5)");
    cg.addColorStop(1, "rgba(120,220,255,0)");
    ctx.fillStyle = cg;
    ctx.beginPath();
    ctx.arc(p.x, p.y, baseR * 0.5, 0, TAU);
    ctx.fill();

    // two counter-rotating 3D rings (torus of small segments)
    var polys = [];
    for (var ri = 0; ri < rings.length; ri++) {
      var ring = rings[ri];
      var rot = t * ring.speed * ring.dir + ring.tilt;
      var SEG = ring.segs.length;
      var segSize = 0.16;
      for (var s = 0; s < SEG; s++) {
        var ang = ring.segs[s] + rot;
        var x = Math.cos(ang) * ring.radius;
        var z = Math.sin(ang) * ring.radius;
        var y = cy + Math.sin(ang * 2 + rot) * 0.15;
        // small box segment
        var faces = E.makeBox(x, y, z, segSize, segSize, segSize);
        var base = ring.dir === 1 ? [255, 61, 240] : [34, 230, 255];
        var edge = ring.dir === 1 ? "rgba(255,120,255,0.9)" : "rgba(120,255,255,0.9)";
        var glow = ring.dir === 1 ? "rgba(255,61,240,0.8)" : "rgba(34,230,255,0.8)";
        var ps = E.buildPolys(faces, cam, W, H, LIGHT, base, edge, glow);
        for (var q = 0; q < ps.length; q++) polys.push(ps[q]);
      }
    }
    E.renderPolys(ctx, polys);
    return polys.length;
  }

  // ---- crystals: 6 orbiting octahedra ----
  function drawCrystals() {
    var polys = [];
    var t = state.time;
    for (var i = 0; i < crystals.length; i++) {
      var c = crystals[i];
      var ang = c.phase + t * 0.5;
      var x = Math.cos(ang) * c.radius;
      var z = Math.sin(ang) * c.radius;
      var y = c.height + Math.sin(t * 1.2 + c.phase) * 0.2;
      var faces = E.makeOctahedron(x, y, z, c.r);
      // rotate octahedron about its own center for spin
      var cx = x, cy = y, cz = z;
      var spin = t * c.spin;
      var cs = Math.cos(spin), sn = Math.sin(spin);
      for (var f = 0; f < faces.length; f++) {
        for (var v = 0; v < faces[f].v.length; v++) {
          var pt = faces[f].v[v];
          var dx = pt.x - cx, dz = pt.z - cz;
          pt.x = cx + dx * cs - dz * sn;
          pt.z = cz + dx * sn + dz * cs;
        }
        // recompute normal
        var A = faces[f].v[0], B = faces[f].v[1], C = faces[f].v[2];
        faces[f].n = E.norm(E.cross(E.sub(B, A), E.sub(C, A)));
      }
      var base = [180, 90, 255];
      var edge = "rgba(160,220,255,0.95)";
      var glow = "rgba(120,180,255,0.9)";
      var ps = E.buildPolys(faces, cam, W, H, LIGHT, base, edge, glow);
      for (var q = 0; q < ps.length; q++) polys.push(ps[q]);
    }
    E.renderPolys(ctx, polys);
    return polys.length;
  }

  // ---- monument: 6 boxes = 36 faces ----
  function drawMonument() {
    var polys = [];
    for (var i = 0; i < monument.length; i++) {
      var base = [40, 70, 120];
      var edge = "rgba(34,230,255,0.85)";
      var glow = "rgba(34,230,255,0.6)";
      var ps = E.buildPolys(monument[i], cam, W, H, LIGHT, base, edge, glow);
      for (var q = 0; q < ps.length; q++) polys.push(ps[q]);
    }
    E.renderPolys(ctx, polys);
    return polys.length;
  }

  // ---- rising neon particles ----
  function drawParticles(dt) {
    var t = state.time;
    for (var i = 0; i < particles.length; i++) {
      var pt = particles[i];
      if (!state.paused) {
        pt.y += pt.vy * dt * state.speed;
        pt.life -= dt * 0.15 * state.speed;
        if (pt.life <= 0 || pt.y > 6.5) {
          particles[i] = S.spawnParticle(false);
          continue;
        }
      }
      var cs = E.toCamera(E.v3(pt.x, pt.y, pt.z), cam);
      if (cs.z < 0.2) continue;
      var p = E.project(cs, cam, W, H);
      var a = Math.max(0, Math.min(1, pt.life));
      var col = pt.hue === 0 ? "255,61,240" : "34,230,255";
      ctx.globalAlpha = a;
      ctx.fillStyle = "rgba(" + col + ",0.9)";
      ctx.shadowColor = "rgba(" + col + ",0.9)";
      ctx.shadowBlur = 8;
      ctx.beginPath();
      ctx.arc(p.x, p.y, pt.sz * a, 0, TAU);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    ctx.shadowBlur = 0;
  }

  // ---- main loop ----
  function frame(now) {
    if (!state.last) state.last = now;
    var dt = (now - state.last) / 1000;
    state.last = now;
    if (dt > 0.1) dt = 0.1;

    // fps
    state.fpsAcc += dt; state.fpsN++;
    state.fpsT += dt;
    if (state.fpsT >= 0.5) {
      state.fps = Math.round(state.fpsN / state.fpsAcc);
      state.fpsAcc = 0; state.fpsN = 0; state.fpsT = 0;
    }

    if (!state.paused) {
      state.time += dt * state.speed;
      if (state.orbit) cam.yaw += dt * 0.25 * state.speed;
    }

    drawBackground();
    drawStars();
    drawGrid();
    var nCore = drawPortalCore();
    var nMon = drawMonument();
    var nCry = drawCrystals();
    drawParticles(dt);

    // HUD
    elFps.textContent = state.fps;
    elPolys.textContent = nCore + nMon + nCry;
    elParts.textContent = particles.length;

    global.requestAnimationFrame(frame);
  }
  global.requestAnimationFrame(frame);
})(typeof window !== "undefined" ? window : this);
