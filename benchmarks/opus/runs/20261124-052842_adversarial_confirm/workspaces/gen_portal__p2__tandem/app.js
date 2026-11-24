// app.js - neon portal demo: canvas setup, render loop, HUD, controls
(function (global) {
  'use strict';

  var E = global.Engine3D;

  var canvas = document.getElementById('c');
  var ctx = canvas.getContext('2d');

  var W = 0, H = 0, DPR = 1;

  // ---- pre-rendered glow sprites (drawn once, blitted each frame) ----
  function makeGlowSprite(color, core) {
    var size = 64;
    var cv = document.createElement('canvas');
    cv.width = size;
    cv.height = size;
    var c = cv.getContext('2d');
    var rgb = hexToRgb(color);
    var g = c.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    g.addColorStop(0, 'rgba(' + core[0] + ',' + core[1] + ',' + core[2] + ',1)');
    g.addColorStop(0.25, 'rgba(' + rgb[0] + ',' + rgb[1] + ',' + rgb[2] + ',0.85)');
    g.addColorStop(0.6, 'rgba(' + rgb[0] + ',' + rgb[1] + ',' + rgb[2] + ',0.35)');
    g.addColorStop(1, 'rgba(' + rgb[0] + ',' + rgb[1] + ',' + rgb[2] + ',0)');
    c.fillStyle = g;
    c.fillRect(0, 0, size, size);
    return cv;
  }

  var particleSprites = {};
  function particleSprite(color) {
    if (!particleSprites[color]) {
      var rgb = hexToRgb(color);
      particleSprites[color] = makeGlowSprite(color, [Math.min(255, rgb[0] + 120), Math.min(255, rgb[1] + 120), Math.min(255, rgb[2] + 120)]);
    }
    return particleSprites[color];
  }

  // portal disc sprite: white center -> violet -> transparent
  var portalSprite = (function () {
    var size = 256;
    var cv = document.createElement('canvas');
    cv.width = size;
    cv.height = size;
    var c = cv.getContext('2d');
    var g = c.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    g.addColorStop(0, 'rgba(255,255,255,0.95)');
    g.addColorStop(0.4, 'rgba(157,77,255,0.7)');
    g.addColorStop(1, 'rgba(157,77,255,0)');
    c.fillStyle = g;
    c.fillRect(0, 0, size, size);
    return cv;
  })();

  var bgGradient = null;

  function resize() {
    DPR = global.devicePixelRatio || 1;
    W = global.innerWidth;
    H = global.innerHeight;
    canvas.width = Math.floor(W * DPR);
    canvas.height = Math.floor(H * DPR);
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    bgGradient = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.75);
    bgGradient.addColorStop(0, '#1a0b2e');
    bgGradient.addColorStop(1, '#05010d');
  }
  resize();
  global.addEventListener('resize', resize);

  // ---- scene data ----
  var scene = global.Scene.buildScene();
  var boxes = scene.boxes;
  var crystals = scene.crystals;
  var stars = scene.stars;
  var particles = scene.particles;

  // ---- state ----
  var state = {
    paused: false,
    orbit: true,
    speed: 1,
    camAngle: 0,
    time: 0,
    frames: 0,
    polysDrawn: 0
  };

  var TARGET = [0, 3.5, 0];
  var CAM_RADIUS = 15;
  var CAM_Y = 5.5;
  var FOV = 1.05;
  var LIGHT = E.norm([0.4, 1.0, 0.6]);

  // ---- helpers ----
  function hexToRgb(hex) {
    var n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function rgba(hex, a) {
    var c = hexToRgb(hex);
    return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a + ')';
  }
  function shadeHex(hex, f) {
    var c = hexToRgb(hex);
    var r = Math.min(255, Math.round(c[0] * f));
    var g = Math.min(255, Math.round(c[1] * f));
    var b = Math.min(255, Math.round(c[2] * f));
    return 'rgb(' + r + ',' + g + ',' + b + ')';
  }
  function rotY(p, a) {
    var c = Math.cos(a), s = Math.sin(a);
    return [p[0] * c + p[2] * s, p[1], -p[0] * s + p[2] * c];
  }
  function rotX(p, a) {
    var c = Math.cos(a), s = Math.sin(a);
    return [p[0], p[1] * c - p[2] * s, p[1] * s + p[2] * c];
  }

  // cheap neon glow: wide translucent stroke under a bright thin stroke
  function neonStroke(color, width) {
    ctx.strokeStyle = rgba(color, 0.3);
    ctx.lineWidth = width * 3;
    ctx.stroke();
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.stroke();
  }

  // ---- background ----
  function drawBackground() {
    ctx.fillStyle = bgGradient;
    ctx.fillRect(0, 0, W, H);
  }

  // ---- stars ----
  function drawStars(cam) {
    ctx.fillStyle = '#ffffff';
    for (var i = 0; i < stars.length; i++) {
      var st = stars[i];
      var p = E.add(TARGET, E.scale(st.dir, 90));
      var pr = E.project(cam, p, W, H, FOV);
      if (!pr) continue;
      var tw = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(state.time * st.speed + st.phase));
      ctx.globalAlpha = tw;
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, st.size, 0, 6.2832);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // ---- grid floor ----
  function drawGrid(cam) {
    var N = 12, S = 2;
    ctx.lineWidth = 1;
    var i, a, b;
    for (i = -N; i <= N; i++) {
      a = E.project(cam, [i * S, 0, -N * S], W, H, FOV);
      b = E.project(cam, [i * S, 0, N * S], W, H, FOV);
      if (a && b) {
        var al = 0.5 / (1 + (a.z + b.z) * 0.02);
        ctx.strokeStyle = rgba('#ff2bd6', Math.max(0.03, Math.min(0.5, al)));
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }
      a = E.project(cam, [-N * S, 0, i * S], W, H, FOV);
      b = E.project(cam, [N * S, 0, i * S], W, H, FOV);
      if (a && b) {
        var al2 = 0.5 / (1 + (a.z + b.z) * 0.02);
        ctx.strokeStyle = rgba('#ff2bd6', Math.max(0.03, Math.min(0.5, al2)));
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }
    }
  }

  // ---- portal core ----
  function drawPortal(cam) {
    var center = [0, 3.5, 0];
    var pc = E.project(cam, center, W, H, FOV);
    if (!pc) return;
    var scale = (H / 2) / Math.tan(FOV / 2);
    var R = (2.4 / pc.z) * scale;

    // glowing disc (pre-rendered sprite, blitted)
    ctx.globalCompositeOperation = 'lighter';
    ctx.drawImage(portalSprite, pc.x - R, pc.y - R, R * 2, R * 2);
    ctx.globalCompositeOperation = 'source-over';

    // two counter-rotating rings as projected 3D polylines
    drawRing(cam, center, 2.6, state.time * 0.8, '#00f0ff');
    drawRing(cam, center, 3.1, -state.time * 0.6, '#ff2bd6');
  }

  function drawRing(cam, center, radius, angle, color) {
    var SEG = 48;
    var pts = [];
    for (var i = 0; i <= SEG; i++) {
      var a = (i / SEG) * 6.2832;
      var local = [Math.cos(a) * radius, Math.sin(a) * radius, 0];
      local = rotX(local, angle);
      local = rotY(local, angle * 0.5);
      var wp = E.add(center, local);
      var pr = E.project(cam, wp, W, H, FOV);
      pts.push(pr);
    }
    ctx.beginPath();
    var started = false;
    for (var j = 0; j < pts.length; j++) {
      if (!pts[j]) { started = false; continue; }
      if (!started) { ctx.moveTo(pts[j].x, pts[j].y); started = true; }
      else ctx.lineTo(pts[j].x, pts[j].y);
    }
    neonStroke(color, 2);
  }

  // ---- collect + draw sorted polys ----
  function collectPolys(cam) {
    var polys = [];
    var i, f, box, proj, depth, k;

    // box faces
    for (i = 0; i < boxes.length; i++) {
      box = boxes[i];
      for (f = 0; f < box.faces.length; f++) {
        var idx = box.faces[f];
        var A = box.corners[idx[0]], B = box.corners[idx[1]], C = box.corners[idx[2]];
        if (!E.visible(cam, A, B, C)) continue;
        proj = [
          E.project(cam, A, W, H, FOV),
          E.project(cam, B, W, H, FOV),
          E.project(cam, box.corners[idx[3]], W, H, FOV),
          E.project(cam, C, W, H, FOV)
        ];
        if (proj[0] && proj[1] && proj[2] && proj[3]) {
          depth = (proj[0].z + proj[1].z + proj[2].z + proj[3].z) / 4;
          var nn = E.faceNormal(A, B, C);
          polys.push({ type: 'box', pts: proj, depth: depth, light: E.shade(nn, LIGHT) });
        }
      }
    }

    // crystal triangles
    for (i = 0; i < crystals.length; i++) {
      var cr = crystals[i];
      var ang = cr.baseAngle + state.time * cr.orbitSpeed;
      var cx = Math.cos(ang) * cr.radius;
      var cz = Math.sin(ang) * cr.radius;
      var cy = cr.height + Math.sin(state.time * 0.8 + i) * 0.3;
      var spin = state.time * cr.spinSpeed;
      var world = [];
      for (k = 0; k < cr.octa.verts.length; k++) {
        var v = cr.octa.verts[k];
        v = rotY(v, spin);
        v = rotX(v, spin * 0.7);
        world.push([v[0] + cx, v[1] + cy, v[2] + cz]);
      }
      for (f = 0; f < cr.octa.tris.length; f++) {
        var t = cr.octa.tris[f];
        var A2 = world[t[0]], B2 = world[t[1]], C2 = world[t[2]];
        if (!E.visible(cam, A2, B2, C2)) continue;
        var p2 = [
          E.project(cam, A2, W, H, FOV),
          E.project(cam, B2, W, H, FOV),
          E.project(cam, C2, W, H, FOV)
        ];
        if (p2[0] && p2[1] && p2[2]) {
          depth = (p2[0].z + p2[1].z + p2[2].z) / 3;
          var nn2 = E.faceNormal(A2, B2, C2);
          polys.push({ type: 'crystal', pts: p2, depth: depth, light: E.shade(nn2, LIGHT), color: cr.color });
        }
      }
    }

    return E.sortPolys(polys);
  }

  function drawPolys(polys) {
    var i, p, j;
    for (i = 0; i < polys.length; i++) {
      p = polys[i];
      ctx.beginPath();
      ctx.moveTo(p.pts[0].x, p.pts[0].y);
      for (j = 1; j < p.pts.length; j++) ctx.lineTo(p.pts[j].x, p.pts[j].y);
      ctx.closePath();

      if (p.type === 'box') {
        ctx.fillStyle = shadeHex('#140a24', 0.4 + 0.6 * p.light);
        ctx.fill();
        neonStroke(i % 2 === 0 ? '#00f0ff' : '#ff2bd6', 1.5);
      } else {
        ctx.fillStyle = rgba(p.color, 0.35 + 0.5 * p.light);
        ctx.fill();
        neonStroke(p.color, 1.5);
      }
    }
  }

  // ---- particles ----
  function updateParticles(dt) {
    for (var i = 0; i < particles.length; i++) {
      var p = particles[i];
      p.y += p.vy * dt;
      if (p.y > 7) {
        p.y = 0;
        p.x = (Math.random() - 0.5) * 9;
        p.z = (Math.random() - 0.5) * 6;
      }
    }
  }
  function drawParticles(cam) {
    ctx.globalCompositeOperation = 'lighter';
    var scale = (H / 2) / Math.tan(FOV / 2);
    for (var i = 0; i < particles.length; i++) {
      var p = particles[i];
      var pr = E.project(cam, [p.x, p.y, p.z], W, H, FOV);
      if (!pr) continue;
      var r = Math.max(2, (p.size / pr.z) * scale * 0.05);
      ctx.drawImage(particleSprite(p.hue), pr.x - r, pr.y - r, r * 2, r * 2);
    }
    ctx.globalCompositeOperation = 'source-over';
  }

  // ---- HUD ----
  var elFps = document.getElementById('fps');
  var elPolys = document.getElementById('polys');
  var elParts = document.getElementById('parts');
  var btnPause = document.getElementById('btnPause');
  var btnOrbit = document.getElementById('btnOrbit');
  var btnReset = document.getElementById('btnReset');
  var speedInput = document.getElementById('speed');

  var fpsFrames = 0, fpsTimer = 0;

  function updateHUD(dt) {
    fpsFrames++;
    fpsTimer += dt;
    if (fpsTimer >= 0.5) {
      var fps = Math.round(fpsFrames / fpsTimer);
      elFps.textContent = String(fps);
      elPolys.textContent = String(state.polysDrawn);
      elParts.textContent = String(particles.length);
      fpsFrames = 0;
      fpsTimer = 0;
    }
  }

  // ---- controls ----
  btnPause.addEventListener('click', function () {
    state.paused = !state.paused;
    btnPause.textContent = state.paused ? 'Resume' : 'Pause';
  });
  btnOrbit.addEventListener('click', function () {
    state.orbit = !state.orbit;
    btnOrbit.textContent = state.orbit ? 'Orbit ON' : 'Orbit OFF';
  });
  btnReset.addEventListener('click', function () {
    state.paused = false;
    state.orbit = true;
    state.speed = 1;
    state.camAngle = 0;
    btnPause.textContent = 'Pause';
    btnOrbit.textContent = 'Orbit ON';
    speedInput.value = '1';
  });
  speedInput.addEventListener('input', function () {
    state.speed = parseFloat(speedInput.value);
  });

  // ---- main loop ----
  var last = global.performance.now();

  function frame(now) {
    var dt = (now - last) / 1000;
    last = now;
    if (dt > 0.1) dt = 0.1;

    if (!state.paused) {
      state.time += dt * state.speed;
      if (state.orbit) state.camAngle += dt * state.speed * 0.4;
      updateParticles(dt * state.speed);
    }

    var cam = E.makeCamera(
      [TARGET[0] + Math.sin(state.camAngle) * CAM_RADIUS, CAM_Y, TARGET[2] + Math.cos(state.camAngle) * CAM_RADIUS],
      TARGET,
      [0, 1, 0]
    );

    drawBackground();
    drawStars(cam);
    drawGrid(cam);
    drawPortal(cam);

    var polys = collectPolys(cam);
    drawPolys(polys);
    state.polysDrawn = polys.length;

    drawParticles(cam);

    state.frames++;
    updateHUD(dt);

    global.requestAnimationFrame(frame);
  }
  global.requestAnimationFrame(frame);

  // ---- expose ----
  global.app = {
    get paused() { return state.paused; },
    get orbit() { return state.orbit; },
    get speed() { return state.speed; },
    get camAngle() { return state.camAngle; },
    get time() { return state.time; },
    stars: stars,
    particles: particles,
    crystals: crystals,
    boxes: boxes,
    boxFaceCount: scene.boxFaceCount,
    crystalTriCount: scene.crystalTriCount,
    get polysDrawn() { return state.polysDrawn; },
    get frames() { return state.frames; }
  };
})(window);
