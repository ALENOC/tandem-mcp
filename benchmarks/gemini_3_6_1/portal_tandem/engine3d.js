// engine3d.js : software 3D renderer for the neon portal gate.
// Plain browser script, no import/export. Sets window.Engine3D.
// Draws the object returned by window.Scene.build() on a 2D canvas context.

(function () {
  var TWO_PI = Math.PI * 2;

  // Camera defaults (constraint 5).
  var DEF = { yaw: 0.55, pitch: 0.34, dist: 9.6, fov: 580, target: [0, 0.35, 0] };

  // Light direction, normalized (constraint 21).
  var _lx = 0.45, _ly = 0.8, _lz = -0.4;
  var _ll = Math.sqrt(_lx * _lx + _ly * _ly + _lz * _lz);
  var LIGHT = [_lx / _ll, _ly / _ll, _lz / _ll];

  // Crystal octahedron geometry (constraint 17): half height 0.42, half width 0.24.
  var HH = 0.42, HW = 0.24;
  var OCTA = [
    [[0, HH, 0], [HW, 0, 0], [0, 0, HW]],
    [[0, HH, 0], [0, 0, HW], [-HW, 0, 0]],
    [[0, HH, 0], [-HW, 0, 0], [0, 0, -HW]],
    [[0, HH, 0], [0, 0, -HW], [HW, 0, 0]],
    [[0, -HH, 0], [0, 0, HW], [HW, 0, 0]],
    [[0, -HH, 0], [-HW, 0, 0], [0, 0, HW]],
    [[0, -HH, 0], [0, 0, -HW], [-HW, 0, 0]],
    [[0, -HH, 0], [HW, 0, 0], [0, 0, -HW]]
  ];

  var state = {
    canvas: null,
    ctx: null,
    scene: null,
    W: 0,
    H: 0,
    dpr: 1,
    yaw: DEF.yaw,
    pitch: DEF.pitch,
    dist: DEF.dist,
    fov: DEF.fov,
    target: DEF.target.slice(),
    speed: 1,
    paused: false,
    orbit: true,
    time: 0,
    last: 0,
    fps: 0,
    fpsAcc: 0,
    fpsN: 0,
    polys: 0,
    parts: 0,
    dragging: false,
    lastX: 0,
    lastY: 0
  };

  function clamp(v, lo, hi) {
    return v < lo ? lo : (v > hi ? hi : v);
  }

  function sizeCanvas() {
    var c = state.canvas;
    if (!c) return;
    state.dpr = window.devicePixelRatio || 1;
    state.W = window.innerWidth;
    state.H = window.innerHeight;
    c.width = Math.round(state.W * state.dpr);
    c.height = Math.round(state.H * state.dpr);
    c.style.width = state.W + 'px';
    c.style.height = state.H + 'px';
    state.ctx.setTransform(state.dpr, 0, 0, state.dpr, 0, 0);
  }

  // Project a world point to CSS-pixel screen coords. Returns null when behind the near plane.
  function project(x, y, z) {
    var tx = x - state.target[0];
    var ty = y - state.target[1];
    var tz = z - state.target[2];
    var cy = Math.cos(state.yaw), sy = Math.sin(state.yaw);
    var x1 = tx * cy - tz * sy;
    var z1 = tx * sy + tz * cy;
    var cp = Math.cos(state.pitch), sp = Math.sin(state.pitch);
    var y2 = ty * cp + z1 * sp;
    var z2 = -ty * sp + z1 * cp;
    var depth = z2 + state.dist;
    if (depth < 0.2) return null;
    var view = Math.min(state.W / 1180, state.H / 720);
    var s = state.fov * view / depth;
    return { x: state.W / 2 + x1 * s, y: state.H / 2 - y2 * s, depth: depth };
  }

  function drawStars() {
    var ctx = state.ctx;
    var stars = state.scene.stars;
    ctx.save();
    for (var i = 0; i < stars.length; i++) {
      var st = stars[i];
      var p = project(st.p[0], st.p[1], st.p[2]);
      if (!p) continue;
      var tw = Math.sin(state.time * st.rate + st.phase);
      var a = 0.35 + 0.65 * (0.5 + 0.5 * tw);
      var sz = st.size;
      ctx.globalAlpha = clamp(a, 0, 1);
      ctx.fillStyle = '#cfe9ff';
      ctx.fillRect(p.x - sz / 2, p.y - sz / 2, sz, sz);
    }
    ctx.globalAlpha = 1;
    ctx.restore();
  }

  function drawGrid() {
    var ctx = state.ctx;
    ctx.save();
    ctx.lineWidth = 1;
    for (var i = -12; i <= 12; i++) {
      var major = i % 4 === 0;
      ctx.strokeStyle = major ? 'rgba(0,229,255,0.55)' : 'rgba(0,180,255,0.16)';
      var a = project(i, -2.0, -12);
      var b = project(i, -2.0, 12);
      if (a && b) {
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      }
      var c = project(-12, -2.0, i);
      var d = project(12, -2.0, i);
      if (c && d) {
        ctx.beginPath();
        ctx.moveTo(c.x, c.y);
        ctx.lineTo(d.x, d.y);
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  // Build the list of polygons to depth-sort and draw (constraint 23).
  function buildPolys() {
    var polys = [];
    var faces = state.scene.faces;
    for (var i = 0; i < faces.length; i++) {
      var f = faces[i];
      var pts = f.pts;
      var proj = [];
      var sum = 0;
      var ok = true;
      for (var k = 0; k < pts.length; k++) {
        var p = project(pts[k][0], pts[k][1], pts[k][2]);
        if (!p) { ok = false; break; }
        proj.push(p);
        sum += p.depth;
      }
      if (!ok) continue;
      polys.push({ kind: 'face', proj: proj, world: pts, color: f.color, glow: f.glow, mean: sum / pts.length, crystal: false });
    }

    var crystals = state.scene.crystals;
    for (var c = 0; c < crystals.length; c++) {
      var cr = crystals[c];
      var ang = cr.angle + 0.35 * state.time;
      var cx = 2.45 * Math.cos(ang);
      var cz = 2.45 * Math.sin(ang);
      var cy = 0.5 + 0.28 * Math.sin(1.4 * state.time + cr.phase);
      var rot = state.time * cr.spin;
      var crs = Math.cos(rot), srs = Math.sin(rot);
      for (var t = 0; t < OCTA.length; t++) {
        var tri = OCTA[t];
        var proj = [];
        var sum = 0;
        var ok = true;
        for (var k = 0; k < 3; k++) {
          var lx = tri[k][0], ly = tri[k][1], lz = tri[k][2];
          var wx = cx + lx * crs + lz * srs;
          var wz = cz - lx * srs + lz * crs;
          var wy = cy + ly;
          var p = project(wx, wy, wz);
          if (!p) { ok = false; break; }
          proj.push(p);
          sum += p.depth;
        }
        if (!ok) continue;
        polys.push({ kind: 'crystal', proj: proj, world: tri, color: cr.color, glow: 0.1, mean: sum / 3, crystal: true });
      }
    }

    // Portal core participates in the same depth order (constraint 24).
    var pc = project(0, 0.55, 0);
    if (pc) polys.push({ kind: 'portal', proj: [pc], mean: pc.depth });

    polys.sort(function (a, b) { return b.mean - a.mean; });
    return polys;
  }

  function drawPoly(poly) {
    var ctx = state.ctx;
    var proj = poly.proj;
    if (poly.kind === 'portal') {
      drawPortalCore(proj[0]);
      return;
    }
    var n = proj.length;
    var w0 = poly.world[0], w1 = poly.world[1], w2 = poly.world[2];
    var e1x = w1[0] - w0[0], e1y = w1[1] - w0[1], e1z = w1[2] - w0[2];
    var e2x = w2[0] - w0[0], e2y = w2[1] - w0[1], e2z = w2[2] - w0[2];
    var nx = e1y * e2z - e1z * e2y;
    var ny = e1z * e2x - e1x * e2z;
    var nz = e1x * e2y - e1y * e2x;
    var nl = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1;
    nx /= nl; ny /= nl; nz /= nl;
    var dot = nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2];
    var bright = 0.42 + 0.95 * Math.max(0, dot) + poly.glow;
    var r = clamp(Math.round(poly.color[0] * bright), 0, 255);
    var g = clamp(Math.round(poly.color[1] * bright), 0, 255);
    var b = clamp(Math.round(poly.color[2] * bright), 0, 255);
    ctx.beginPath();
    ctx.moveTo(proj[0].x, proj[0].y);
    for (var i = 1; i < n; i++) ctx.lineTo(proj[i].x, proj[i].y);
    ctx.closePath();
    ctx.fillStyle = 'rgb(' + r + ',' + g + ',' + b + ')';
    ctx.fill();
    ctx.lineWidth = 1;
    ctx.strokeStyle = poly.crystal ? 'rgba(255,255,255,0.85)' : 'rgba(0,229,255,0.5)';
    ctx.stroke();
  }

  function drawPortalCore(p) {
    var ctx = state.ctx;
    var view = Math.min(state.W / 1180, state.H / 720);
    var s = state.fov * view / p.depth;
    var radius = 1.05 * (1 + 0.08 * Math.sin(0.6 * state.time)) * s;
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    var grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, radius);
    grad.addColorStop(0, 'rgba(255,255,255,0.95)');
    grad.addColorStop(0.35, 'rgba(0,229,255,0.7)');
    grad.addColorStop(0.7, 'rgba(255,70,215,0.35)');
    grad.addColorStop(1, 'rgba(255,70,215,0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(p.x, p.y, radius, 0, TWO_PI);
    ctx.fill();
    ctx.restore();
  }

  function drawRings() {
    var ctx = state.ctx;
    drawRing(1.0, 'rgba(0,229,255,0.8)', 0.5, state.time * 0.9);
    drawRing(0.78, 'rgba(255,70,215,0.8)', -0.5, -state.time * 1.1);
  }

  function drawRing(radius, color, tilt, rot) {
    var ctx = state.ctx;
    var N = 48;
    var ct = Math.cos(tilt), st = Math.sin(tilt);
    var cr = Math.cos(rot), sr = Math.sin(rot);
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    var started = false;
    for (var i = 0; i <= N; i++) {
      var a = (i / N) * TWO_PI;
      var x = radius * Math.cos(a);
      var z = radius * Math.sin(a);
      var y = 0;
      var y2 = y * ct - z * st;
      var z2 = y * st + z * ct;
      var x3 = x * cr - z2 * sr;
      var z3 = x * sr + z2 * cr;
      var p = project(x3, 0.55 + y2, z3);
      if (!p) { started = false; continue; }
      if (!started) { ctx.moveTo(p.x, p.y); started = true; }
      else ctx.lineTo(p.x, p.y);
    }
    ctx.stroke();
    ctx.restore();
  }

  function drawParticles() {
    var ctx = state.ctx;
    var parts = state.scene.particles;
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    for (var i = 0; i < parts.length; i++) {
      var pt = parts[i];
      var p = project(pt.x, pt.y, pt.z);
      if (!p) continue;
      var view = Math.min(state.W / 1180, state.H / 720);
      var s = state.fov * view / p.depth;
      var r = Math.max(1, pt.size * s);
      ctx.fillStyle = 'hsl(' + pt.hue + ',100%,70%)';
      ctx.beginPath();
      ctx.arc(p.x, p.y, r, 0, TWO_PI);
      ctx.fill();
    }
    ctx.restore();
  }

  function updateParticles(dt) {
    var parts = state.scene.particles;
    for (var i = 0; i < parts.length; i++) {
      var pt = parts[i];
      pt.y += pt.v * dt;
      if (pt.y > 3.6) pt.y = -1.9;
    }
  }

  function frame(now) {
    if (!state.last) state.last = now;
    var dt = (now - state.last) / 1000;
    state.last = now;
    if (dt > 0.05) dt = 0.05;

    if (!state.paused) {
      state.time += dt * state.speed;
      if (state.orbit) state.yaw += 0.22 * dt * state.speed;
      updateParticles(dt * state.speed);
    }

    state.fpsAcc += dt;
    state.fpsN++;
    if (state.fpsAcc >= 0.5) {
      state.fps = Math.round(state.fpsN / state.fpsAcc);
      state.fpsAcc = 0;
      state.fpsN = 0;
    }

    var ctx = state.ctx;
    ctx.clearRect(0, 0, state.W, state.H);

    drawStars();
    drawGrid();

    var polys = buildPolys();
    state.polys = 0;
    for (var i = 0; i < polys.length; i++) {
      var poly = polys[i];
      if (poly.kind === 'face' || poly.kind === 'crystal') state.polys++;
      drawPoly(poly);
    }

    drawRings();

    state.parts = state.scene.particles.length;
    drawParticles();

    window.requestAnimationFrame(frame);
  }

  function onPointerDown(e) {
    state.dragging = true;
    state.lastX = e.clientX;
    state.lastY = e.clientY;
    try { state.canvas.setPointerCapture(e.pointerId); } catch (err) {}
  }
  function onPointerMove(e) {
    if (!state.dragging) return;
    var dx = e.clientX - state.lastX;
    var dy = e.clientY - state.lastY;
    state.lastX = e.clientX;
    state.lastY = e.clientY;
    state.yaw += dx * 0.005;
    state.pitch += dy * 0.005;
    state.pitch = clamp(state.pitch, -1.4, 1.4);
  }
  function onPointerUp() {
    state.dragging = false;
  }

  function init(canvas) {
    state.canvas = canvas;
    state.ctx = canvas.getContext('2d');
    state.scene = window.Scene.build();
    sizeCanvas();
    window.addEventListener('resize', sizeCanvas);
    canvas.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    state.last = 0;
    window.requestAnimationFrame(frame);
  }

  window.Engine3D = {
    init: init,
    setSpeed: function (v) { state.speed = v; },
    togglePause: function () { state.paused = !state.paused; return state.paused; },
    toggleOrbit: function () { state.orbit = !state.orbit; return state.orbit; },
    reset: function () {
      state.yaw = DEF.yaw;
      state.pitch = DEF.pitch;
      state.dist = DEF.dist;
      state.fov = DEF.fov;
      state.target = DEF.target.slice();
      state.time = 0;
    },
    getStats: function () { return { fps: state.fps, polys: state.polys, parts: state.parts }; }
  };
})();
