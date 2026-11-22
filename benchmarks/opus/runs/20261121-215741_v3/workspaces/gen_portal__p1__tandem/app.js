// app.js - main loop, HUD wiring, window.app state.
(function (global) {
  'use strict';

  var canvas = document.getElementById('c');
  var renderer = new Engine3D.Renderer(canvas);

  var scene = Scene.buildScene();

  // ---- window.app state ----
  var app = {
    paused: false,
    orbit: true,
    speed: 1,
    camAngle: 0,
    boxFaces: scene.boxFaces,
    crystalTris: scene.crystalTris,
    stars: scene.stars,
    particles: scene.particles,
    polys: 0,
    frames: 0
  };
  global.app = app;

  // ---- HUD elements ----
  var elFps = document.getElementById('fps');
  var elPolys = document.getElementById('polys');
  var elParts = document.getElementById('parts');
  var elPause = document.getElementById('pause');
  var elOrbit = document.getElementById('orbit');
  var elReset = document.getElementById('reset');
  var elSpeed = document.getElementById('speed');

  // ---- scene time (advances only when not paused) ----
  var sceneTime = 0;
  var gridScroll = 0;

  // ---- resize / devicePixelRatio ----
  function resize() {
    var dpr = global.devicePixelRatio || 1;
    renderer.resize(global.innerWidth, global.innerHeight, dpr);
  }
  global.addEventListener('resize', resize);
  resize();

  // ---- camera: orbit around Y axis, look at portal center, slightly elevated ----
  var portalCenter = [0, 3.5, 0];
  function cameraEye() {
    var a = app.camAngle;
    var dist = 16;
    var h = 6.5;
    return [Math.sin(a) * dist, h, Math.cos(a) * dist];
  }

  // ---- background: dark radial gradient space, painted each frame ----
  function paintBackground() {
    var ctx = renderer.ctx;
    var w = renderer.width, h = renderer.height;
    var g = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, Math.max(w, h) * 0.75);
    g.addColorStop(0, '#1a0b3d');
    g.addColorStop(1, '#05010f');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
  }

  // ---- flat shading: darken base color by face normal vs light ----
  function shade(base, n, light) {
    var d = n[0] * light[0] + n[1] * light[1] + n[2] * light[2];
    if (d < 0) d = 0;
    var f = 0.35 + 0.65 * d;
    var r = Math.min(255, Math.round(base[0] * f));
    var g = Math.min(255, Math.round(base[1] * f));
    var b = Math.min(255, Math.round(base[2] * f));
    return 'rgb(' + r + ',' + g + ',' + b + ')';
  }

  var BOX_BASE = [0x1b, 0x14, 0x40];
  var LIGHT = [0.3, 0.6, 0.75];

  // ---- collect drawables (world-space) then painter's sort by depth ----
  function drawBoxes() {
    var items = [];
    for (var i = 0; i < scene.boxes.length; i++) {
      var box = scene.boxes[i];
      for (var f = 0; f < box.faces.length; f++) {
        var face = box.faces[f];
        var n = face.n;
        var c = face.pts[0];
        var cx = (face.pts[0][0] + face.pts[1][0] + face.pts[2][0] + face.pts[3][0]) / 4;
        var cy = (face.pts[0][1] + face.pts[1][1] + face.pts[2][1] + face.pts[3][1]) / 4;
        var cz = (face.pts[0][2] + face.pts[1][2] + face.pts[2][2] + face.pts[3][2]) / 4;
        // backface cull: skip faces pointing away from camera
        var eye = cameraEye();
        var vx = eye[0] - cx, vy = eye[1] - cy, vz = eye[2] - cz;
        if (n[0] * vx + n[1] * vy + n[2] * vz <= 0) continue;
        var edge = (i % 2 === 0) ? '#00f0ff' : '#ff2bd6';
        items.push({
          pts: face.pts,
          color: shade(BOX_BASE, n, LIGHT),
          edge: edge,
          depth: (cx + cy + cz) / 3
        });
      }
    }
    items.sort(function (a, b) { return a.depth - b.depth; });
    for (var k = 0; k < items.length; k++) {
      renderer.poly(items[k].pts, items[k].color, items[k].edge);
    }
  }

  // ---- crystals: orbiting, spinning octahedra with additive glow ----
  function drawCrystals() {
    var items = [];
    for (var i = 0; i < scene.crystals.length; i++) {
      var cr = scene.crystals[i];
      var ang = cr.baseAngle + sceneTime * 0.4;
      var cx = Math.cos(ang) * cr.radius;
      var cy = cr.height;
      var cz = Math.sin(ang) * cr.radius;
      var spin = sceneTime * cr.spin;
      var cosS = Math.cos(spin), sinS = Math.sin(spin);
      var geo = cr.geo;
      for (var t = 0; t < geo.tris.length; t++) {
        var tri = geo.tris[t];
        var wpts = [];
        for (var v = 0; v < 3; v++) {
          var px = tri[v][0], py = tri[v][1], pz = tri[v][2];
          // spin around Y then translate to orbit position
          var rx = px * cosS + pz * sinS;
          var rz = -px * sinS + pz * cosS;
          wpts.push([rx + cx, py + cy, rz + cz]);
        }
        var mx = (wpts[0][0] + wpts[1][0] + wpts[2][0]) / 3;
        var my = (wpts[0][1] + wpts[1][1] + wpts[2][1]) / 3;
        var mz = (wpts[0][2] + wpts[1][2] + wpts[2][2]) / 3;
        items.push({ pts: wpts, color: cr.color, depth: (mx + my + mz) / 3 });
      }
    }
    items.sort(function (a, b) { return a.depth - b.depth; });
    var ctx = renderer.ctx;
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    ctx.shadowBlur = 12;
    for (var k = 0; k < items.length; k++) {
      var it = items[k];
      ctx.shadowColor = it.color;
      renderer.poly(it.pts, it.color, null);
    }
    ctx.restore();
  }

  // ---- portal core: radial gradient disk + two concentric neon rings ----
  function drawPortal() {
    var p = scene.portal;
    var ctx = renderer.ctx;
    var c = renderer.project([p.x, p.y, p.z]);
    if (!c) return;
    // scale: pixels per world unit at this depth
    var near2 = renderer.project([p.x, p.y, p.z + 1]);
    var scale = 1;
    if (near2) {
      var d = Math.abs(near2.x - c.x);
      if (d > 0.001) scale = d;
    }
    var R = p.outerR * scale;
    // glowing disk
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    var g = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, R);
    g.addColorStop(0, 'rgba(255,255,255,0.9)');
    g.addColorStop(0.35, 'rgba(157,77,255,0.7)');
    g.addColorStop(0.7, 'rgba(255,43,214,0.35)');
    g.addColorStop(1, 'rgba(0,240,255,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(c.x, c.y, R, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    // two concentric rings, opposite rotation, >=48 segments each
    var seg = p.seg;
    var inner = [];
    var outer = [];
    var t = sceneTime;
    for (var i = 0; i <= seg; i++) {
      var a = (i / seg) * Math.PI * 2;
      // inner ring #ff2bd6
      var ia = a + t * 0.8;
      inner.push([
        p.x + Math.cos(ia) * p.innerR,
        p.y + Math.sin(ia) * p.innerR,
        p.z
      ]);
      // outer ring #00f0ff
      var oa = -a - t * 0.5;
      outer.push([
        p.x + Math.cos(oa) * p.outerR,
        p.y + Math.sin(oa) * p.outerR,
        p.z
      ]);
    }
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    ctx.shadowBlur = 16;
    ctx.shadowColor = '#00f0ff';
    renderer.line(outer, '#00f0ff', 3);
    ctx.shadowColor = '#ff2bd6';
    renderer.line(inner, '#ff2bd6', 3);
    ctx.restore();
  }

  // ---- cyber grid floor at y=0, fading with distance, scrolling ----
  function drawGrid() {
    var ctx = renderer.ctx;
    var extent = 40;
    var step = 2;
    var off = gridScroll % step;
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    for (var i = -extent; i <= extent; i += step) {
      var z = i + off;
      // line along x at fixed z
      var a = renderer.project([-extent, 0, z]);
      var b = renderer.project([extent, 0, z]);
      if (a && b) {
        var fade = 1 - Math.min(1, Math.abs(z) / extent);
        ctx.strokeStyle = 'rgba(255,43,214,' + (0.5 * fade).toFixed(3) + ')';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
        renderer.count++;
      }
      var x = i + off;
      var c = renderer.project([x, 0, -extent]);
      var d = renderer.project([x, 0, extent]);
      if (c && d) {
        var fade2 = 1 - Math.min(1, Math.abs(x) / extent);
        ctx.strokeStyle = 'rgba(0,240,255,' + (0.5 * fade2).toFixed(3) + ')';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(c.x, c.y);
        ctx.lineTo(d.x, d.y);
        ctx.stroke();
        renderer.count++;
      }
    }
    ctx.restore();
  }

  // ---- stars: small dots with twinkling alpha (per-star sine phase) ----
  function drawStars() {
    var ctx = renderer.ctx;
    for (var i = 0; i < scene.stars.length; i++) {
      var s = scene.stars[i];
      var p = renderer.project([s.x, s.y, s.z]);
      if (!p) continue;
      var tw = 0.4 + 0.6 * (0.5 + 0.5 * Math.sin(sceneTime * s.speed + s.phase));
      ctx.fillStyle = 'rgba(232,246,255,' + tw.toFixed(3) + ')';
      ctx.beginPath();
      ctx.arc(p.x, p.y, s.size, 0, Math.PI * 2);
      ctx.fill();
      renderer.count++;
    }
  }

  // ---- particles: rising from platform, respawn at bottom above max height ----
  var MAX_H = 8;
  function updateParticles(dt) {
    for (var i = 0; i < app.particles.length; i++) {
      var p = app.particles[i];
      p.y += p.vy * dt;
      if (p.y > MAX_H) {
        p.y = 0;
        p.x = (Math.random() * 2 - 1) * 5;
        p.z = (Math.random() * 2 - 1) * 5;
      }
    }
  }
  function drawParticles() {
    var ctx = renderer.ctx;
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    for (var i = 0; i < app.particles.length; i++) {
      var p = app.particles[i];
      var s = renderer.project([p.x, p.y, p.z]);
      if (!s) continue;
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(s.x, s.y, p.size, 0, Math.PI * 2);
      ctx.fill();
      renderer.count++;
    }
    ctx.restore();
  }

  // ---- render one frame ----
  function render() {
    renderer.begin();
    renderer.lookAt(cameraEye(), portalCenter, [0, 1, 0]);
    paintBackground();
    drawStars();
    drawGrid();
    drawBoxes();
    drawPortal();
    drawCrystals();
    drawParticles();
    app.polys = renderer.count;
  }

  // ---- HUD ----
  var fpsAccum = 0, fpsFrames = 0, fpsVal = 0;
  function updateHUD(dt) {
    fpsAccum += dt;
    fpsFrames++;
    if (fpsAccum >= 0.5) {
      fpsVal = Math.round(fpsFrames / fpsAccum);
      fpsAccum = 0;
      fpsFrames = 0;
    }
    elFps.textContent = 'FPS: ' + fpsVal;
    elPolys.textContent = 'POLYS: ' + app.polys;
    elParts.textContent = 'PARTS: ' + app.particles.length;
  }

  // ---- main loop ----
  var last = global.performance.now();
  function frame(now) {
    var dt = (now - last) / 1000;
    last = now;
    if (dt < 0) dt = 0;
    if (dt > 0.1) dt = 0.1;
    app.frames++;
    if (!app.paused) {
      sceneTime += dt;
      gridScroll += dt * 0.5;
      if (app.orbit) app.camAngle += dt * app.speed;
      updateParticles(dt);
    }
    render();
    updateHUD(dt);
    global.requestAnimationFrame(frame);
  }
  global.requestAnimationFrame(frame);

  // ---- controls ----
  elPause.addEventListener('click', function () {
    app.paused = !app.paused;
    elPause.textContent = app.paused ? 'Resume' : 'Pause';
  });
  elOrbit.addEventListener('click', function () {
    app.orbit = !app.orbit;
    elOrbit.textContent = app.orbit ? 'Orbit ON' : 'Orbit OFF';
  });
  elReset.addEventListener('click', function () {
    app.paused = false;
    app.orbit = true;
    app.speed = 1;
    app.camAngle = 0;
    elPause.textContent = 'Pause';
    elOrbit.textContent = 'Orbit ON';
    elSpeed.value = '1';
  });
  elSpeed.addEventListener('input', function () {
    app.speed = parseFloat(elSpeed.value);
  });

})(typeof window !== 'undefined' ? window : this);
