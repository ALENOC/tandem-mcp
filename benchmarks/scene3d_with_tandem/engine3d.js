(function () {
  'use strict';

  var TAU = Math.PI * 2;

  function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }
  function lerp(a, b, t) { return a + (b - a) * t; }

  function PortalEngine(canvas) {
    var ctx = canvas.getContext('2d');
    var W = 0, H = 0, DPR = 1;

    // ---- camera ----
    var cam = { yaw: 0.7, pitch: 0.32, dist: 9.5, target: [0, 0.7, 0] };
    var camHome = { yaw: 0.7, pitch: 0.32, dist: 9.5 };

    // ---- state ----
    var t = 0;
    var speed = 1;
    var autoOrbit = true;
    var polys = [];
    var stars = [];
    var energy = [];
    var lastNow = 0;
    var dragging = false;
    var lastX = 0, lastY = 0;

    // ---- resize ----
    function resize() {
      DPR = window.devicePixelRatio || 1;
      W = canvas.clientWidth || window.innerWidth;
      H = canvas.clientHeight || window.innerHeight;
      canvas.width = Math.round(W * DPR);
      canvas.height = Math.round(H * DPR);
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    }

    // ---- projection ----
    function project(x, y, z) {
      var dx = x - cam.target[0];
      var dy = y - cam.target[1];
      var dz = z - cam.target[2];
      var cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw);
      var x1 = dx * cy - dz * sy;
      var z1 = dx * sy + dz * cy;
      var y1 = dy;
      var cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);
      var y2 = y1 * cp - z1 * sp;
      var z2 = y1 * sp + z1 * cp;
      var x2 = x1;
      var zc = z2 + cam.dist;
      if (zc < 0.1) zc = 0.1;
      var f = (H * 0.92) / zc;
      return {
        x: W / 2 + x2 * f,
        y: H / 2 - y2 * f,
        z: zc,
        s: f
      };
    }

    // ---- polygon helpers ----
    function addBox(cx, cy, cz, sx, sy, sz, fill, stroke, glow) {
      var hx = sx / 2, hy = sy / 2, hz = sz / 2;
      var v = [
        [cx - hx, cy - hy, cz - hz],
        [cx + hx, cy - hy, cz - hz],
        [cx + hx, cy + hy, cz - hz],
        [cx - hx, cy + hy, cz - hz],
        [cx - hx, cy - hy, cz + hz],
        [cx + hx, cy - hy, cz + hz],
        [cx + hx, cy + hy, cz + hz],
        [cx - hx, cy + hy, cz + hz]
      ];
      var faces = [
        [0, 1, 2, 3], [5, 4, 7, 6], [4, 0, 3, 7],
        [1, 5, 6, 2], [3, 2, 6, 7], [4, 5, 1, 0]
      ];
      for (var i = 0; i < faces.length; i++) {
        var f = faces[i];
        var pts = [v[f[0]], v[f[1]], v[f[2]], v[f[3]]];
        var cxp = 0, cyp = 0, czp = 0;
        for (var k = 0; k < 4; k++) { cxp += pts[k][0]; cyp += pts[k][1]; czp += pts[k][2]; }
        cxp /= 4; cyp /= 4; czp /= 4;
        polys.push({ pts: pts, cx: cxp, cy: cyp, cz: czp, fill: fill, stroke: stroke, glow: glow, kind: 'box' });
      }
    }

    function addOcta(cx, cy, cz, r, fill, stroke, glow) {
      var v = [
        [cx, cy + r, cz], [cx, cy - r, cz],
        [cx + r, cy, cz], [cx - r, cy, cz],
        [cx, cy, cz + r], [cx, cy, cz - r]
      ];
      var faces = [
        [0, 2, 4], [0, 4, 3], [0, 3, 5], [0, 5, 2],
        [1, 4, 2], [1, 3, 4], [1, 5, 3], [1, 2, 5]
      ];
      for (var i = 0; i < faces.length; i++) {
        var f = faces[i];
        var pts = [v[f[0]], v[f[1]], v[f[2]]];
        var cxp = 0, cyp = 0, czp = 0;
        for (var k = 0; k < 3; k++) { cxp += pts[k][0]; cyp += pts[k][1]; czp += pts[k][2]; }
        cxp /= 3; cyp /= 3; czp /= 3;
        polys.push({ pts: pts, cx: cxp, cy: cyp, cz: czp, fill: fill, stroke: stroke, glow: glow, kind: 'octa' });
      }
    }

    // ---- scene build ----
    function buildScene() {
      polys.length = 0;
      var bob = Math.sin(t * 0.8) * 0.12;

      // stepped obsidian island
      var steps = [
        { y: -1.9, s: 5.2, h: 0.5, c: '#0a0a14' },
        { y: -1.4, s: 4.2, h: 0.5, c: '#0d0d1a' },
        { y: -0.9, s: 3.2, h: 0.5, c: '#10101f' },
        { y: -0.4, s: 2.2, h: 0.5, c: '#141424' }
      ];
      for (var i = 0; i < steps.length; i++) {
        var st = steps[i];
        addBox(0, st.y + bob, 0, st.s, st.h, st.s, st.c, 'rgba(56,189,248,0.35)', 6);
      }

      // twin monolith pillars
      var top = 2.6 + bob;
      addBox(-1.6, top / 2 + bob, 0, 0.5, top, 0.5, '#0b0b16', 'rgba(56,189,248,0.5)', 8);
      addBox(1.6, top / 2 + bob, 0, 0.5, top, 0.5, '#0b0b16', 'rgba(56,189,248,0.5)', 8);

      // top lintel arch
      addBox(0, top + 0.25 + bob, 0, 3.7, 0.5, 0.5, '#0e0e1c', 'rgba(56,189,248,0.6)', 10);

      // 6 orbiting glowing octahedron crystals
      for (var c = 0; c < 6; c++) {
        var a = t * 0.9 + (c / 6) * TAU;
        var ox = Math.cos(a) * 2.6;
        var oz = Math.sin(a) * 2.6;
        var oy = 1.2 + bob + Math.sin(t * 2 + c) * 0.25;
        addOcta(ox, oy, oz, 0.28, 'rgba(56,189,248,0.85)', 'rgba(186,230,253,0.95)', 14);
      }
    }

    // ---- stars ----
    function initStars() {
      stars.length = 0;
      for (var i = 0; i < 160; i++) {
        var r = 14 + Math.random() * 10;
        var th = Math.random() * TAU;
        var ph = Math.acos(2 * Math.random() - 1);
        stars.push({
          x: r * Math.sin(ph) * Math.cos(th),
          y: r * Math.cos(ph) * 0.6 + 2,
          z: r * Math.sin(ph) * Math.sin(th),
          tw: Math.random() * TAU,
          sp: 1 + Math.random() * 3,
          sz: 0.6 + Math.random() * 1.4
        });
      }
    }

    // ---- energy particles ----
    function initEnergy() {
      energy.length = 0;
      for (var i = 0; i < 110; i++) {
        energy.push({
          x: (Math.random() - 0.5) * 4,
          y: -2 + Math.random() * 5,
          z: (Math.random() - 0.5) * 4,
          vy: 0.4 + Math.random() * 0.8,
          sz: 1 + Math.random() * 2.5,
          hue: 180 + Math.random() * 60
        });
      }
    }

    // ---- step ----
    function step(dt, spd, orbit) {
      speed = spd;
      autoOrbit = orbit;
      t += dt * speed;
      if (autoOrbit) cam.yaw += dt * 0.15 * speed;

      for (var i = 0; i < energy.length; i++) {
        var p = energy[i];
        p.y += p.vy * dt * speed;
        if (p.y > 3.2) {
          p.y = -2;
          p.x = (Math.random() - 0.5) * 4;
          p.z = (Math.random() - 0.5) * 4;
        }
      }
    }

    // ---- render ----
    function render(now) {
      if (!lastNow) lastNow = now;
      var dt = clamp((now - lastNow) / 1000, 0, 0.05);
      lastNow = now;
      step(dt, speed, autoOrbit);
      buildScene();

      ctx.clearRect(0, 0, W, H);

      // background
      var bg = ctx.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * 0.7);
      bg.addColorStop(0, '#0a1024');
      bg.addColorStop(1, '#040610');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, W, H);

      // stars
      for (var i = 0; i < stars.length; i++) {
        var s = stars[i];
        var p = project(s.x, s.y, s.z);
        if (p.z <= 0.1) continue;
        var tw = 0.4 + 0.6 * (0.5 + 0.5 * Math.sin(t * s.sp + s.tw));
        ctx.globalAlpha = tw;
        ctx.fillStyle = '#cfe8ff';
        ctx.beginPath();
        ctx.arc(p.x, p.y, s.sz * (p.s / (H * 0.9)) * 3, 0, TAU);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      // cyber grid floor at y = -2.0
      drawGrid();

      // depth sort polys (painter's)
      polys.sort(function (a, b) { return b.z - a.z; });
      for (var j = 0; j < polys.length; j++) {
        var poly = polys[j];
        var proj = [];
        for (var k = 0; k < poly.pts.length; k++) {
          proj.push(project(poly.pts[k][0], poly.pts[k][1], poly.pts[k][2]));
        }
        ctx.beginPath();
        ctx.moveTo(proj[0].x, proj[0].y);
        for (var m = 1; m < proj.length; m++) ctx.lineTo(proj[m].x, proj[m].y);
        ctx.closePath();
        if (poly.glow) {
          ctx.shadowColor = poly.stroke || poly.fill;
          ctx.shadowBlur = poly.glow;
        }
        ctx.fillStyle = poly.fill;
        ctx.fill();
        ctx.shadowBlur = 0;
        if (poly.stroke) {
          ctx.strokeStyle = poly.stroke;
          ctx.lineWidth = 1.2;
          ctx.stroke();
        }
      }

      // volumetric portal core in arch center
      drawPortal();

      // energy rings (2 counter-rotating)
      drawRings();

      // energy particles
      for (var e = 0; e < energy.length; e++) {
        var ep = energy[e];
        var pp = project(ep.x, ep.y, ep.z);
        if (pp.z <= 0.1) continue;
        var g = ctx.createRadialGradient(pp.x, pp.y, 0, pp.x, pp.y, ep.sz * 3);
        g.addColorStop(0, 'hsla(' + ep.hue + ',100%,75%,0.9)');
        g.addColorStop(1, 'hsla(' + ep.hue + ',100%,60%,0)');
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(pp.x, pp.y, ep.sz * 3, 0, TAU);
        ctx.fill();
      }

      return { polys: polys.length, particles: energy.length };
    }

    function drawGrid() {
      var N = 8, span = 12;
      ctx.lineWidth = 1;
      for (var i = -N; i <= N; i++) {
        var a = project(i * (span / N), -2.0, -span / 2);
        var b = project(i * (span / N), -2.0, span / 2);
        ctx.strokeStyle = 'rgba(56,189,248,' + (0.05 + 0.12 * (1 - Math.abs(i) / N)) + ')';
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
        var c = project(-span / 2, -2.0, i * (span / N));
        var d = project(span / 2, -2.0, i * (span / N));
        ctx.beginPath();
        ctx.moveTo(c.x, c.y);
        ctx.lineTo(d.x, d.y);
        ctx.stroke();
      }
    }

    function drawPortal() {
      var c = project(0, 1.4 + Math.sin(t * 0.8) * 0.12, 0);
      var R = 1.1 * (c.s / (H * 0.9)) * 3;
      var g = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, R);
      g.addColorStop(0, 'rgba(255,255,255,0.95)');
      g.addColorStop(0.3, 'rgba(120,220,255,0.7)');
      g.addColorStop(0.7, 'rgba(56,189,248,0.25)');
      g.addColorStop(1, 'rgba(56,189,248,0)');
      ctx.globalCompositeOperation = 'lighter';
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(c.x, c.y, R, 0, TAU);
      ctx.fill();
      ctx.globalCompositeOperation = 'source-over';
    }

    function drawRings() {
      var cy = 1.4 + Math.sin(t * 0.8) * 0.12;
      var rings = [
        { r: 1.3, sp: 1.0, col: 'rgba(120,220,255,0.8)' },
        { r: 1.6, sp: -1.4, col: 'rgba(186,140,255,0.7)' }
      ];
      for (var i = 0; i < rings.length; i++) {
        var rg = rings[i];
        var seg = 40;
        ctx.beginPath();
        for (var k = 0; k <= seg; k++) {
          var a = (k / seg) * TAU + t * rg.sp;
          var x = Math.cos(a) * rg.r;
          var z = Math.sin(a) * rg.r;
          var y = cy + Math.sin(a * 3 + t * 2) * 0.05;
          var p = project(x, y, z);
          if (k === 0) ctx.moveTo(p.x, p.y);
          else ctx.lineTo(p.x, p.y);
        }
        ctx.strokeStyle = rg.col;
        ctx.lineWidth = 2;
        ctx.shadowColor = rg.col;
        ctx.shadowBlur = 12;
        ctx.stroke();
        ctx.shadowBlur = 0;
      }
    }

    // ---- input ----
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
      cam.pitch = clamp(cam.pitch + dy * 0.005, -1.2, 1.4);
    }
    function onUp() { dragging = false; }
    function onWheel(e) {
      e.preventDefault();
      cam.dist = clamp(cam.dist + e.deltaY * 0.01, 4, 20);
    }

    canvas.addEventListener('mousedown', onDown);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    canvas.addEventListener('wheel', onWheel, { passive: false });

    function resetCamera() {
      cam.yaw = camHome.yaw;
      cam.pitch = camHome.pitch;
      cam.dist = camHome.dist;
    }

    resize();
    initStars();
    initEnergy();

    return {
      canvas: canvas,
      resize: resize,
      project: project,
      step: step,
      render: render,
      resetCamera: resetCamera,
      setSpeed: function (s) { speed = s; },
      setAutoOrbit: function (b) { autoOrbit = b; },
      getCamera: function () { return cam; }
    };
  }

  window.PortalEngine = PortalEngine;
})();
