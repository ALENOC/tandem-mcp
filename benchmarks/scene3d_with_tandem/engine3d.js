(function (global) {
  'use strict';

  var TAU = Math.PI * 2;

  function PortalEngine(canvas, hudRefs) {
    hudRefs = hudRefs || {};
    var ctx = canvas.getContext('2d');

    var W = 0, H = 0, DPR = 1;
    var cam = { yaw: 0.55, pitch: 0.34, dist: 9.6, fov: 580 };
    var LIGHT = { x: 0.48, y: 0.72, z: -0.5 };
    var t = 0, last = 0, speed = 1, playing = true, orbit = true;
    var fps = 0, fpsAcc = 0, fpsN = 0, fpsT = 0;
    var polyCount = 0, partCount = 0;
    var raf = 0;

    var stars = [];
    var parts = [];
    var polys = [];

    function resize() {
      DPR = Math.min(2, global.devicePixelRatio || 1);
      W = canvas.clientWidth || global.innerWidth || 800;
      H = canvas.clientHeight || global.innerHeight || 600;
      canvas.width = Math.max(1, Math.round(W * DPR));
      canvas.height = Math.max(1, Math.round(H * DPR));
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    }

    function project(x, y, z) {
      var cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw);
      var cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch);
      var x1 = x * cy - z * sy;
      var z1 = x * sy + z * cy;
      var y1 = y * cp - z1 * sp;
      var z2 = y * sp + z1 * cp;
      var rz = z2 + cam.dist;
      if (rz < 0.12) rz = 0.12;
      var s = (cam.fov * Math.min(W, H) / 720) / rz;
      return { x: W * 0.5 + x1 * s, y: H * 0.52 - y1 * s, s: s, rz: rz };
    }

    function shade(c, n) {
      var d = (n.x * LIGHT.x + n.y * LIGHT.y + n.z * LIGHT.z) * 0.5 + 0.5;
      var f = 0.42 + 0.72 * d;
      var r = Math.min(255, c[0] * f) | 0;
      var g = Math.min(255, c[1] * f) | 0;
      var b = Math.min(255, c[2] * f) | 0;
      return 'rgb(' + r + ',' + g + ',' + b + ')';
    }

    function addBox(cx, cy, cz, sx, sy, sz, fill, rim) {
      var hx = sx / 2, hy = sy / 2, hz = sz / 2;
      var v = [
        [cx - hx, cy - hy, cz - hz], [cx + hx, cy - hy, cz - hz],
        [cx + hx, cy + hy, cz - hz], [cx - hx, cy + hy, cz - hz],
        [cx - hx, cy - hy, cz + hz], [cx + hx, cy - hy, cz + hz],
        [cx + hx, cy + hy, cz + hz], [cx - hx, cy + hy, cz + hz]
      ];
      var faces = [
        [1, 2, 3, 0], [5, 4, 7, 6], [4, 0, 3, 7], [1, 5, 6, 2],
        [4, 5, 6, 7], [0, 1, 2, 3]
      ];
      var nrm = [
        [0, 0, -1], [0, 0, 1], [-1, 0, 0], [1, 0, 0], [0, 1, 0], [0, -1, 0]
      ];
      for (var i = 0; i < faces.length; i++) {
        var f = faces[i];
        var a = v[f[0]], b = v[f[1]], c = v[f[2]], d = v[f[3]];
        var pa = project(a[0], a[1], a[2]);
        var pb = project(b[0], b[1], b[2]);
        var pc = project(c[0], c[1], c[2]);
        var pd = project(d[0], d[1], d[2]);
        var cxp = (a[0] + b[0] + c[0] + d[0]) / 4;
        var cyp = (a[1] + b[1] + c[1] + d[1]) / 4;
        var czp = (a[2] + b[2] + c[2] + d[2]) / 4;
        var n = nrm[i];
        var depth = project(cxp, cyp, czp).rz;
        polys.push({
          type: 'box', depth: depth,
          pts: [pa, pb, pc, pd],
          fill: shade(fill, n), rim: rim
        });
      }
    }

    function addOcta(cx, cy, cz, rx, ry, rz, col, rim) {
      var top = [cx, cy + ry, cz];
      var bot = [cx, cy - ry, cz];
      var e0 = [cx + rx, cy, cz];
      var e1 = [cx, cy, cz + rz];
      var e2 = [cx - rx, cy, cz];
      var e3 = [cx, cy, cz - rz];
      var tris = [
        [top, e0, e1], [top, e1, e2], [top, e2, e3], [top, e3, e0],
        [bot, e1, e0], [bot, e2, e1], [bot, e3, e2], [bot, e0, e3]
      ];
      for (var i = 0; i < tris.length; i++) {
        var tr = tris[i];
        var A = tr[0], B = tr[1], C = tr[2];
        var ux = B[0] - A[0], uy = B[1] - A[1], uz = B[2] - A[2];
        var vx = C[0] - A[0], vy = C[1] - A[1], vz = C[2] - A[2];
        var nx = uy * vz - uz * vy;
        var ny = uz * vx - ux * vz;
        var nz = ux * vy - uy * vx;
        var nl = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1;
        nx /= nl; ny /= nl; nz /= nl;
        var pa = project(A[0], A[1], A[2]);
        var pb = project(B[0], B[1], B[2]);
        var pc = project(C[0], C[1], C[2]);
        var cxp = (A[0] + B[0] + C[0]) / 3;
        var cyp = (A[1] + B[1] + C[1]) / 3;
        var czp = (A[2] + B[2] + C[2]) / 3;
        polys.push({
          type: 'tri', depth: project(cxp, cyp, czp).rz,
          pts: [pa, pb, pc],
          fill: shade(col, { x: nx, y: ny, z: nz }), rim: rim
        });
      }
    }

    function addRing(cx, cy, cz, r, seg, tilt, spin, col, rim) {
      var ct = Math.cos(tilt), st = Math.sin(tilt);
      var ring = [];
      for (var i = 0; i < seg; i++) {
        var a = spin + i / seg * TAU;
        var x = Math.cos(a) * r;
        var z = Math.sin(a) * r;
        var y = 0;
        var y2 = y * ct - z * st;
        var z2 = y * st + z * ct + Math.cos(a + t) * 0.14;
        ring.push([cx + x, cy + y2, cz + z2]);
      }
      for (var j = 0; j < seg; j++) {
        var A = ring[j];
        var B = ring[(j + 1) % seg];
        var pa = project(A[0], A[1], A[2]);
        var pb = project(B[0], B[1], B[2]);
        var cxp = (A[0] + B[0]) / 2;
        var cyp = (A[1] + B[1]) / 2;
        var czp = (A[2] + B[2]) / 2;
        polys.push({
          type: 'line', depth: project(cxp, cyp, czp).rz,
          pts: [pa, pb], fill: col, rim: rim
        });
      }
    }

    function buildScene() {
      polys.length = 0;

      addBox(0, -1.25, 0, 4.6, 0.34, 4.6, [14, 21, 38], 'rgba(56,189,248,0.45)');
      addBox(0, -0.85, 0, 3.4, 0.36, 3.4, [20, 29, 52], 'rgba(232,121,249,0.5)');

      addBox(-1.25, 0.48, 0, 0.56, 2.3, 0.56, [18, 28, 50], 'rgba(56,189,248,0.65)');
      addBox(1.25, 0.48, 0, 0.56, 2.3, 0.56, [18, 28, 50], 'rgba(56,189,248,0.65)');

      addBox(0, 1.95, 0, 3.45, 0.46, 0.72, [24, 34, 62], 'rgba(232,121,249,0.75)');
      addBox(0, 2.32, 0, 2.1, 0.24, 0.46, [16, 24, 46], 'rgba(56,189,248,0.6)');

      var cyan = [22, 163, 224], mag = [192, 68, 226];
      var cyanRim = 'rgba(125,211,252,0.9)', magRim = 'rgba(245,208,254,0.9)';
      for (var i = 0; i < 6; i++) {
        var ang = t * 0.6 + i * TAU / 6;
        var cx = Math.cos(ang) * 2.45;
        var cz = Math.sin(ang) * 2.45;
        var cy = 0.35 + Math.sin(t * 1.9 + i * 1.05) * 0.28;
        var isCyan = i % 2 === 0;
        addOcta(cx, cy, cz, 0.26, 0.44, 0.26, isCyan ? cyan : mag, isCyan ? cyanRim : magRim);
      }

      addRing(0, 0.52, 0, 1.05, 44, 0.25, t * 0.9, 'rgba(125,211,252,0.9)', 'rgba(125,211,252,0.9)');
      addRing(0, 0.52, 0, 0.78, 36, -0.45, -t * 1.3, 'rgba(245,208,254,0.9)', 'rgba(245,208,254,0.9)');
    }

    function drawGrid() {
      var ext = 7, step = 1, y = -2.0;
      ctx.lineWidth = 1;
      for (var i = -ext; i <= ext; i += step) {
        var a1 = project(i, y, -ext), a2 = project(i, y, ext);
        var b1 = project(-ext, y, i), b2 = project(ext, y, i);
        if (i === 0) {
          ctx.strokeStyle = 'rgba(232,121,249,0.34)';
        } else {
          ctx.strokeStyle = 'rgba(56,189,248,0.16)';
        }
        ctx.beginPath();
        ctx.moveTo(a1.x, a1.y); ctx.lineTo(a2.x, a2.y);
        ctx.moveTo(b1.x, b1.y); ctx.lineTo(b2.x, b2.y);
        ctx.stroke();
      }
    }

    function drawStars() {
      for (var i = 0; i < stars.length; i++) {
        var s = stars[i];
        var tw = 0.5 + 0.5 * Math.sin(t * s.sp + s.ph);
        var a = 0.25 + 0.65 * tw;
        var x = (s.x * W) % W; if (x < 0) x += W;
        var y = (s.y * H) % H; if (y < 0) y += H;
        ctx.globalAlpha = a;
        ctx.fillStyle = s.c;
        ctx.beginPath();
        ctx.arc(x, y, s.r, 0, TAU);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    }

    function drawPortal() {
      var p = project(0, 0.52, 0);
      var R = 1.08 * p.s * 1.25;
      var g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, R);
      g.addColorStop(0, 'rgba(255,255,255,0.95)');
      g.addColorStop(0.4, 'rgba(125,211,252,0.85)');
      g.addColorStop(0.75, 'rgba(192,68,226,0.42)');
      g.addColorStop(1, 'rgba(192,68,226,0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(p.x, p.y, R, 0, TAU);
      ctx.fill();
    }

    function drawParts() {
      for (var i = 0; i < parts.length; i++) {
        var p = parts[i];
        var pr = project(p.x, p.y, p.z);
        var a = 0.35 + 0.5 * (0.5 + 0.5 * Math.sin(t * 2 + p.ph));
        ctx.globalAlpha = a;
        ctx.fillStyle = p.c;
        ctx.beginPath();
        ctx.arc(pr.x, pr.y, Math.max(0.6, p.r * pr.s * 0.02), 0, TAU);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    }

    function drawPolys() {
      polys.sort(function (a, b) { return b.depth - a.depth; });
      for (var i = 0; i < polys.length; i++) {
        var p = polys[i];
        if (p.type === 'line') {
          ctx.strokeStyle = p.fill;
          ctx.lineWidth = 2.2;
          ctx.beginPath();
          ctx.moveTo(p.pts[0].x, p.pts[0].y);
          ctx.lineTo(p.pts[1].x, p.pts[1].y);
          ctx.stroke();
        } else {
          ctx.beginPath();
          ctx.moveTo(p.pts[0].x, p.pts[0].y);
          for (var j = 1; j < p.pts.length; j++) ctx.lineTo(p.pts[j].x, p.pts[j].y);
          ctx.closePath();
          ctx.fillStyle = p.fill;
          ctx.fill();
          ctx.strokeStyle = p.rim;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }
    }

    function update(dt) {
      if (orbit) cam.yaw += dt * 0.12;
      for (var i = 0; i < parts.length; i++) {
        var p = parts[i];
        p.y += dt * p.vy;
        if (p.y > 3.2) { p.y = -1.6; }
      }
    }

    function frame(now) {
      raf = global.requestAnimationFrame ? global.requestAnimationFrame(frame) : 0;
      if (!last) last = now;
      var dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      if (playing) { t += dt * speed; update(dt * speed); }

      fpsAcc += dt; fpsN++;
      if (now - fpsT > 250) {
        fps = fpsN / Math.max(0.001, fpsAcc);
        fpsAcc = 0; fpsN = 0; fpsT = now;
      }

      buildScene();
      polyCount = polys.length;
      partCount = parts.length;

      ctx.clearRect(0, 0, W, H);
      drawStars();
      drawGrid();
      drawPortal();
      drawPolys();
      drawParts();

      if (hudRefs.fpsEl) hudRefs.fpsEl.textContent = Math.round(fps);
      if (hudRefs.polysEl) hudRefs.polysEl.textContent = polyCount;
      if (hudRefs.partsEl) hudRefs.partsEl.textContent = partCount;
    }

    function initStars() {
      stars.length = 0;
      for (var i = 0; i < 180; i++) {
        stars.push({
          x: Math.random(), y: Math.random(),
          r: 0.4 + Math.random() * 1.4,
          sp: 0.5 + Math.random() * 2.5,
          ph: Math.random() * TAU,
          c: Math.random() < 0.5 ? '#e0f2fe' : '#c7d2fe'
        });
      }
    }

    function initParts() {
      parts.length = 0;
      var cols = ['rgba(125,211,252,0.9)', 'rgba(245,208,254,0.9)'];
      for (var i = 0; i < 110; i++) {
        parts.push({
          x: (Math.random() - 0.5) * 4.5,
          y: -1.6 + Math.random() * 4.8,
          z: (Math.random() - 0.5) * 4.5,
          vy: 0.25 + Math.random() * 0.5,
          r: 0.5 + Math.random() * 1.2,
          ph: Math.random() * TAU,
          c: cols[i % 2]
        });
      }
    }

    function bind() {
      var dragging = false, px = 0, py = 0;
      canvas.addEventListener('pointerdown', function (e) {
        dragging = true; px = e.clientX; py = e.clientY;
        canvas.setPointerCapture && canvas.setPointerCapture(e.pointerId);
      });
      canvas.addEventListener('pointermove', function (e) {
        if (!dragging) return;
        cam.yaw += (e.clientX - px) * 0.005;
        cam.pitch += (e.clientY - py) * 0.005;
        cam.pitch = Math.max(-1.4, Math.min(1.4, cam.pitch));
        px = e.clientX; py = e.clientY;
      });
      window.addEventListener('pointerup', function () { dragging = false; });
      canvas.addEventListener('wheel', function (e) {
        e.preventDefault();
        cam.dist += e.deltaY * 0.01;
        cam.dist = Math.max(3, Math.min(20, cam.dist));
      }, { passive: false });

      if (hudRefs.playBtn) {
        hudRefs.playBtn.addEventListener('click', function () {
          playing = !playing;
          hudRefs.playBtn.textContent = playing ? 'Pause' : 'Play';
          hudRefs.playBtn.classList.toggle('active', playing);
        });
      }
      if (hudRefs.orbitBtn) {
        hudRefs.orbitBtn.addEventListener('click', function () {
          orbit = !orbit;
          hudRefs.orbitBtn.classList.toggle('active', orbit);
        });
      }
      if (hudRefs.resetBtn) {
        hudRefs.resetBtn.addEventListener('click', function () {
          cam.yaw = 0.55; cam.pitch = 0.34; cam.dist = 9.6;
          t = 0; speed = 1;
          if (hudRefs.spd) hudRefs.spd.value = '1.0';
          if (hudRefs.spdVal) hudRefs.spdVal.textContent = '1.0x';
        });
      }
      if (hudRefs.spd) {
        hudRefs.spd.addEventListener('input', function () {
          speed = parseFloat(hudRefs.spd.value) || 1;
          if (hudRefs.spdVal) hudRefs.spdVal.textContent = speed.toFixed(1) + 'x';
        });
      }
    }

    function start() {
      resize();
      initStars();
      initParts();
      bind();
      if (global.addEventListener) global.addEventListener('resize', resize);
      last = 0;
      raf = global.requestAnimationFrame ? global.requestAnimationFrame(frame) : 0;
    }

    return { start: start, resize: resize };
  }

  global.PortalEngine = PortalEngine;
})(typeof window !== 'undefined' ? window : this);
