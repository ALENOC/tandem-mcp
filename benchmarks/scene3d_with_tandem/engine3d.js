/* engine3d.js
 * Pure HTML5 2D-canvas software 3D engine.
 * No WebGL, no external libraries.
 * Perspective projection + painter's algorithm z-sorting.
 * Flat/specular shading with a wireframe toggle.
 */
(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Public API surface
  // ---------------------------------------------------------------------------
  var Engine3D = {
    init: init,
    setSpeed: setSpeed,
    togglePause: togglePause,
    toggleWireframe: toggleWireframe,
    reset: reset,
    getStats: getStats
  };

  // ---------------------------------------------------------------------------
  // Module state
  // ---------------------------------------------------------------------------
  var canvas = null;
  var ctx = null;
  var W = 0;      // CSS pixel width
  var H = 0;      // CSS pixel height
  var dpr = 1;

  // Camera (orbit)
  var cam = {
    yaw: 0.6,
    pitch: 0.35,
    dist: 14,
    minDist: 5,
    maxDist: 40,
    focal: 0
  };

  var speed = 1.0;
  var paused = false;
  var wireframe = false;

  var simTime = 0;
  var lastTs = 0;
  var rafId = 0;

  // Stats
  var fps = 0;
  var polys = 0;
  var fpsAccum = 0;
  var fpsFrames = 0;
  var fpsTimer = 0;

  // Interaction
  var dragging = false;
  var lastX = 0;
  var lastY = 0;

  // Precomputed scene data
  var stars = [];
  var gridLines = [];
  var portalRings = [];
  var monolith = null;
  var core = null;
  var particles = [];

  // ---------------------------------------------------------------------------
  // Small math helpers
  // ---------------------------------------------------------------------------
  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }

  function normalize(v) {
    var l = Math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z) || 1;
    return { x: v.x / l, y: v.y / l, z: v.z / l };
  }

  function cross(a, b) {
    return {
      x: a.y * b.z - a.z * b.y,
      y: a.z * b.x - a.x * b.z,
      z: a.x * b.y - a.y * b.x
    };
  }

  function dot(a, b) { return a.x * b.x + a.y * b.y + a.z * b.z; }

  // ---------------------------------------------------------------------------
  // Camera transform + perspective projection
  // ---------------------------------------------------------------------------
  function toCamera(p) {
    var cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw);
    var cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);

    // Rotate around Y (yaw)
    var x1 = p.x * cy - p.z * sy;
    var z1 = p.x * sy + p.z * cy;
    var y1 = p.y;

    // Rotate around X (pitch)
    var y2 = y1 * cp - z1 * sp;
    var z2 = y1 * sp + z1 * cp;
    var x2 = x1;

    // Push back by distance (camera sits at +Z looking at origin)
    return { x: x2, y: y2, z: z2 + cam.dist };
  }

  function project(cp) {
    var f = cam.focal;
    return {
      x: W * 0.5 + (cp.x * f) / cp.z,
      y: H * 0.5 - (cp.y * f) / cp.z,
      z: cp.z,
      s: f / cp.z
    };
  }

  // World-space position of the camera (inverse of toCamera applied to origin).
  function cameraWorldPos() {
    var cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw);
    var cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);
    return {
      x: -sy * cp * cam.dist,
      y: -sp * cam.dist,
      z: -cy * cp * cam.dist
    };
  }

  // ---------------------------------------------------------------------------
  // Scene construction
  // ---------------------------------------------------------------------------
  function buildStars() {
    stars = [];
    var n = 260;
    for (var i = 0; i < n; i++) {
      // Distribute on a large sphere shell
      var u = Math.random() * 2 - 1;
      var th = Math.random() * Math.PI * 2;
      var r = Math.sqrt(1 - u * u);
      var rad = 60 + Math.random() * 40;
      stars.push({
        x: r * Math.cos(th) * rad,
        y: u * rad,
        z: r * Math.sin(th) * rad,
        b: 0.4 + Math.random() * 0.6,
        tw: Math.random() * 6.28
      });
    }
  }

  function buildGrid() {
    gridLines = [];
    var ext = 24;
    var step = 2;
    var y = -4;
    var i;
    for (i = -ext; i <= ext; i += step) {
      gridLines.push({ a: { x: i, y: y, z: -ext }, b: { x: i, y: y, z: ext }, major: (i % 8 === 0) });
      gridLines.push({ a: { x: -ext, y: y, z: i }, b: { x: ext, y: y, z: i }, major: (i % 8 === 0) });
    }
  }

  function buildPortal() {
    portalRings = [];
    var segs = 64;
    var radii = [3.2, 2.6, 2.0, 1.5];
    var cols = [
      [0, 255, 255],   // cyan
      [255, 0, 200],   // magenta
      [0, 255, 255],
      [255, 0, 200]
    ];
    for (var r = 0; r < radii.length; r++) {
      var pts = [];
      for (var i = 0; i <= segs; i++) {
        var a = (i / segs) * Math.PI * 2;
        pts.push({
          x: Math.cos(a) * radii[r],
          y: Math.sin(a) * radii[r],
          z: 0
        });
      }
      portalRings.push({ pts: pts, col: cols[r], phase: r * 0.7, width: 3.5 - r * 0.5 });
    }
  }

  // Faceted monolith: a beveled box (12 faces) built from 8 corner verts.
  function buildMonolith() {
    var hx = 1.1, hy = 2.2, hz = 0.5;
    var v = [
      { x: -hx, y: -hy, z: -hz }, { x: hx, y: -hy, z: -hz },
      { x: hx, y: hy, z: -hz }, { x: -hx, y: hy, z: -hz },
      { x: -hx, y: -hy, z: hz }, { x: hx, y: -hy, z: hz },
      { x: hx, y: hy, z: hz }, { x: -hx, y: hy, z: hz }
    ];
    var faces = [
      [0, 1, 2, 3], // back
      [5, 4, 7, 6], // front
      [4, 0, 3, 7], // left
      [1, 5, 6, 2], // right
      [3, 2, 6, 7], // top
      [4, 5, 1, 0]  // bottom
    ];
    monolith = { verts: v, faces: faces, baseY: 0.4 };
  }

  function buildCore() {
    // Glowing icosahedron-ish core: use an octahedron (6 verts, 8 faces)
    var r = 0.55;
    var v = [
      { x: r, y: 0, z: 0 }, { x: -r, y: 0, z: 0 },
      { x: 0, y: r, z: 0 }, { x: 0, y: -r, z: 0 },
      { x: 0, y: 0, z: r }, { x: 0, y: 0, z: -r }
    ];
    var faces = [
      [0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4],
      [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5]
    ];
    core = { verts: v, faces: faces };
  }

  function buildParticles() {
    particles = [];
    var n = 40;
    for (var i = 0; i < n; i++) {
      particles.push({
        ang: (i / n) * Math.PI * 2,
        rad: 4.2 + (i % 3) * 0.5,
        y: Math.sin(i * 1.3) * 1.6,
        spd: 0.4 + (i % 5) * 0.12,
        size: 0.12 + (i % 4) * 0.05,
        hue: i % 2
      });
    }
  }

  function buildScene() {
    buildStars();
    buildGrid();
    buildPortal();
    buildMonolith();
    buildCore();
    buildParticles();
  }

  // ---------------------------------------------------------------------------
  // Rendering primitives (all pushed into a depth-sorted draw list)
  // ---------------------------------------------------------------------------
  var drawList = [];

  function pushPoly(verts, col, opts) {
    // verts: array of projected {x,y,z}
    var depth = 0;
    for (var i = 0; i < verts.length; i++) depth += verts[i].z;
    depth /= verts.length;
    drawList.push({ type: 'poly', verts: verts, col: col, depth: depth, opts: opts || {} });
  }

  function pushLine(a, b, col, width, glow) {
    drawList.push({
      type: 'line', a: a, b: b, col: col,
      depth: (a.z + b.z) * 0.5, width: width, glow: glow
    });
  }

  function pushPoint(p, col, size, glow) {
    drawList.push({ type: 'point', p: p, col: col, size: size, glow: glow, depth: p.z });
  }

  // Flat + specular shading of a face given world-space normal and projected verts
  function shadeFace(worldVerts, normal, baseCol, opts) {
    var light = normalize({ x: -0.4, y: 0.8, z: 0.6 });
    var ndl = dot(normal, light);
    if (ndl < 0) ndl = 0;
    var ambient = 0.25;
    var diff = ambient + (1 - ambient) * ndl;

    // Specular (Blinn-ish) using view dir ~ (0,0,1) in camera space approx
    var view = { x: 0, y: 0, z: 1 };
    var half = normalize({
      x: light.x + view.x,
      y: light.y + view.y,
      z: light.z + view.z
    });
    var spec = Math.pow(Math.max(0, dot(normal, half)), 24) * (opts.specular || 0.6);

    var r = clamp(baseCol[0] * diff + 255 * spec, 0, 255) | 0;
    var g = clamp(baseCol[1] * diff + 255 * spec, 0, 255) | 0;
    var b = clamp(baseCol[2] * diff + 255 * spec, 0, 255) | 0;
    return [r, g, b];
  }

  // ---------------------------------------------------------------------------
  // Scene drawing
  // ---------------------------------------------------------------------------
  function drawStars() {
    for (var i = 0; i < stars.length; i++) {
      var s = stars[i];
      var cp = toCamera(s);
      if (cp.z <= 0.1) continue;
      var p = project(cp);
      if (p.x < -20 || p.x > W + 20 || p.y < -20 || p.y > H + 20) continue;
      var tw = 0.6 + 0.4 * Math.sin(simTime * 2 + s.tw);
      var a = clamp(s.b * tw, 0, 1);
      pushPoint(p, [255, 255, 255], 1 + s.b, a);
    }
  }

  function drawGrid() {
    for (var i = 0; i < gridLines.length; i++) {
      var L = gridLines[i];
      var a = toCamera(L.a);
      var b = toCamera(L.b);
      if (a.z <= 0.1 || b.z <= 0.1) continue;
      var pa = project(a);
      var pb = project(b);
      // Fade with distance
      var fade = clamp(1.4 - (a.z + b.z) * 0.5 / cam.dist, 0.15, 1);
      var col = L.major ? [0, 255, 255] : [255, 0, 200];
      var alpha = (L.major ? 0.55 : 0.3) * fade;
      pushLine(pa, pb, col, L.major ? 1.6 : 1, alpha);
    }
  }

  function drawPortal() {
    for (var r = 0; r < portalRings.length; r++) {
      var ring = portalRings[r];
      var spin = simTime * 0.5 + ring.phase;
      var pts = ring.pts;
      var prev = null;
      for (var i = 0; i < pts.length; i++) {
        var w = pts[i];
        // Slowly rotate ring in its own plane for shimmer
        var ca = Math.cos(spin), sa = Math.sin(spin);
        var wx = w.x * ca - w.y * sa;
        var wy = w.x * sa + w.y * ca;
        var cp = toCamera({ x: wx, y: wy, z: w.z });
        if (cp.z <= 0.1) { prev = null; continue; }
        var p = project(cp);
        if (prev) {
          var pulse = 0.6 + 0.4 * Math.sin(simTime * 3 + i * 0.3 + ring.phase);
          pushLine(prev, p, ring.col, ring.width, 0.5 + 0.5 * pulse);
        }
        prev = p;
      }
    }
  }

  function drawMonolith() {
    var rot = simTime * 0.7;
    var cr = Math.cos(rot), sr = Math.sin(rot);
    var bob = Math.sin(simTime * 1.2) * 0.25;

    // Transform each vertex: rotate around Y, then lift, then camera transform
    var wv = [];
    var pv = [];
    for (var i = 0; i < monolith.verts.length; i++) {
      var v = monolith.verts[i];
      var x = v.x * cr - v.z * sr;
      var z = v.x * sr + v.z * cr;
      var y = v.y + monolith.baseY + bob;
      wv.push({ x: x, y: y, z: z });
      pv.push(toCamera({ x: x, y: y, z: z }));
    }

    var camPos = cameraWorldPos();

    for (var f = 0; f < monolith.faces.length; f++) {
      var idx = monolith.faces[f];
      var a = wv[idx[0]], b = wv[idx[1]], c = wv[idx[2]], d = wv[idx[3]];
      var n = normalize(cross({ x: b.x - a.x, y: b.y - a.y, z: b.z - a.z },
                              { x: c.x - a.x, y: c.y - a.y, z: c.z - a.z }));
      // Backface cull: keep faces whose normal points toward the camera
      var toCam = { x: camPos.x - a.x, y: camPos.y - a.y, z: camPos.z - a.z };
      if (dot(n, toCam) <= 0) continue;

      var cam = [pv[idx[0]], pv[idx[1]], pv[idx[2]], pv[idx[3]]];
      var ok = true;
      for (var k = 0; k < cam.length; k++) if (cam[k].z <= 0.1) { ok = false; break; }
      if (!ok) continue;

      var col = shadeFace(wv, n, [120, 140, 255], { specular: 0.7 });
      var verts = cam.map(function (q) { return project(q); });
      pushPoly(verts, col, { specular: true });
      polys++;
    }
  }

  function drawCore() {
    var rot = simTime * 1.5;
    var cr = Math.cos(rot), sr = Math.sin(rot);
    var bob = Math.sin(simTime * 1.2) * 0.25;
    var cy = monolith.baseY + bob;

    var wv = [];
    var pv = [];
    for (var i = 0; i < core.verts.length; i++) {
      var v = core.verts[i];
      var x = v.x * cr - v.z * sr;
      var z = v.x * sr + v.z * cr;
      var y = v.y + cy;
      wv.push({ x: x, y: y, z: z });
      pv.push(toCamera({ x: x, y: y, z: z }));
    }

    var camPos = cameraWorldPos();

    for (var f = 0; f < core.faces.length; f++) {
      var idx = core.faces[f];
      var a = wv[idx[0]], b = wv[idx[1]], c = wv[idx[2]];
      var n = normalize(cross({ x: b.x - a.x, y: b.y - a.y, z: b.z - a.z },
                              { x: c.x - a.x, y: c.y - a.y, z: c.z - a.z }));
      var toCam = { x: camPos.x - a.x, y: camPos.y - a.y, z: camPos.z - a.z };
      if (dot(n, toCam) <= 0) continue;

      var cam = [pv[idx[0]], pv[idx[1]], pv[idx[2]]];
      var ok = true;
      for (var k = 0; k < cam.length; k++) if (cam[k].z <= 0.1) { ok = false; break; }
      if (!ok) continue;

      var pulse = 0.7 + 0.3 * Math.sin(simTime * 4);
      var col = [
        clamp(255 * pulse, 0, 255) | 0,
        clamp(120 * pulse, 0, 255) | 0,
        clamp(255 * pulse, 0, 255) | 0
      ];
      var verts = cam.map(function (q) { return project(q); });
      pushPoly(verts, col, { glow: true });
      polys++;
    }
  }

  function drawParticles() {
    for (var i = 0; i < particles.length; i++) {
      var p = particles[i];
      var ang = p.ang + simTime * p.spd;
      var x = Math.cos(ang) * p.rad;
      var z = Math.sin(ang) * p.rad;
      var y = p.y + Math.sin(simTime * 2 + i) * 0.3;
      var cp = toCamera({ x: x, y: y, z: z });
      if (cp.z <= 0.1) continue;
      var pr = project(cp);
      var col = p.hue ? [0, 255, 255] : [255, 0, 200];
      var size = p.size * pr.s * 0.5;
      pushPoint(pr, col, size, 0.9);
    }
  }

  // ---------------------------------------------------------------------------
  // Draw list rendering (painter's algorithm)
  // ---------------------------------------------------------------------------
  function render() {
    drawList.length = 0;
    polys = 0;

    drawStars();
    drawGrid();
    drawPortal();
    drawMonolith();
    drawCore();
    drawParticles();

    // Painter's algorithm: far to near
    drawList.sort(function (a, b) { return b.depth - a.depth; });

    ctx.clearRect(0, 0, W, H);

    // Background gradient
    var grad = ctx.createRadialGradient(W * 0.5, H * 0.45, 0, W * 0.5, H * 0.5, Math.max(W, H) * 0.75);
    grad.addColorStop(0, '#120a2a');
    grad.addColorStop(1, '#05030f');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);

    for (var i = 0; i < drawList.length; i++) {
      var it = drawList[i];
      if (it.type === 'poly') {
        drawPoly(it);
      } else if (it.type === 'line') {
        drawLine(it);
      } else if (it.type === 'point') {
        drawPoint(it);
      }
    }
  }

  function drawPoly(it) {
    var v = it.verts;
    ctx.beginPath();
    ctx.moveTo(v[0].x, v[0].y);
    for (var i = 1; i < v.length; i++) ctx.lineTo(v[i].x, v[i].y);
    ctx.closePath();

    if (wireframe) {
      ctx.strokeStyle = 'rgb(' + it.col[0] + ',' + it.col[1] + ',' + it.col[2] + ')';
      ctx.lineWidth = 1.2;
      ctx.stroke();
      return;
    }

    if (it.opts.glow) {
      ctx.shadowColor = 'rgb(' + it.col[0] + ',' + it.col[1] + ',' + it.col[2] + ')';
      ctx.shadowBlur = 18;
    }
    ctx.fillStyle = 'rgb(' + it.col[0] + ',' + it.col[1] + ',' + it.col[2] + ')';
    ctx.fill();
    ctx.shadowBlur = 0;
    // subtle edge
    ctx.strokeStyle = 'rgba(255,255,255,0.15)';
    ctx.lineWidth = 0.6;
    ctx.stroke();
  }

  function drawLine(it) {
    ctx.beginPath();
    ctx.moveTo(it.a.x, it.a.y);
    ctx.lineTo(it.b.x, it.b.y);
    ctx.strokeStyle = 'rgba(' + it.col[0] + ',' + it.col[1] + ',' + it.col[2] + ',' + it.glow + ')';
    ctx.lineWidth = it.width;
    if (it.glow > 0.5) {
      ctx.shadowColor = 'rgb(' + it.col[0] + ',' + it.col[1] + ',' + it.col[2] + ')';
      ctx.shadowBlur = 12;
    }
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  function drawPoint(it) {
    var p = it.p;
    ctx.beginPath();
    ctx.arc(p.x, p.y, Math.max(0.5, it.size), 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(' + it.col[0] + ',' + it.col[1] + ',' + it.col[2] + ',' + it.glow + ')';
    if (it.glow > 0.5) {
      ctx.shadowColor = 'rgb(' + it.col[0] + ',' + it.col[1] + ',' + it.col[2] + ')';
      ctx.shadowBlur = 10;
    }
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // ---------------------------------------------------------------------------
  // Main loop
  // ---------------------------------------------------------------------------
  function frame(ts) {
    if (!lastTs) lastTs = ts;
    var dt = (ts - lastTs) / 1000;
    lastTs = ts;
    if (dt > 0.1) dt = 0.1;

    // FPS accounting
    fpsAccum += dt;
    fpsFrames++;
    fpsTimer += dt;
    if (fpsTimer >= 0.5) {
      fps = Math.round(fpsFrames / fpsAccum);
      fpsAccum = 0;
      fpsFrames = 0;
      fpsTimer = 0;
    }

    if (!paused) simTime += dt * speed;

    render();

    rafId = requestAnimationFrame(frame);
  }

  // ---------------------------------------------------------------------------
  // Sizing / DPR
  // ---------------------------------------------------------------------------
  function resize() {
    dpr = window.devicePixelRatio || 1;
    W = canvas.clientWidth || window.innerWidth;
    H = canvas.clientHeight || window.innerHeight;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    cam.focal = Math.min(W, H) * 1.1;
  }

  // ---------------------------------------------------------------------------
  // Interaction
  // ---------------------------------------------------------------------------
  function onDown(e) {
    dragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
  }
  function onMove(e) {
    if (!dragging) return;
    var dx = e.clientX - lastX;
    var dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    cam.yaw += dx * 0.005;
    cam.pitch += dy * 0.005;
    cam.pitch = clamp(cam.pitch, -1.4, 1.4);
  }
  function onUp() { dragging = false; }
  function onWheel(e) {
    e.preventDefault();
    cam.dist += e.deltaY * 0.01;
    cam.dist = clamp(cam.dist, cam.minDist, cam.maxDist);
  }

  function attachEvents() {
    canvas.addEventListener('mousedown', onDown);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    canvas.addEventListener('wheel', onWheel, { passive: false });
    // Touch support
    canvas.addEventListener('touchstart', function (e) {
      if (e.touches.length) { onDown({ clientX: e.touches[0].clientX, clientY: e.touches[0].clientY }); }
    }, { passive: true });
    canvas.addEventListener('touchmove', function (e) {
      if (e.touches.length) { onMove({ clientX: e.touches[0].clientX, clientY: e.touches[0].clientY }); }
    }, { passive: true });
    canvas.addEventListener('touchend', onUp);
    window.addEventListener('resize', resize);
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------
  function init(cv) {
    canvas = cv;
    ctx = canvas.getContext('2d');
    resize();
    buildScene();
    attachEvents();
    lastTs = 0;
    if (rafId) cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(frame);
  }

  function setSpeed(v) {
    speed = clamp(Number(v) || 1, 0, 5);
  }

  function togglePause() {
    paused = !paused;
    return paused;
  }

  function toggleWireframe() {
    wireframe = !wireframe;
    return wireframe;
  }

  function reset() {
    cam.yaw = 0.6;
    cam.pitch = 0.35;
    cam.dist = 14;
    simTime = 0;
    speed = 1.0;
    paused = false;
    wireframe = false;
  }

  function getStats() {
    return { fps: fps, polys: polys };
  }

  // Expose
  if (typeof window !== 'undefined') {
    window.Engine3D = Engine3D;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = Engine3D;
  }
})();
