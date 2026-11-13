(function () {
  var TAU = Math.PI * 2;

  var DEFAULTS = { yaw: 0.55, pitch: 0.34, dist: 9.6, fov: 580, target: [0, 0.35, 0] };
  var LIGHT = (function () {
    var x = 0.45, y = 0.8, z = -0.4;
    var l = Math.sqrt(x * x + y * y + z * z);
    return [x / l, y / l, z / l];
  })();

  var canvas, ctx;
  var scene = null;
  var W = 0, H = 0, dpr = 1;

  var cam = { yaw: DEFAULTS.yaw, pitch: DEFAULTS.pitch, dist: DEFAULTS.dist, fov: DEFAULTS.fov, target: DEFAULTS.target.slice() };
  var speed = 1;
  var paused = false;
  var orbit = true;
  var time = 0;
  var lastT = null;
  var fps = 0;
  var fpsAcc = 0, fpsN = 0;
  var polys = 0;
  var parts = 0;

  var dragging = false, lastX = 0, lastY = 0;

  function resize() {
    dpr = window.devicePixelRatio || 1;
    W = window.innerWidth;
    H = window.innerHeight;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function project(p) {
    var x = p[0] - cam.target[0];
    var y = p[1] - cam.target[1];
    var z = p[2] - cam.target[2];
    var cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw);
    var x1 = x * cy - z * sy;
    var z1 = x * sy + z * cy;
    var cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);
    var y2 = y * cp + z1 * sp;
    var z2 = -y * sp + z1 * cp;
    var depth = z2 + cam.dist;
    if (depth < 0.2) return null;
    var view = Math.min(W / 1180, H / 720);
    var s = cam.fov * view / depth;
    return { x: W / 2 + x1 * s, y: H / 2 - y2 * s, depth: depth, s: s };
  }

  function normalOf(a, b, c) {
    var ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    var vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
    var nx = uy * vz - uz * vy;
    var ny = uz * vx - ux * vz;
    var nz = ux * vy - uy * vx;
    var l = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1;
    return [nx / l, ny / l, nz / l];
  }

  function brightness(n, glow) {
    var d = n[0] * LIGHT[0] + n[1] * LIGHT[1] + n[2] * LIGHT[2];
    if (d < 0) d = 0;
    return 0.42 + 0.95 * d + glow;
  }

  function rgb(c, b) {
    var r = Math.max(0, Math.min(255, Math.round(c[0] * b)));
    var g = Math.max(0, Math.min(255, Math.round(c[1] * b)));
    var bl = Math.max(0, Math.min(255, Math.round(c[2] * b)));
    return 'rgb(' + r + ',' + g + ',' + bl + ')';
  }

  function drawPoly(pts, color, glow, stroke) {
    var n = normalOf(pts[0], pts[1], pts[2]);
    var b = brightness(n, glow);
    var ok = true;
    var sx = [], sy = [];
    for (var i = 0; i < pts.length; i++) {
      var pr = project(pts[i]);
      if (!pr) { ok = false; break; }
      sx.push(pr.x); sy.push(pr.y);
    }
    if (!ok) return;
    ctx.beginPath();
    ctx.moveTo(sx[0], sy[0]);
    for (var j = 1; j < sx.length; j++) ctx.lineTo(sx[j], sy[j]);
    ctx.closePath();
    ctx.fillStyle = rgb(color, b);
    ctx.fill();
    ctx.lineWidth = 1;
    ctx.strokeStyle = stroke;
    ctx.stroke();
    polys++;
  }

  function crystalVerts(cx, cy, cz, spin) {
    var hh = 0.42, hw = 0.24;
    var cs = Math.cos(spin), ss = Math.sin(spin);
    var ring = [
      [hw, 0, 0], [0, 0, hw], [-hw, 0, 0], [0, 0, -hw]
    ];
    var rot = [];
    for (var i = 0; i < 4; i++) {
      var rx = ring[i][0] * cs + ring[i][2] * ss;
      var rz = -ring[i][0] * ss + ring[i][2] * cs;
      rot.push([cx + rx, cy, cz + rz]);
    }
    var top = [cx, cy + hh, cz];
    var bot = [cx, cy - hh, cz];
    var tris = [];
    for (var i = 0; i < 4; i++) {
      var a = rot[i], b = rot[(i + 1) % 4];
      tris.push([top, a, b]);
      tris.push([bot, b, a]);
    }
    return tris;
  }

  function ringPoints(radius, tilt, rot) {
    var pts = [];
    var N = 48;
    var ct = Math.cos(tilt), st = Math.sin(tilt);
    for (var i = 0; i <= N; i++) {
      var a = rot + i / N * TAU;
      var x = radius * Math.cos(a);
      var z = radius * Math.sin(a);
      var y = z * st;
      var z2 = z * ct;
      pts.push([x, y + 0.55, z2]);
    }
    return pts;
  }

  function drawPolyline(pts, color, width) {
    ctx.beginPath();
    var started = false;
    for (var i = 0; i < pts.length; i++) {
      var pr = project(pts[i]);
      if (!pr) { started = false; continue; }
      if (!started) { ctx.moveTo(pr.x, pr.y); started = true; } else ctx.lineTo(pr.x, pr.y);
    }
    ctx.lineWidth = width;
    ctx.strokeStyle = color;
    ctx.stroke();
  }

  function drawStars() {
    for (var i = 0; i < scene.stars.length; i++) {
      var st = scene.stars[i];
      var pr = project(st.p);
      if (!pr) continue;
      var tw = Math.sin(time * st.rate + st.phase);
      var a = 0.35 + 0.35 * tw;
      if (a < 0) a = 0;
      var sz = st.size;
      ctx.fillStyle = 'rgba(200,225,255,' + a.toFixed(3) + ')';
      ctx.fillRect(pr.x - sz / 2, pr.y - sz / 2, sz, sz);
    }
  }

  function drawGrid() {
    var y = -2.0;
    for (var i = -12; i <= 12; i++) {
      var major = (i % 4 === 0);
      var col = major ? 'rgba(80,240,255,0.55)' : 'rgba(40,120,180,0.28)';
      ctx.strokeStyle = col;
      ctx.lineWidth = major ? 1.4 : 1;
      var a1 = project([i, y, -12]), a2 = project([i, y, 12]);
      if (a1 && a2) { ctx.beginPath(); ctx.moveTo(a1.x, a1.y); ctx.lineTo(a2.x, a2.y); ctx.stroke(); }
      var b1 = project([-12, y, i]), b2 = project([12, y, i]);
      if (b1 && b2) { ctx.beginPath(); ctx.moveTo(b1.x, b1.y); ctx.lineTo(b2.x, b2.y); ctx.stroke(); }
    }
  }

  function drawPortalCore() {
    var pr = project([0, 0.55, 0]);
    if (!pr) return;
    var pulse = 1.05 * (1 + 0.12 * Math.sin(time * 0.8));
    var r = pulse * pr.s;
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    var g = ctx.createRadialGradient(pr.x, pr.y, 0, pr.x, pr.y, r);
    g.addColorStop(0, 'rgba(255,255,255,0.95)');
    g.addColorStop(0.35, 'rgba(80,230,255,0.7)');
    g.addColorStop(0.7, 'rgba(255,80,220,0.35)');
    g.addColorStop(1, 'rgba(255,80,220,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(pr.x, pr.y, r, 0, TAU);
    ctx.fill();
    ctx.restore();
  }

  function drawParticles() {
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    for (var i = 0; i < scene.particles.length; i++) {
      var p = scene.particles[i];
      var pr = project([p.x, p.y, p.z]);
      if (!pr) continue;
      var sz = p.size * pr.s;
      if (sz < 0.5) sz = 0.5;
      ctx.fillStyle = 'hsla(' + p.hue + ',100%,65%,0.85)';
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, sz, 0, TAU);
      ctx.fill();
    }
    ctx.restore();
    parts = scene.particles.length;
  }

  function frame(t) {
    if (lastT == null) lastT = t;
    var dt = (t - lastT) / 1000;
    lastT = t;
    if (dt < 0) dt = 0;
    if (dt > 0.05) dt = 0.05;
    if (dt > 0) {
      fpsAcc += dt; fpsN++;
      if (fpsAcc >= 0.5) { fps = fpsN / fpsAcc; fpsAcc = 0; fpsN = 0; }
    }
    if (!paused) {
      time += dt * speed;
      if (orbit) cam.yaw += 0.22 * dt * speed;
    }

    ctx.clearRect(0, 0, W, H);

    drawStars();
    drawGrid();

    polys = 0;
    var items = [];
    for (var i = 0; i < scene.faces.length; i++) {
      var f = scene.faces[i];
      var md = 0;
      for (var k = 0; k < f.pts.length; k++) md += f.pts[k][0] * f.pts[k][0] + f.pts[k][1] * f.pts[k][1] + f.pts[k][2] * f.pts[k][2];
      items.push({ type: 'face', f: f, d: md });
    }
    for (var c = 0; c < scene.crystals.length; c++) {
      var cr = scene.crystals[c];
      var a = cr.angle + 0.35 * time;
      var cx = 2.45 * Math.cos(a);
      var cz = 2.45 * Math.sin(a);
      var cy = 0.5 + 0.28 * Math.sin(1.4 * time + cr.phase);
      var tris = crystalVerts(cx, cy, cz, time * cr.spin);
      for (var ti = 0; ti < tris.length; ti++) {
        var tr = tris[ti];
        var md2 = 0;
        for (var k2 = 0; k2 < tr.length; k2++) md2 += tr[k2][0] * tr[k2][0] + tr[k2][1] * tr[k2][1] + tr[k2][2] * tr[k2][2];
        items.push({ type: 'tri', tr: tr, color: cr.color, d: md2 });
      }
    }
    items.push({ type: 'portal', d: 0.55 * 0.55 });
    items.sort(function (p, q) { return q.d - p.d; });
    for (var j = 0; j < items.length; j++) {
      var it = items[j];
      if (it.type === 'face') drawPoly(it.f.pts, it.f.color, it.f.glow, 'rgba(90,200,255,0.35)');
      else if (it.type === 'tri') drawPoly(it.tr, it.color, 0.2, 'rgba(255,255,255,0.85)');
      else drawPortalCore();
    }

    drawPolyline(ringPoints(1.0, 0.5, time * 0.6), 'rgba(80,230,255,0.8)', 2);
    drawPolyline(ringPoints(0.78, -0.4, -time * 0.9), 'rgba(255,90,220,0.8)', 2);

    if (!paused) {
      for (var pi = 0; pi < scene.particles.length; pi++) {
        var pp = scene.particles[pi];
        pp.y += pp.v * dt * speed;
        if (pp.y > 3.6) pp.y = -1.9;
      }
    }
    drawParticles();

    window.requestAnimationFrame(frame);
  }

  function onPointerDown(e) {
    dragging = true;
    lastX = e.clientX; lastY = e.clientY;
    try { canvas.setPointerCapture(e.pointerId); } catch (err) {}
  }
  function onPointerMove(e) {
    if (!dragging) return;
    var dx = e.clientX - lastX;
    var dy = e.clientY - lastY;
    lastX = e.clientX; lastY = e.clientY;
    cam.yaw += dx * 0.005;
    cam.pitch += dy * 0.005;
    if (cam.pitch > 1.4) cam.pitch = 1.4;
    if (cam.pitch < -1.4) cam.pitch = -1.4;
  }
  function onPointerUp() { dragging = false; }

  function init(cv) {
    canvas = cv;
    ctx = canvas.getContext('2d');
    resize();
    window.addEventListener('resize', resize);
    canvas.addEventListener('pointerdown', onPointerDown);
    canvas.addEventListener('pointermove', onPointerMove);
    canvas.addEventListener('pointerup', onPointerUp);
    scene = window.Scene.build();
    lastT = null;
    window.requestAnimationFrame(frame);
  }

  function setSpeed(v) { speed = v; }
  function togglePause() { paused = !paused; return paused; }
  function toggleOrbit() { orbit = !orbit; return orbit; }
  function reset() {
    cam.yaw = DEFAULTS.yaw;
    cam.pitch = DEFAULTS.pitch;
    cam.dist = DEFAULTS.dist;
    cam.fov = DEFAULTS.fov;
    cam.target = DEFAULTS.target.slice();
    time = 0;
  }
  function getStats() { return { fps: fps, polys: polys, parts: parts }; }

  window.Engine3D = {
    init: init,
    setSpeed: setSpeed,
    togglePause: togglePause,
    toggleOrbit: toggleOrbit,
    reset: reset,
    getStats: getStats
  };
})();
