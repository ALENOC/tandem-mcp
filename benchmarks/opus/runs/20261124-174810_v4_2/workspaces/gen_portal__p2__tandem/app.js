// app.js
// Wires the software 3D engine + scene to a full-viewport canvas, drives the
// animation loop, and manages the glassmorphism HUD.

(function (global) {
  'use strict';

  const E = global.Engine3D;
  const V3 = E.V3;

  // ---------- canvas ----------
  const canvas = document.getElementById('c');
  const ctx = canvas.getContext('2d');

  const renderer = new E.Renderer();
  renderer.ctx = ctx;

  const scene = global.Scene.createScene();

  // ---------- app state ----------
  const app = {
    paused: false,
    orbit: true,
    speed: 1,
    camAngle: 0.6,
    time: 0,
    stats: { fps: 0, polys: 0, parts: 110 },
    counts: scene.counts
  };
  global.app = app;

  // Camera parameters.
  const CAM = {
    radius: 18,
    baseY: 5.5,
    bobAmp: 0.35,
    bobSpeed: 0.5
  };

  const DEFAULTS = { camAngle: 0.6, time: 0, speed: 1 };

  // ---------- HUD elements ----------
  const elFps = document.getElementById('fps');
  const elPolys = document.getElementById('polys');
  const elParts = document.getElementById('parts');
  const btnPause = document.getElementById('btnPause');
  const btnOrbit = document.getElementById('btnOrbit');
  const btnReset = document.getElementById('btnReset');
  const speedInput = document.getElementById('speed');

  // ---------- sizing ----------
  function resize() {
    const dpr = global.devicePixelRatio || 1;
    const w = global.innerWidth;
    const h = global.innerHeight;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    renderer.resize(w, h);
  }
  global.addEventListener('resize', resize);
  resize();

  // ---------- camera ----------
  function computeCamera() {
    const a = app.camAngle;
    const bob = CAM.bobAmp * Math.sin(app.time * CAM.bobSpeed);
    const eye = {
      x: CAM.radius * Math.sin(a),
      y: CAM.baseY + bob,
      z: CAM.radius * Math.cos(a)
    };
    const target = { x: scene.portal.center.x, y: scene.portal.center.y, z: scene.portal.center.z };
    return E.lookAt(eye, target, { x: 0, y: 1, z: 0 });
  }

  // ---------- background ----------
  function drawBackground() {
    const w = renderer.width;
    const h = renderer.height;
    const g = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, Math.max(w, h) * 0.7);
    g.addColorStop(0, '#1a0b3d');
    g.addColorStop(1, '#02010a');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
  }

  // ---------- stars ----------
  function drawStars(cam) {
    for (let i = 0; i < scene.stars.length; i++) {
      const s = scene.stars[i];
      const p = E.project(cam, s, renderer.width, renderer.height, renderer.fov, renderer.near);
      if (!p) continue;
      const tw = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(app.time * 2 + s.phase));
      ctx.globalAlpha = tw;
      ctx.fillStyle = '#ffffff';
      ctx.beginPath();
      ctx.arc(p.x, p.y, s.size, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // ---------- grid floor ----------
  // Project a world point to camera space (x right, y up, z forward).
  function camPoint(cam, p) {
    return E.toCamera(cam, p);
  }
  // Clip a segment in camera space against the near plane (z = near).
  // Returns {a, b} in camera space, or null if fully behind.
  function clipNear(cam, a, b, near) {
    const za = a.z, zb = b.z;
    if (za < near && zb < near) return null;
    if (za >= near && zb >= near) return { a: a, b: b };
    const t = (near - za) / (zb - za);
    const c = { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, z: near };
    if (za < near) return { a: c, b: b };
    return { a: a, b: c };
  }
  function camToScreen(cam, c, w, h, fov) {
    const f = (h / 2) / Math.tan(fov / 2);
    return { x: w / 2 + (c.x * f) / c.z, y: h / 2 - (c.y * f) / c.z };
  }
  function drawGrid(cam) {
    const g = scene.grid;
    const half = g.size;
    const step = g.step;
    const y = g.y;
    const w = renderer.width, h = renderer.height;
    const near = renderer.near;
    ctx.lineWidth = 1;
    // Lines along X (varying z).
    for (let z = -half; z <= half + 0.001; z += step) {
      const a = camPoint(cam, { x: -half, y: y, z: z });
      const b = camPoint(cam, { x: half, y: y, z: z });
      const seg = clipNear(cam, a, b, near);
      if (!seg) continue;
      const pa = camToScreen(cam, seg.a, w, h, renderer.fov);
      const pb = camToScreen(cam, seg.b, w, h, renderer.fov);
      const dist = Math.abs(z) / half;
      ctx.strokeStyle = 'rgba(0,240,255,' + (0.28 * (1 - dist)).toFixed(3) + ')';
      ctx.beginPath();
      ctx.moveTo(pa.x, pa.y);
      ctx.lineTo(pb.x, pb.y);
      ctx.stroke();
    }
    // Lines along Z (varying x).
    for (let x = -half; x <= half + 0.001; x += step) {
      const a = camPoint(cam, { x: x, y: y, z: -half });
      const b = camPoint(cam, { x: x, y: y, z: half });
      const seg = clipNear(cam, a, b, near);
      if (!seg) continue;
      const pa = camToScreen(cam, seg.a, w, h, renderer.fov);
      const pb = camToScreen(cam, seg.b, w, h, renderer.fov);
      const dist = Math.abs(x) / half;
      ctx.strokeStyle = 'rgba(0,240,255,' + (0.28 * (1 - dist)).toFixed(3) + ')';
      ctx.beginPath();
      ctx.moveTo(pa.x, pa.y);
      ctx.lineTo(pb.x, pb.y);
      ctx.stroke();
    }
  }

  // ---------- portal core ----------
  function drawPortalCore(cam) {
    const c = scene.portal.center;
    const p = E.project(cam, c, renderer.width, renderer.height, renderer.fov, renderer.near);
    if (!p) return;
    const f = (renderer.height / 2) / Math.tan(renderer.fov / 2);
    const scale = f / p.z;
    const r = scene.portal.radius * scale;

    // Glowing radial-gradient disc: magenta core to cyan edge.
    const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, r);
    grad.addColorStop(0, '#ff2bd6');
    grad.addColorStop(0.55, 'rgba(255,43,214,0.55)');
    grad.addColorStop(1, 'rgba(0,240,255,0)');
    ctx.globalCompositeOperation = 'lighter';
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalCompositeOperation = 'source-over';

    // Two counter-rotating rings drawn as bright glowing projected 3D polylines,
    // on top of the disc, centered between the pillars, radius > disc radius.
    drawRing(cam, c, scene.portal.radius * 1.15, app.time * 0.8, '#00f0ff', 2.5);
    drawRing(cam, c, scene.portal.radius * 1.45, -app.time * 0.5, '#ff2bd6', 3);
  }

  function drawRing(cam, center, radius, angle, color, width) {
    const seg = scene.portal.ringSegments;
    const pts = [];
    for (let i = 0; i <= seg; i++) {
      const t = (i / seg) * Math.PI * 2;
      const a = t + angle;
      pts.push({
        x: center.x + radius * Math.cos(a),
        y: center.y + radius * Math.sin(a),
        z: center.z
      });
    }
    const proj = renderer.projectPolyline(pts);
    if (!proj) return;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.shadowColor = color;
    ctx.shadowBlur = 14;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(proj[0].x, proj[0].y);
    for (let i = 1; i < proj.length; i++) ctx.lineTo(proj[i].x, proj[i].y);
    ctx.stroke();
    ctx.restore();
  }

  // ---------- solid geometry (boxes + crystals) ----------
  function buildSolidItems() {
    const items = [];
    // Box faces.
    for (let bi = 0; bi < scene.boxes.length; bi++) {
      const box = scene.boxes[bi];
      for (let fi = 0; fi < box.faces.length; fi++) {
        const face = box.faces[fi];
        items.push({ kind: 'quad', verts: face.v, normal: face.n, base: box.base, edge: box.edge });
      }
    }
    // Crystal triangles (spun on own axis + bobbed).
    for (let ci = 0; ci < scene.crystals.length; ci++) {
      const cr = scene.crystals[ci];
      const orbitA = app.time * cr.orbitSpeed + cr.orbitPhase;
      const cx = Math.cos(orbitA) * cr.orbitRadius;
      const cz = Math.sin(orbitA) * cr.orbitRadius;
      const cy = scene.portal.center.y + cr.bobAmp * Math.sin(app.time * 1.5 + cr.bobPhase);
      const spin = app.time * cr.spinSpeed;
      const axis = V3.normalize(cr.spinAxis);
      const tris = cr.base;
      for (let ti = 0; ti < tris.length; ti++) {
        const tri = tris[ti];
        const wv = [];
        for (let vi = 0; vi < 3; vi++) {
          const v = tri[vi];
          const rv = rotateAroundAxis(v, axis, spin);
          wv.push({ x: rv.x + cx, y: rv.y + cy, z: rv.z + cz });
        }
        items.push({ kind: 'tri', verts: wv, base: cr.baseColor, edge: cr.edge });
      }
    }
    return items;
  }

  // Rodrigues rotation of vector v around unit axis by angle.
  function rotateAroundAxis(v, axis, angle) {
    const c = Math.cos(angle);
    const s = Math.sin(angle);
    const k = axis;
    const dot = V3.dot(k, v);
    const cross = V3.cross(k, v);
    return {
      x: v.x * c + cross.x * s + k.x * dot * (1 - c),
      y: v.y * c + cross.y * s + k.y * dot * (1 - c),
      z: v.z * c + cross.z * s + k.z * dot * (1 - c)
    };
  }

  // ---------- particles ----------
  function updateParticles(dt) {
    for (let i = 0; i < scene.particles.length; i++) {
      const p = scene.particles[i];
      p.y += p.vy * dt;
      p.life += dt * 0.4;
      if (p.y > 6 || p.life > 1) {
        // Respawn at the bottom.
        p.x = (Math.random() - 0.5) * 5;
        p.y = 0.2 + Math.random() * 0.5;
        p.z = (Math.random() - 0.5) * 5;
        p.life = 0;
      }
    }
  }

  function drawParticles(cam) {
    for (let i = 0; i < scene.particles.length; i++) {
      const p = scene.particles[i];
      const proj = E.project(cam, p, renderer.width, renderer.height, renderer.fov, renderer.near);
      if (!proj) continue;
      const fade = 1 - p.life;
      ctx.globalAlpha = Math.max(0, fade);
      ctx.fillStyle = p.hue === 'cyan' ? '#00f0ff' : '#ff2bd6';
      ctx.beginPath();
      ctx.arc(proj.x, proj.y, 2.2, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  // ---------- HUD ----------
  function updateHud() {
    elFps.textContent = String(app.stats.fps);
    elPolys.textContent = String(app.stats.polys);
    elParts.textContent = String(app.stats.parts);
  }

  // ---------- main loop ----------
  let lastTs = 0;
  let fpsAccum = 0;
  let fpsFrames = 0;
  let fpsTimer = 0;

  function frame(ts) {
    if (!lastTs) lastTs = ts;
    let dt = (ts - lastTs) / 1000;
    lastTs = ts;
    if (dt > 0.1) dt = 0.1;

    // FPS (measured over real time).
    fpsFrames++;
    fpsTimer += dt;
    if (fpsTimer >= 0.5) {
      app.stats.fps = Math.round(fpsFrames / fpsTimer);
      fpsFrames = 0;
      fpsTimer = 0;
    }

    // Advance time / camera only when not paused.
    if (!app.paused) {
      const sdt = dt * app.speed;
      app.time += sdt;
      if (app.orbit) app.camAngle += sdt * 0.35;
      updateParticles(sdt);
    }

    const cam = computeCamera();
    renderer.begin(cam);

    drawBackground();
    drawStars(cam);
    drawGrid(cam);
    drawPortalCore(cam);

    // Painter's algorithm over all solid geometry.
    renderer.drawSorted(buildSolidItems());

    drawParticles(cam);

    app.stats.polys = renderer.polys;
    app.stats.parts = scene.counts.particles;
    updateHud();

    global.requestAnimationFrame(frame);
  }

  // ---------- controls ----------
  btnPause.addEventListener('click', function () {
    app.paused = !app.paused;
    btnPause.textContent = app.paused ? 'Resume' : 'Pause';
  });

  btnOrbit.addEventListener('click', function () {
    app.orbit = !app.orbit;
    btnOrbit.textContent = app.orbit ? 'Orbit ON' : 'Orbit OFF';
  });

  btnReset.addEventListener('click', function () {
    app.camAngle = DEFAULTS.camAngle;
    app.time = DEFAULTS.time;
    app.speed = DEFAULTS.speed;
    speedInput.value = String(DEFAULTS.speed);
    app.paused = false;
    btnPause.textContent = 'Pause';
  });

  speedInput.addEventListener('input', function () {
    app.speed = parseFloat(speedInput.value);
  });

  global.requestAnimationFrame(frame);
})(window);
