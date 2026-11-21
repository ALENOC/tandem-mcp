/* app.js - render loop, camera orbit, HUD controls */
(function (global) {
  "use strict";
  var E = global.Engine3D;
  var S = global.Scene;

  var canvas = document.getElementById("c");
  var ctx = canvas.getContext("2d");
  var elFps = document.getElementById("fps");
  var elPolys = document.getElementById("polys");
  var elParts = document.getElementById("parts");
  var btnPause = document.getElementById("btn-pause");
  var btnOrbit = document.getElementById("btn-orbit");
  var btnReset = document.getElementById("btn-reset");
  var speedEl = document.getElementById("speed");

  var state = S.build();
  var lightDir = E.normalize([0.35, 0.85, 0.4]);
  var W = 0, H = 0;

  function resize() {
    W = canvas.width = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }
  window.addEventListener("resize", resize);
  resize();

  function rgb(c) { return "rgb(" + (c[0] | 0) + "," + (c[1] | 0) + "," + (c[2] | 0) + ")"; }

  // Collect a world-space face into the render list.
  function addFace(list, verts, base, edge, glow) {
    var n = E.faceNormal(verts[0], verts[1], verts[2]);
    list.push({ verts: verts, base: base, edge: edge, glow: glow, normal: n });
  }

  // Project all faces, cull back-facing, compute depth, sort far->near.
  function renderFaces(list, basis) {
    var out = [];
    for (var i = 0; i < list.length; i++) {
      var f = list[i];
      var v = f.verts;
      // back-face cull: keep faces whose normal points toward camera
      var toCam = [
        basis.pos[0] - v[0][0], basis.pos[1] - v[0][1], basis.pos[2] - v[0][2]
      ];
      if (E.dot(f.normal, toCam) <= 0) continue;
      var pts = [];
      var depth = 0;
      var ok = true;
      for (var j = 0; j < v.length; j++) {
        var p = E.project(v[j], basis, W, H, state.cam.fov);
        if (!p) { ok = false; break; }
        pts.push(p);
        depth += p.z;
      }
      if (!ok) continue;
      depth /= v.length;
      out.push({ pts: pts, depth: depth, base: f.base, edge: f.edge, glow: f.glow, normal: f.normal });
    }
    E.sortFaces(out);
    for (var k = 0; k < out.length; k++) {
      var o = out[k];
      var col = E.shade(o.base, o.normal, lightDir);
      E.drawPoly(ctx, o.pts, rgb(col), rgb(o.edge), o.glow, rgb(o.edge), 1.2);
    }
    return out.length;
  }

  function drawGrid(basis) {
    ctx.save();
    ctx.strokeStyle = "rgba(0,229,255,0.35)";
    ctx.lineWidth = 1;
    ctx.shadowColor = "rgba(0,229,255,0.6)";
    ctx.shadowBlur = 6;
    for (var i = 0; i < state.grid.length; i++) {
      var a = E.project(state.grid[i][0], basis, W, H, state.cam.fov);
      var b = E.project(state.grid[i][1], basis, W, H, state.cam.fov);
      if (!a || !b) continue;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawStars() {
    for (var i = 0; i < state.stars.length; i++) {
      var s = state.stars[i];
      var tw = 0.4 + 0.6 * (0.5 + 0.5 * Math.sin(state.t * s.sp + s.ph));
      E.drawGlow(ctx, s.x * W, s.y * H, s.r, "rgba(200,230,255,1)", tw);
    }
  }

  function drawCore(basis) {
    var c = E.project([0, 5, 0], basis, W, H, state.cam.fov);
    if (!c) return;
    var pulse = 0.7 + 0.3 * Math.sin(state.t * 3);
    E.drawGlow(ctx, c.x, c.y, 26 * pulse, "rgba(120,240,255,0.9)", 0.9);
    E.drawGlow(ctx, c.x, c.y, 14 * pulse, "rgba(255,255,255,0.95)", 1);
  }

  function drawParts(basis) {
    for (var i = 0; i < state.parts.length; i++) {
      var p = state.parts[i];
      var pr = E.project([p.x, p.y, p.z], basis, W, H, state.cam.fov);
      if (!pr) continue;
      var a = 0.5 + 0.5 * Math.sin(state.t * 2 + p.ph);
      E.drawGlow(ctx, pr.x, pr.y, p.r * 40, "rgba(0,229,255,1)", 0.35 + 0.5 * a);
    }
  }

  function frame() {
    var basis = E.cameraBasis(state.cam);
    ctx.clearRect(0, 0, W, H);

    drawStars();
    drawGrid(basis);

    // ---- gather all 3D faces ----
    var list = [];
    var i, j;

    // monument (36 faces)
    for (i = 0; i < state.monument.length; i++) {
      var m = state.monument[i];
      for (j = 0; j < m.faces.length; j++) {
        addFace(list, m.faces[j], m.faces[j].length === 4 ? m.base || [40, 60, 120] : [40, 60, 120], m.edge, 8);
      }
    }

    // crystals (48 triangles)
    for (i = 0; i < state.crystals.length; i++) {
      var cr = state.crystals[i];
      var ang = cr.angle + state.t * 0.6;
      var cx = Math.cos(ang) * cr.radius;
      var cz = Math.sin(ang) * cr.radius;
      var cy = cr.y + Math.sin(state.t * 1.2 + i) * 0.4;
      var faces = S.octa(cx, cy, cz, cr.r, cr.base);
      for (j = 0; j < faces.length; j++) addFace(list, faces[j], cr.base, cr.base, 10);
    }

    // two counter-rotating rings (stood up, facing viewer)
    var ringA = state.ringA, ringB = state.ringB;
    for (j = 0; j < ringA.length; j++) {
      var fa = S.rotY(ringA[j], state.t * 0.9);
      fa = S.rotX(fa, Math.PI / 2);
      fa = fa.map(function (p) { return [p[0], p[1] + 5, p[2]]; });
      addFace(list, fa, [0, 229, 255], [0, 229, 255], 12);
    }
    for (j = 0; j < ringB.length; j++) {
      var fb = S.rotY(ringB[j], -state.t * 1.3);
      fb = S.rotX(fb, Math.PI / 2);
      fb = fb.map(function (p) { return [p[0], p[1] + 5, p[2]]; });
      addFace(list, fb, [255, 0, 200], [255, 0, 200], 12);
    }

    var polys = renderFaces(list, basis);
    drawCore(basis);
    drawParts(basis);

    elPolys.textContent = String(polys);
    elParts.textContent = String(state.parts.length);
  }

  // ---- animation loop ----
  var last = performance.now();
  var fpsAcc = 0, fpsCount = 0, fpsTimer = 0;

  function loop(now) {
    var dt = (now - last) / 1000;
    last = now;
    if (dt > 0.1) dt = 0.1;

    if (!state.paused) {
      state.t += dt * state.speed;
      if (state.orbit) state.cam.theta += dt * 0.3 * state.speed;
      // advance rising particles
      for (var i = 0; i < state.parts.length; i++) {
        var p = state.parts[i];
        p.y += p.vy * dt * state.speed;
        if (p.y > 14) { p.y = 0; p.x = (Math.random() - 0.5) * 8; p.z = (Math.random() - 0.5) * 8; }
      }
    }

    frame();

    // fps
    fpsAcc += dt; fpsCount++; fpsTimer += dt;
    if (fpsTimer >= 0.5) {
      var fps = Math.round(fpsCount / fpsAcc);
      elFps.textContent = String(fps);
      fpsAcc = 0; fpsCount = 0; fpsTimer = 0;
    }

    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);

  // ---- controls ----
  btnPause.addEventListener("click", function () {
    state.paused = !state.paused;
    btnPause.textContent = state.paused ? "Resume" : "Pause";
  });

  btnOrbit.addEventListener("click", function () {
    state.orbit = !state.orbit;
    btnOrbit.textContent = state.orbit ? "Orbit ON" : "Orbit OFF";
  });

  btnReset.addEventListener("click", function () {
    state.cam.theta = 0.7;
    state.cam.phi = 0.42;
    state.cam.radius = 30;
    state.speed = 1;
    speedEl.value = "1";
    if (state.paused) {
      state.paused = false;
      btnPause.textContent = "Pause";
    }
  });

  speedEl.addEventListener("input", function () {
    state.speed = parseFloat(speedEl.value);
  });

})(window);
