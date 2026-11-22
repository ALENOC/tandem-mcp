// app.js
// Main loop, HUD, controls and window.app for the NEON PORTAL 3D demo.
// Uses Engine3D (math/projection/renderer) and Scene (geometry builders).

(function (global) {
  "use strict";
  var E = global.Engine3D;
  var S = global.Scene;

  var canvas = document.getElementById("c");
  var ctx = canvas.getContext("2d");

  var elFps = document.getElementById("fps");
  var elPolys = document.getElementById("polys");
  var elParts = document.getElementById("parts");
  var btnPause = document.getElementById("btnPause");
  var btnOrbit = document.getElementById("btnOrbit");
  var btnReset = document.getElementById("btnReset");
  var speedInput = document.getElementById("speed");

  // ---- Scene data ----
  var scene = S.buildScene();
  var boxFaces = scene.boxFaces;      // 36
  var crystalTris = scene.crystalTris; // 48

  // Crystal orbit parameters (6 crystals).
  var CRYSTAL_COLORS = [
    { r: 0, g: 240, b: 255 },   // cyan #00f0ff
    { r: 255, g: 43, b: 214 },  // magenta #ff2bd6
    { r: 157, g: 77, b: 255 }   // violet #9d4dff
  ];
  var crystals = [];
  for (var i = 0; i < 6; i++) {
    crystals.push({
      baseAngle: (i / 6) * Math.PI * 2,
      orbitSpeed: 0.6 + i * 0.05,
      spinSpeed: 1.2 + i * 0.15,
      radius: 3.6,
      height: 1.4 + (i % 3) * 0.35,
      size: 0.32,
      color: CRYSTAL_COLORS[i % 3]
    });
  }

  // ---- Stars: exactly 180, fixed screen positions, twinkle ----
  var stars = [];
  (function () {
    var seed = 1337;
    function rnd() {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      return (seed & 0xffff) / 0xffff;
    }
    for (var i = 0; i < 180; i++) {
      stars.push({
        x: rnd(),
        y: rnd(),
        r: 0.5 + rnd() * 1.4,
        phase: rnd() * Math.PI * 2,
        tw: 1.5 + rnd() * 2.5
      });
    }
  })();

  // ---- Particles: exactly 110, rise from platform, fade at top ----
  var particles = [];
  (function () {
    var seed = 9001;
    function rnd() {
      seed = (seed * 214013 + 2531011) & 0x7fffffff;
      return (seed & 0xffff) / 0xffff;
    }
    function spawn(p, initial) {
      p.x = (rnd() - 0.5) * 5.0;
      p.z = (rnd() - 0.5) * 5.0;
      p.y = initial ? rnd() * 4.0 : -0.4;
      p.vy = 0.5 + rnd() * 0.7;
      p.size = 0.05 + rnd() * 0.08;
      p.hue = rnd();
    }
    for (var i = 0; i < 110; i++) {
      var p = {};
      spawn(p, true);
      particles.push(p);
    }
  })();

  // ---- App state ----
  var app = {
    paused: false,
    orbit: true,
    speed: 1,
    camAngle: 0,
    stars: stars,
    particles: particles,
    crystals: crystals,
    boxFaces: boxFaces,
    crystalTris: crystalTris,
    polys: 0,
    frame: 0
  };
  global.app = app;

  // ---- Sizing (devicePixelRatio aware) ----
  var W = 0, H = 0, DPR = 1;
  function resize() {
    DPR = global.devicePixelRatio || 1;
    W = global.innerWidth;
    H = global.innerHeight;
    canvas.width = Math.round(W * DPR);
    canvas.height = Math.round(H * DPR);
    canvas.style.width = W + "px";
    canvas.style.height = H + "px";
  }
  global.addEventListener("resize", resize);
  resize();

  // ---- Simulation time (only advances when not paused) ----
  var simTime = 0;
  var lastTs = 0;
  var fps = 0;
  var fpsAccum = 0, fpsCount = 0, fpsTimer = 0;

  var FOCAL = 520;
  var TARGET = E.v3(0, 1.2, 0);
  var LIGHT = E.normalize(E.v3(0.4, 1.0, 0.6));

  // ---- Background: dark radial-gradient space ----
  function drawBackground() {
    var g = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.72);
    g.addColorStop(0, "#1a0b3a");
    g.addColorStop(1, "#05020f");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  }

  // ---- Stars (screen space, twinkle) ----
  function drawStars() {
    ctx.save();
    for (var i = 0; i < stars.length; i++) {
      var s = stars[i];
      var a = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(simTime * s.tw + s.phase));
      ctx.globalAlpha = a;
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.arc(s.x * W, s.y * H, s.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  // ---- Cyber grid floor on y=0 ----
  function drawGrid(cam, proj) {
    var span = 14, step = 1;
    ctx.save();
    ctx.lineWidth = 1;
    for (var i = -span; i <= span; i += step) {
      var alpha = 0.28 * (1 - Math.abs(i) / (span + 1));
      if (alpha <= 0.01) continue;
      ctx.globalAlpha = alpha;
      ctx.strokeStyle = "#00f0ff";
      ctx.shadowColor = "#00f0ff";
      ctx.shadowBlur = 6;
      // line along z at x=i
      var a1 = proj.project(cam.toCam(E.v3(i, 0, -span)));
      var b1 = proj.project(cam.toCam(E.v3(i, 0, span)));
      ctx.beginPath();
      ctx.moveTo(a1.x, a1.y);
      ctx.lineTo(b1.x, b1.y);
      ctx.stroke();
      // line along x at z=i
      var a2 = proj.project(cam.toCam(E.v3(-span, 0, i)));
      var b2 = proj.project(cam.toCam(E.v3(span, 0, i)));
      ctx.beginPath();
      ctx.moveTo(a2.x, a2.y);
      ctx.lineTo(b2.x, b2.y);
      ctx.stroke();
    }
    ctx.restore();
  }

  // ---- Portal core: glowing disc + two counter-rotating rings ----
  function drawPortal(cam, proj) {
    var center = proj.project(cam.toCam(E.v3(0, 1.3, 0)));
    var R = 1.15 * (FOCAL / cam.toCam(E.v3(0, 1.3, 0)).z);
    ctx.save();
    // glowing radial gradient disc
    var g = ctx.createRadialGradient(center.x, center.y, 0, center.x, center.y, R);
    g.addColorStop(0, "rgba(255,255,255,0.95)");
    g.addColorStop(0.35, "rgba(0,240,255,0.85)");
    g.addColorStop(0.7, "rgba(157,77,255,0.55)");
    g.addColorStop(1, "rgba(255,43,214,0.0)");
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(center.x, center.y, R, 0, Math.PI * 2);
    ctx.fill();

    // two concentric rings, opposite rotation, projected 3D polylines
    drawRing(cam, proj, 1.0, 0.0, 48, "#00f0ff", 14, 1.0);   // outer clockwise
    drawRing(cam, proj, 0.62, Math.PI / 8, 40, "#ff2bd6", 12, -1.0); // inner counter-clockwise
    ctx.restore();
  }

  function drawRing(cam, proj, radius, phase, seg, color, glow, dir) {
    var pts = [];
    for (var i = 0; i <= seg; i++) {
      var a = phase + dir * simTime * 1.4 + (i / seg) * Math.PI * 2;
      var p = E.v3(Math.cos(a) * radius, 1.3 + Math.sin(a) * radius, 0);
      pts.push(proj.project(cam.toCam(p)));
    }
    ctx.save();
    ctx.globalAlpha = 0.9;
    ctx.strokeStyle = color;
    ctx.shadowColor = color;
    ctx.shadowBlur = glow;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (var i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
    ctx.stroke();
    ctx.restore();
  }

  // ---- Particles (projected, rising, fading at top) ----
  function drawParticles(cam, proj) {
    ctx.save();
    for (var i = 0; i < particles.length; i++) {
      var p = particles[i];
      var cp = cam.toCam(E.v3(p.x, p.y, p.z));
      if (cp.z <= 0.1) continue;
      var pr = proj.project(cp);
      var t = (p.y + 0.4) / 4.4;
      if (t < 0) t = 0; if (t > 1) t = 1;
      var alpha = (1 - t) * 0.85;
      var size = p.size * (FOCAL / cp.z);
      var col = p.hue < 0.5 ? "#00f0ff" : "#ff2bd6";
      ctx.globalAlpha = alpha;
      ctx.fillStyle = col;
      ctx.shadowColor = col;
      ctx.shadowBlur = 8;
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, Math.max(0.5, size), 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  // ---- Boxes (flat shaded faces + neon edge glow) ----
  function drawBoxes(cam, proj, ren) {
    for (var bi = 0; bi < scene.boxes.length; bi++) {
      var item = scene.boxes[bi];
      var faces = item.box.faces;
      for (var fi = 0; fi < faces.length; fi++) {
        var f = faces[fi];
        var v = f.v;
        var n = f.n;
        // backface cull: skip faces pointing away from camera
        var centroid = E.v3(
          (v[0].x + v[1].x + v[2].x + v[3].x) / 4,
          (v[0].y + v[1].y + v[2].y + v[3].y) / 4,
          (v[0].z + v[1].z + v[2].z + v[3].z) / 4
        );
        var toCam = E.sub(cam.eye, centroid);
        if (E.dot(n, toCam) <= 0) continue;
        var ca = cam.toCam(v[0]);
        var cb = cam.toCam(v[1]);
        var cc = cam.toCam(v[2]);
        var cd = cam.toCam(v[3]);
        if (ca.z <= 0.1 || cb.z <= 0.1 || cc.z <= 0.1 || cd.z <= 0.1) continue;
        var color = E.shade(item.base, n, LIGHT);
        var glow = item.pillar ? 10 : 0;
        ren.triangle(ca, cb, cc, color, glow, 1);
        ren.triangle(ca, cc, cd, color, glow, 1);
        // neon edge glow on the box outline
        if (item.edge) {
          var edgeColor = item.pillar ? "#ff2bd6" : "#00f0ff";
          drawEdge(cam, proj, [v[0], v[1], v[2], v[3]], edgeColor);
        }
      }
    }
  }

  function drawEdge(cam, proj, verts, color) {
    ctx.save();
    ctx.globalAlpha = 0.5;
    ctx.strokeStyle = color;
    ctx.shadowColor = color;
    ctx.shadowBlur = 12;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    var p0 = proj.project(cam.toCam(verts[0]));
    ctx.moveTo(p0.x, p0.y);
    for (var i = 1; i < verts.length; i++) {
      var p = proj.project(cam.toCam(verts[i]));
      ctx.lineTo(p.x, p.y);
    }
    ctx.closePath();
    ctx.stroke();
    ctx.restore();
  }

  // ---- Crystals (octahedra, orbiting + spinning) ----
  function drawCrystals(cam, proj, ren) {
    var oct = S.octahedron(1);
    for (var i = 0; i < crystals.length; i++) {
      var c = crystals[i];
      var ang = c.baseAngle + simTime * c.orbitSpeed;
      var cx = Math.cos(ang) * c.radius;
      var cz = Math.sin(ang) * c.radius;
      var cy = c.height + Math.sin(simTime * 1.1 + i) * 0.2;
      var spin = simTime * c.spinSpeed;
      var cs = Math.cos(spin), sn = Math.sin(spin);
      var tris = oct.tris;
      for (var ti = 0; ti < tris.length; ti++) {
        var t = tris[ti];
        var a = rotY(t[0], cs, sn);
        var b = rotY(t[1], cs, sn);
        var d = rotY(t[2], cs, sn);
        a = E.add(E.scale(a, c.size), E.v3(cx, cy, cz));
        b = E.add(E.scale(b, c.size), E.v3(cx, cy, cz));
        d = E.add(E.scale(d, c.size), E.v3(cx, cy, cz));
        var ca = cam.toCam(a), cb = cam.toCam(b), cc = cam.toCam(d);
        if (ca.z <= 0.1 || cb.z <= 0.1 || cc.z <= 0.1) continue;
        var n = E.normalize(E.cross(E.sub(b, a), E.sub(d, a)));
        var color = E.shade(c.color, n, LIGHT);
        ren.triangle(ca, cb, cc, color, 12, 1);
      }
    }
  }

  function rotY(p, cs, sn) {
    return E.v3(p.x * cs + p.z * sn, p.y, -p.x * sn + p.z * cs);
  }

  // ---- HUD ----
  function updateHUD() {
    elFps.textContent = "FPS: " + Math.round(fps);
    elPolys.textContent = "POLYS: " + app.polys;
    elParts.textContent = "PARTS: " + particles.length;
  }

  // ---- Main loop ----
  function tick(ts) {
    if (!lastTs) lastTs = ts;
    var dt = (ts - lastTs) / 1000;
    lastTs = ts;
    if (dt > 0.1) dt = 0.1;

    // fps
    fpsAccum += dt; fpsCount++; fpsTimer += dt;
    if (fpsTimer >= 0.5) {
      fps = fpsCount / fpsAccum;
      fpsAccum = 0; fpsCount = 0; fpsTimer = 0;
    }

    if (!app.paused) {
      simTime += dt * app.speed;
      if (app.orbit) {
        app.camAngle += dt * app.speed * 0.4;
      }
      // advance particles
      for (var i = 0; i < particles.length; i++) {
        var p = particles[i];
        p.y += p.vy * dt * app.speed;
        if (p.y > 4.0) {
          p.x = (Math.random() - 0.5) * 5.0;
          p.z = (Math.random() - 0.5) * 5.0;
          p.y = -0.4;
          p.vy = 0.5 + Math.random() * 0.7;
        }
      }
      app.frame++;
    }

    render();
    updateHUD();
    global.requestAnimationFrame(tick);
  }

  function render() {
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    drawBackground();
    drawStars();

    // camera: orbit around Y, slight vertical bob, look at portal center
    var bob = Math.sin(simTime * 0.8) * 0.15;
    var dist = 9.5;
    var eye = E.v3(
      Math.sin(app.camAngle) * dist,
      2.2 + bob,
      Math.cos(app.camAngle) * dist
    );
    var cam = E.makeCamera(eye, TARGET, E.v3(0, 1, 0));
    var proj = E.makeProjection(FOCAL, W, H);
    var ren = new E.Renderer(ctx);
    ren.proj = proj;
    ren.begin();

    drawGrid(cam, proj);
    drawPortal(cam, proj);
    drawBoxes(cam, proj, ren);
    drawCrystals(cam, proj, ren);
    var n = ren.render();
    app.polys = n;
    drawParticles(cam, proj);
  }

  // ---- Controls ----
  btnPause.addEventListener("click", function () {
    app.paused = !app.paused;
    btnPause.textContent = app.paused ? "Play" : "Pause";
  });
  btnOrbit.addEventListener("click", function () {
    app.orbit = !app.orbit;
    btnOrbit.textContent = app.orbit ? "Orbit ON" : "Orbit OFF";
  });
  btnReset.addEventListener("click", function () {
    app.camAngle = 0;
    app.speed = 1;
    speedInput.value = "1";
    app.paused = false;
    btnPause.textContent = "Pause";
    app.orbit = true;
    btnOrbit.textContent = "Orbit ON";
  });
  speedInput.addEventListener("input", function () {
    app.speed = parseFloat(speedInput.value);
  });

  global.requestAnimationFrame(tick);
})(window);
