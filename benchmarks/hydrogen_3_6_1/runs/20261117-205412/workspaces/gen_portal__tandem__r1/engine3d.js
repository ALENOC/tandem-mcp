// engine3d.js : software 3D renderer on the 2D canvas context. Sets window.Engine3D. No import/export.
(function () {
  var DEF = { yaw: 0.55, pitch: 0.34, dist: 9.6, fov: 580, target: [0, 0.35, 0] };
  var LIGHT = (function () {
    var x = 0.45, y = 0.8, z = -0.4;
    var l = Math.sqrt(x * x + y * y + z * z);
    return [x / l, y / l, z / l];
  })();

  var canvas, ctx, W, H, dpr;
  var scene = null;
  var yaw = DEF.yaw, pitch = DEF.pitch, dist = DEF.dist, fov = DEF.fov, target = DEF.target.slice();
  var speed = 1.0, paused = false, orbit = true;
  var time = 0, last = 0, fps = 0, fpsAcc = 0, fpsN = 0;
  var polys = 0, parts = 0;
  var dragging = false, lastX = 0, lastY = 0;

  function resize() {
    dpr = window.devicePixelRatio || 1;
    W = window.innerWidth;
    H = window.innerHeight;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function project(x, y, z) {
    x -= target[0]; y -= target[1]; z -= target[2];
    var cy = Math.cos(yaw), sy = Math.sin(yaw);
    var x1 = x * cy - z * sy;
    var z1 = x * sy + z * cy;
    var cp = Math.cos(pitch), sp = Math.sin(pitch);
    var y2 = y * cp + z1 * sp;
    var z2 = -y * sp + z1 * cp;
    var depth = z2 + dist;
    if (depth < 0.2) return null;
    var view = Math.min(W / 1180, H / 720);
    var s = fov * view / depth;
    return { x: W / 2 + x1 * s, y: H / 2 - y2 * s, depth: depth, s: s };
  }

  function normalOf(a, b, c) {
    var ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    var vx = c[0] - a[0], vy = c[1] - a[1], vz = c[2] - a[2];
    var nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    var l = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1;
    return [nx / l, ny / l, nz / l];
  }

  function drawPoly(pts, color, glow, white) {
    var n = normalOf(pts[0], pts[1], pts[2]);
    var d = Math.max(0, n[0] * LIGHT[0] + n[1] * LIGHT[1] + n[2] * LIGHT[2]);
    var b = 0.42 + 0.95 * d + glow;
    var r = Math.min(255, color[0] * b) | 0;
    var g = Math.min(255, color[1] * b) | 0;
    var bl = Math.min(255, color[2] * b) | 0;
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (var i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
    ctx.closePath();
    ctx.fillStyle = 'rgb(' + r + ',' + g + ',' + bl + ')';
    ctx.fill();
    ctx.lineWidth = 1;
    ctx.strokeStyle = white ? 'rgba(255,255,255,0.85)' : 'rgba(0,220,255,0.35)';
    ctx.stroke();
    polys++;
  }

  function octa(cx, cy, cz, spin, color) {
    var hh = 0.42, hw = 0.24;
    var cs = Math.cos(spin), sn = Math.sin(spin);
    var ring = [
      [hw, 0, 0], [0, 0, hw], [-hw, 0, 0], [0, 0, -hw]
    ].map(function (p) {
      return [cx + p[0] * cs + p[2] * sn, cy + p[1], cz - p[0] * sn + p[2] * cs];
    });
    var top = [cx, cy + hh, cz], bot = [cx, cy - hh, cz];
    var tris = [];
    for (var i = 0; i < 4; i++) {
      var a = ring[i], b = ring[(i + 1) % 4];
      tris.push([a, b, top]);
      tris.push([a, bot, b]);
    }
    return tris.map(function (t) {
      var P = t.map(function (v) { return project(v[0], v[1], v[2]); });
      if (P.some(function (p) { return !p; })) return null;
      return { pts: P, color: color, glow: 0.25, white: true, depth: (P[0].depth + P[1].depth + P[2].depth) / 3 };
    }).filter(Boolean);
  }

  function drawGrid() {
    var i, a, b;
    for (i = -12; i <= 12; i++) {
      a = project(i, -2.0, -12); b = project(i, -2.0, 12);
      if (a && b) {
        ctx.strokeStyle = i % 4 === 0 ? 'rgba(0,220,255,0.5)' : 'rgba(0,150,220,0.16)';
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }
      a = project(-12, -2.0, i); b = project(12, -2.0, i);
      if (a && b) {
        ctx.strokeStyle = i % 4 === 0 ? 'rgba(0,220,255,0.5)' : 'rgba(0,150,220,0.16)';
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }
    }
  }

  function drawStars() {
    for (var i = 0; i < scene.stars.length; i++) {
      var st = scene.stars[i];
      var p = project(st.p[0], st.p[1], st.p[2]);
      if (!p) continue;
      var tw = 0.5 + 0.5 * Math.sin(time * st.rate + st.phase);
      var a = 0.25 + 0.75 * tw;
      var sz = st.size;
      ctx.fillStyle = 'rgba(200,230,255,' + a.toFixed(3) + ')';
      ctx.fillRect(p.x - sz / 2, p.y - sz / 2, sz, sz);
    }
  }

  function drawPortal() {
    var c = project(0, 0.55, 0);
    if (!c) return;
    var pulse = 1 + 0.08 * Math.sin(time * 0.9);
    var R = 1.05 * c.s * pulse;
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    var g = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, R);
    g.addColorStop(0, 'rgba(255,255,255,0.95)');
    g.addColorStop(0.35, 'rgba(0,220,255,0.7)');
    g.addColorStop(0.7, 'rgba(255,70,215,0.4)');
    g.addColorStop(1, 'rgba(255,70,215,0)');
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(c.x, c.y, R, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
  }

  function drawRing(radius, color, dir) {
    var seg = 40, prev = null;
    ctx.beginPath();
    var started = false;
    for (var i = 0; i <= seg; i++) {
      var t = i / seg * Math.PI * 2;
      var ang = t + dir * time * 0.8;
      var x = radius * Math.cos(ang);
      var z = radius * Math.sin(ang);
      var y = 0.55 + 0.18 * Math.sin(t * 2 + dir * time);
      var p = project(x, y, z);
      if (!p) { started = false; prev = null; continue; }
      if (!started) { ctx.moveTo(p.x, p.y); started = true; } else ctx.lineTo(p.x, p.y);
      prev = p;
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  function drawParticles(dt) {
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    for (var i = 0; i < scene.particles.length; i++) {
      var pt = scene.particles[i];
      if (!paused) {
        pt.y += pt.v * dt;
        if (pt.y > 3.6) pt.y = -1.9;
      }
      var p = project(pt.x + Math.sin(time * pt.sway + i) * 0.1, pt.y, pt.z);
      if (!p) continue;
      var sz = pt.size * p.s;
      ctx.fillStyle = 'hsla(' + pt.hue + ',100%,70%,0.8)';
      ctx.beginPath(); ctx.arc(p.x, p.y, sz, 0, Math.PI * 2); ctx.fill();
    }
    ctx.restore();
    parts = scene.particles.length;
  }

  function frame(now) {
    requestAnimationFrame(frame);
    if (!last) last = now;
    var dt = (now - last) / 1000;
    last = now;
    if (dt > 0.05) dt = 0.05;
    if (dt <= 0) dt = 0.016;
    fpsAcc += dt; fpsN++;
    if (fpsAcc >= 0.5) { fps = Math.round(fpsN / fpsAcc); fpsAcc = 0; fpsN = 0; }

    if (!paused) {
      time += dt * speed;
      if (orbit) yaw += 0.22 * dt * speed;
    }

    ctx.clearRect(0, 0, W, H);
    polys = 0;

    drawStars();
    drawGrid();

    var polysList = [];
    for (var i = 0; i < scene.faces.length; i++) {
      var f = scene.faces[i];
      var P = f.pts.map(function (v) { return project(v[0], v[1], v[2]); });
      if (P.some(function (p) { return !p; })) continue;
      polysList.push({ pts: P, color: f.color, glow: f.glow, white: false, depth: (P[0].depth + P[1].depth + P[2].depth + P[3].depth) / 4 });
    }
    for (var c = 0; c < scene.crystals.length; c++) {
      var cr = scene.crystals[c];
      var a = cr.angle + 0.35 * time;
      var cx = 2.45 * Math.cos(a);
      var cz = 2.45 * Math.sin(a);
      var cy = 0.5 + 0.28 * Math.sin(1.4 * time + cr.phase);
      var tris = octa(cx, cy, cz, time * cr.spin, cr.color);
      for (var t = 0; t < tris.length; t++) polysList.push(tris[t]);
    }
    polysList.sort(function (m, n) { return n.depth - m.depth; });
    for (var k = 0; k < polysList.length; k++) drawPoly(polysList[k].pts, polysList[k].color, polysList[k].glow, polysList[k].white);

    drawPortal();
    drawRing(1.0, 'rgba(0,220,255,0.9)', 1);
    drawRing(0.78, 'rgba(255,70,215,0.9)', -1);

    drawParticles(dt);
  }

  function onDown(e) { dragging = true; lastX = e.clientX; lastY = e.clientY; }
  function onMove(e) {
    if (!dragging) return;
    yaw += (e.clientX - lastX) * 0.005;
    pitch += (e.clientY - lastY) * 0.005;
    lastX = e.clientX; lastY = e.clientY;
  }
  function onUp() { dragging = false; }

  function init(cv) {
    canvas = cv;
    ctx = canvas.getContext('2d');
    resize();
    window.addEventListener('resize', resize);
    canvas.addEventListener('pointerdown', onDown);
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    scene = window.Scene.build();
    last = 0;
    requestAnimationFrame(frame);
  }

  window.Engine3D = {
    init: init,
    setSpeed: function (v) { speed = v; },
    togglePause: function () { paused = !paused; return paused; },
    toggleOrbit: function () { orbit = !orbit; return orbit; },
    reset: function () {
      yaw = DEF.yaw; pitch = DEF.pitch; dist = DEF.dist; fov = DEF.fov;
      target = DEF.target.slice(); time = 0;
    },
    getStats: function () { return { fps: fps, polys: polys, parts: parts }; }
  };
})();
