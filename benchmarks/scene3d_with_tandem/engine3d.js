/* engine3d.js
 * Pure HTML5 2D-canvas software 3D engine.
 * No WebGL, no external libraries.
 * Perspective projection + painter's algorithm z-sorting.
 * Flat shading with crisp neon wireframe edges.
 *
 * Scene: Neon Portal Monument (totem)
 *   - cyber-grid floor
 *   - two-tier stepped obsidian platform
 *   - twin pillars + lintel beam + crown cap
 *   - radial-gradient glowing portal core + 2 counter-rotating tilted rings
 *   - 6 orbiting octahedral crystals (wireframe)
 *   - twinkling stars + rising neon particles
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
    toggleOrbit: toggleOrbit,
    reset: reset,
    getStats: getStats
  };

  // ---------------------------------------------------------------------------
  // Module state
  // ---------------------------------------------------------------------------
  var canvas = null;
  var ctx = null;
  var W = 0;
  var H = 0;
  var dpr = 1;

  // Camera (orbit)
  var cam = {
    yaw: 0.55,
    pitch: 0.34,
    dist: 9.6,
    minDist: 4,
    maxDist: 30,
    fov: 580,
    focal: 580
  };

  var speed = 1.0;
  var paused = false;
  var wireframe = false;
  var autoOrbit = true;

  var simTime = 0;
  var lastTs = 0;
  var rafId = 0;

  // Stats
  var fps = 0;
  var polys = 0;
  var parts = 0;
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
  var platform = null;
  var pillars = null;
  var lintel = null;
  var crown = null;
  var crystals = [];
  var particles = [];

  // Neon palette
  var CYAN = [0, 255, 255];
  var MAGENTA = [255, 0, 200];

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
  // Geometry builders
  // ---------------------------------------------------------------------------
  // Axis-aligned box centered at (cx,cy,cz) with half-extents (hx,hy,hz).
  // Returns { verts, faces } with outward-facing normals.
  function makeBox(cx, cy, cz, hx, hy, hz) {
    var v = [
      { x: cx - hx, y: cy - hy, z: cz - hz },
      { x: cx + hx, y: cy - hy, z: cz - hz },
      { x: cx + hx, y: cy + hy, z: cz - hz },
      { x: cx - hx, y: cy + hy, z: cz - hz },
      { x: cx - hx, y: cy - hy, z: cz + hz },
      { x: cx + hx, y: cy - hy, z: cz + hz },
      { x: cx + hx, y: cy + hy, z: cz + hz },
      { x: cx - hx, y: cy + hy, z: cz + hz }
    ];
    var faces = [
      [0, 1, 2, 3], // back  (-z)
      [5, 4, 7, 6], // front (+z)
      [4, 0, 3, 7], // left  (-x)
      [1, 5, 6, 2], // right (+x)
      [3, 2, 6, 7], // top   (+y)
      [4, 5, 1, 0]  // bottom(-y)
    ];
    return { verts: v, faces: faces };
  }

  // Octahedron centered at origin with radius r.
  function makeOcta(r) {
    var v = [
      { x: r, y: 0, z: 0 }, { x: -r, y: 0, z: 0 },
      { x: 0, y: r, z: 0 }, { x: 0, y: -r, z: 0 },
      { x: 0, y: 0, z: r }, { x: 0, y: 0, z: -r }
    ];
    var faces = [
      [0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4],
      [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5]
    ];
    return { verts: v, faces: faces };
  }

  // ---------------------------------------------------------------------------
  // Scene construction
  // ---------------------------------------------------------------------------
  function buildStars() {
    stars = [];
    var n = 180;
    for (var i = 0; i < n; i++) {
      var u = Math.random() * 2 - 1;
      var th = Math.random() * Math.PI * 2;
      var r = Math.sqrt(1 - u * u);
      var rad = 55 + Math.random() * 45;
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
    var ext = 22;
    var step = 2;
    var y = -2.0;
    var i;
    for (i = -ext; i <= ext; i += step) {
      gridLines.push({ a: { x: i, y: y, z: -ext }, b: { x: i, y: y, z: ext }, major: (i % 8 === 0) });
      gridLines.push({ a: { x: -ext, y: y, z: i }, b: { x: ext, y: y, z: i }, major: (i % 8 === 0) });
    }
  }

  function buildPlatform() {
    // Two-tier stepped obsidian platform.
    // Tier 1 (lower, wider) top at y=-1.25; Tier 2 (upper, narrower) top at y=-0.85.
    platform = {
      tier1: makeBox(0, -1.65, 0, 3.4, 0.4, 3.4), // top face at y=-1.25
      tier2: makeBox(0, -1.05, 0, 2.5, 0.2, 2.5)  // top face at y=-0.85
    };
  }

  function buildPillars() {
    // Twin pillars at x=+-1.25 from y=-0.85 to y=1.85 (center y=0.5, half-height 1.35).
    var py = 0.5, ph = 1.35, pw = 0.28;
    pillars = [
      makeBox(-1.25, py, 0, pw, ph, pw),
      makeBox(1.25, py, 0, pw, ph, pw)
    ];
    // Lintel beam at y=1.95 spanning the pillars.
    lintel = makeBox(0, 1.95, 0, 1.55, 0.22, 0.34);
    // Crown cap at y=2.32.
    crown = makeBox(0, 2.32, 0, 1.7, 0.18, 0.5);
  }

  function buildCrystals() {
    crystals = [];
    var n = 6;
    for (var i = 0; i < n; i++) {
      crystals.push({
        ang: (i / n) * Math.PI * 2,
        rad: 2.45,
        y: 0.5 + Math.sin(i * 1.7) * 0.4,
        spd: 0.5 + (i % 3) * 0.15,
        r: 0.34,
        hue: i % 2,
        spin: i * 0.9
      });
    }
  }

  function buildParticles() {
    particles = [];
    var n = 110;
    for (var i = 0; i < n; i++) {
      particles.push({
        x: (Math.random() * 2 - 1) * 6,
        z: (Math.random() * 2 - 1) * 6,
        y: -2 + Math.random() * 5,
        spd: 0.4 + Math.random() * 0.8,
        size: 0.05 + Math.random() * 0.08,
        hue: i % 2
      });
    }
  }

  function buildScene() {
    buildStars();
    buildGrid();
    buildPlatform();
    buildPillars();
    buildCrystals();
    buildParticles();
  }

  // ---------------------------------------------------------------------------
  // Rendering primitives (all pushed into a depth-sorted draw list)
  // ---------------------------------------------------------------------------
  var drawList = [];

  function pushPoly(verts, col, opts) {
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

  // Flat shading: ambient + diffuse from a fixed light, plus a small specular.
  function shadeFace(normal, baseCol, opts) {
    var light = normalize({ x: -0.4, y: 0.85, z: 0.55 });
    var ndl = dot(normal, light);
    if (ndl < 0) ndl = 0;
    var ambient = 0.22;
    var diff = ambient + (1 - ambient) * ndl;
    var view = { x: 0, y: 0, z: 1 };
    var half = normalize({
      x: light.x + view.x,
      y: light.y + view.y,
      z: light.z + view.z
    });
    var spec = Math.pow(Math.max(0, dot(normal, half)), 20) * (opts.specular || 0.5);
    var r = clamp(baseCol[0] * diff + 255 * spec, 0, 255) | 0;
    var g = clamp(baseCol[1] * diff + 255 * spec, 0, 255) | 0;
    var b = clamp(baseCol[2] * diff + 255 * spec, 0, 255) | 0;
    return [r, g, b];
  }

  // Draw a solid mesh (box / octahedron) with dark shaded faces + neon edges.
  // All faces are emitted and depth-sorted by the painter's algorithm.
  // mesh: { verts, faces } in world space.
  function drawMesh(mesh, baseCol, edgeCol, opts) {
    opts = opts || {};
    var wv = [];
    var pv = [];
    for (var i = 0; i < mesh.verts.length; i++) {
      var v = mesh.verts[i];
      wv.push(v);
      pv.push(toCamera(v));
    }
    for (var f = 0; f < mesh.faces.length; f++) {
      var idx = mesh.faces[f];
      var a = wv[idx[0]], b = wv[idx[1]], c = wv[idx[2]];
      var n = normalize(cross({ x: b.x - a.x, y: b.y - a.y, z: b.z - a.z },
                              { x: c.x - a.x, y: c.y - a.y, z: c.z - a.z }));

      var cam = [pv[idx[0]], pv[idx[1]], pv[idx[2]]];
      if (idx.length === 4) cam.push(pv[idx[3]]);
      var ok = true;
      for (var k = 0; k < cam.length; k++) if (cam[k].z <= 0.1) { ok = false; break; }
      if (!ok) continue;

      var col = shadeFace(n, baseCol, { specular: opts.specular || 0.4 });
      var verts = cam.map(function (q) { return project(q); });
      pushPoly(verts, col, { edge: edgeCol, glow: opts.glow });
      polys++;
    }
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
      var tw = 0.55 + 0.45 * Math.sin(simTime * 2 + s.tw);
      var a = clamp(s.b * tw, 0, 1);
      pushPoint(p, [255, 255, 255], 0.8 + s.b * 1.2, a);
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
      var fade = clamp(1.5 - (a.z + b.z) * 0.5 / cam.dist, 0.15, 1);
      var col = L.major ? CYAN : MAGENTA;
      var alpha = (L.major ? 0.6 : 0.32) * fade;
      pushLine(pa, pb, col, L.major ? 1.6 : 1, alpha);
    }
  }

  function drawPlatform() {
    // Dark obsidian fill with glowing cyan/magenta edges.
    drawMesh(platform.tier1, [12, 18, 40], CYAN, { specular: 0.3 });
    drawMesh(platform.tier2, [12, 18, 40], MAGENTA, { specular: 0.3 });
  }

  function drawPillars() {
    for (var i = 0; i < pillars.length; i++) {
      drawMesh(pillars[i], [14, 20, 44], i === 0 ? CYAN : MAGENTA, { specular: 0.35 });
    }
    drawMesh(lintel, [14, 20, 44], CYAN, { specular: 0.35 });
    drawMesh(crown, [16, 22, 48], MAGENTA, { specular: 0.4 });
  }

  // Radial-gradient glowing portal core at (0, 0.5, 0) + 2 counter-rotating tilted rings.
  function drawPortalCore() {
    var cx = 0, cy = 0.5, cz = 0;
    var cp = toCamera({ x: cx, y: cy, z: cz });
    if (cp.z <= 0.1) return;
    var p = project(cp);
    var pulse = 0.85 + 0.15 * Math.sin(simTime * 3);
    var rad = 1.4 * p.s * pulse;
    drawList.push({ type: 'core', p: p, rad: rad, depth: cp.z, pulse: pulse });

    // Two counter-rotating tilted neon rings.
    drawRing(cx, cy, cz, 1.0, 0.5, simTime * 0.8, CYAN, 2.4);
    drawRing(cx, cy, cz, 1.35, -0.35, -simTime * 0.6, MAGENTA, 2.0);
  }

  // A tilted neon ring (circle of radius r) centered at (cx,cy,cz).
  // tiltX/tiltZ are fixed plane tilts; spin rotates the ring in its own plane.
  function drawRing(cx, cy, cz, r, tiltX, spin, col, width) {
    var segs = 48;
    var ca = Math.cos(spin), sa = Math.sin(spin);
    var tx = Math.cos(tiltX), sx = Math.sin(tiltX);
    var prev = null;
    for (var i = 0; i <= segs; i++) {
      var a = (i / segs) * Math.PI * 2;
      var lx = Math.cos(a) * r;
      var ly = Math.sin(a) * r;
      // Rotate in-plane (spin) then tilt around X
      var rx = lx * ca - ly * sa;
      var ry = lx * sa + ly * ca;
      var wx = cx + rx;
      var wy = cy + ry * tx;
      var wz = cz + ry * sx;
      var cp = toCamera({ x: wx, y: wy, z: wz });
      if (cp.z <= 0.1) { prev = null; continue; }
      var p = project(cp);
      if (prev) {
        var pulse = 0.6 + 0.4 * Math.sin(simTime * 3 + i * 0.3);
        pushLine(prev, p, col, width, 0.5 + 0.5 * pulse);
      }
      prev = p;
    }
  }

  function drawCrystals() {
    for (var i = 0; i < crystals.length; i++) {
      var c = crystals[i];
      var ang = c.ang + simTime * c.spd;
      var cx = Math.cos(ang) * c.rad;
      var cz = Math.sin(ang) * c.rad;
      var cy = c.y + Math.sin(simTime * 1.5 + i) * 0.2;
      // Build a spinning octahedron at the crystal position.
      var base = makeOcta(c.r);
      var cr = Math.cos(simTime * 1.2 + c.spin), sr = Math.sin(simTime * 1.2 + c.spin);
      var verts = [];
      for (var k = 0; k < base.verts.length; k++) {
        var v = base.verts[k];
        var x = v.x * cr - v.z * sr;
        var z = v.x * sr + v.z * cr;
        verts.push({ x: cx + x, y: cy + v.y, z: cz + z });
      }
      var col = c.hue ? CYAN : MAGENTA;
      drawMesh({ verts: verts, faces: base.faces }, [10, 14, 30], col, { specular: 0.6, glow: true });
    }
  }

  function drawParticles() {
    for (var i = 0; i < particles.length; i++) {
      var p = particles[i];
      var y = p.y + (simTime * p.spd) % 5;
      if (y > 3) y -= 5;
      var cp = toCamera({ x: p.x, y: y, z: p.z });
      if (cp.z <= 0.1) continue;
      var pr = project(cp);
      var col = p.hue ? CYAN : MAGENTA;
      var size = p.size * pr.s * 0.6;
      pushPoint(pr, col, size, 0.85);
      parts++;
    }
  }

  // ---------------------------------------------------------------------------
  // Draw list rendering (painter's algorithm)
  // ---------------------------------------------------------------------------
  function render() {
    drawList.length = 0;
    polys = 0;
    parts = 0;

    drawStars();
    drawGrid();
    drawPlatform();
    drawPillars();
    drawPortalCore();
    drawCrystals();
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
      } else if (it.type === 'core') {
        drawCore(it);
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
      ctx.shadowBlur = 14;
    }
    ctx.fillStyle = 'rgb(' + it.col[0] + ',' + it.col[1] + ',' + it.col[2] + ')';
    ctx.fill();
    ctx.shadowBlur = 0;

    // Crisp neon edge
    if (it.opts.edge) {
      ctx.strokeStyle = 'rgba(' + it.opts.edge[0] + ',' + it.opts.edge[1] + ',' + it.opts.edge[2] + ',0.9)';
      ctx.lineWidth = 1.4;
      ctx.shadowColor = 'rgb(' + it.opts.edge[0] + ',' + it.opts.edge[1] + ',' + it.opts.edge[2] + ')';
      ctx.shadowBlur = 8;
      ctx.stroke();
      ctx.shadowBlur = 0;
    } else {
      ctx.strokeStyle = 'rgba(255,255,255,0.12)';
      ctx.lineWidth = 0.6;
      ctx.stroke();
    }
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

  function drawCore(it) {
    var p = it.p;
    var r = Math.max(4, it.rad);
    var g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, r);
    g.addColorStop(0, 'rgba(255,255,255,' + (0.95 * it.pulse) + ')');
    g.addColorStop(0.35, 'rgba(0,255,255,' + (0.7 * it.pulse) + ')');
    g.addColorStop(0.7, 'rgba(255,0,200,' + (0.35 * it.pulse) + ')');
    g.addColorStop(1, 'rgba(255,0,200,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.fill();
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

    if (!paused) {
      simTime += dt * speed;
      if (autoOrbit && !dragging) cam.yaw += dt * 0.25 * speed;
    }

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
    cam.focal = cam.fov;
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

  function toggleOrbit() {
    autoOrbit = !autoOrbit;
    return autoOrbit;
  }

  function reset() {
    cam.yaw = 0.55;
    cam.pitch = 0.34;
    cam.dist = 9.6;
    simTime = 0;
    speed = 1.0;
    paused = false;
    wireframe = false;
    autoOrbit = true;
  }

  function getStats() {
    return { fps: fps, polys: polys, parts: parts };
  }

  // Expose
  if (typeof window !== 'undefined') {
    window.Engine3D = Engine3D;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = Engine3D;
  }
})();
