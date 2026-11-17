(function () {
  var DEFAULTS = {
    yaw: 0.55,
    pitch: 0.34,
    dist: 9.6,
    fov: 580,
    target: [0, 0.35, 0]
  };

  var lightLen = Math.hypot(0.45, 0.8, -0.4);
  var LIGHT = [0.45 / lightLen, 0.8 / lightLen, -0.4 / lightLen];

  var canvas = null;
  var ctx = null;
  var scene = null;
  var W = 1080;
  var H = 690;
  var dpr = 1;

  var yaw = DEFAULTS.yaw;
  var pitch = DEFAULTS.pitch;
  var dist = DEFAULTS.dist;
  var fov = DEFAULTS.fov;
  var target = DEFAULTS.target.slice();

  var time = 0;
  var speed = 1.0;
  var paused = false;
  var orbit = true;

  var lastNow = null;
  var fps = 60;
  var lastPolys = 0;
  var lastParts = 0;

  var dragging = false;
  var dragX = 0;
  var dragY = 0;

  function resize() {
    if (!canvas) return;
    dpr = window.devicePixelRatio || 1;
    W = window.innerWidth || 1080;
    H = window.innerHeight || 690;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
  }

  function project(p) {
    var x = p[0] - target[0];
    var y = p[1] - target[1];
    var z = p[2] - target[2];

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
    return {
      x: W / 2 + x1 * s,
      y: H / 2 - y2 * s,
      depth: depth,
      s: s
    };
  }

  function faceNormal(pts) {
    var ax = pts[1][0] - pts[0][0];
    var ay = pts[1][1] - pts[0][1];
    var az = pts[1][2] - pts[0][2];
    var bx = pts[2][0] - pts[0][0];
    var by = pts[2][1] - pts[0][1];
    var bz = pts[2][2] - pts[0][2];
    var nx = ay * bz - az * by;
    var ny = az * bx - ax * bz;
    var nz = ax * by - ay * bx;
    var len = Math.hypot(nx, ny, nz) || 1;
    return [nx / len, ny / len, nz / len];
  }

  function drawStars() {
    var stars = scene.stars;
    for (var i = 0; i < stars.length; i++) {
      var st = stars[i];
      var pr = project(st.p);
      if (!pr) continue;
      var tw = 0.5 + 0.5 * Math.sin(time * st.rate + st.phase);
      var alpha = 0.25 + 0.75 * tw;
      ctx.fillStyle = 'rgba(200, 235, 255, ' + alpha.toFixed(3) + ')';
      var sz = st.size;
      ctx.fillRect(pr.x - sz * 0.5, pr.y - sz * 0.5, sz, sz);
    }
  }

  function drawGridSegment(p0, p1) {
    var steps = 6;
    var prev = null;
    ctx.beginPath();
    var started = false;
    for (var k = 0; k <= steps; k++) {
      var t = k / steps;
      var pt = [
        p0[0] + (p1[0] - p0[0]) * t,
        p0[1] + (p1[1] - p0[1]) * t,
        p0[2] + (p1[2] - p0[2]) * t
      ];
      var pr = project(pt);
      if (pr) {
        if (!started || !prev) {
          ctx.moveTo(pr.x, pr.y);
          started = true;
        } else {
          ctx.lineTo(pr.x, pr.y);
        }
        prev = pr;
      } else {
        prev = null;
      }
    }
    if (started) ctx.stroke();
  }

  function drawGrid() {
    ctx.lineWidth = 1;
    for (var i = -12; i <= 12; i++) {
      var major = (i % 4 === 0);
      ctx.strokeStyle = major ? 'rgba(0, 230, 255, 0.38)' : 'rgba(0, 165, 255, 0.13)';
      drawGridSegment([i, -2.0, -12], [i, -2.0, 12]);
      drawGridSegment([-12, -2.0, i], [12, -2.0, i]);
    }
  }

  function buildCrystalTriangles(crystal) {
    var a = crystal.angle + 0.35 * time;
    var cx = 2.45 * Math.cos(a);
    var cz = 2.45 * Math.sin(a);
    var cy = 0.5 + 0.28 * Math.sin(1.4 * time + crystal.phase);

    var ry = time * crystal.spin;
    var cr = Math.cos(ry), sr = Math.sin(ry);
    var hh = 0.42;
    var hw = 0.24;

    function rot(lx, ly, lz) {
      return [
        cx + lx * cr - lz * sr,
        cy + ly,
        cz + lx * sr + lz * cr
      ];
    }

    var top = rot(0, hh, 0);
    var bot = rot(0, -hh, 0);
    var eq = [
      rot(hw, 0, 0),
      rot(0, 0, hw),
      rot(-hw, 0, 0),
      rot(0, 0, -hw)
    ];

    var tris = [];
    for (var i = 0; i < 4; i++) {
      var next = (i + 1) % 4;
      tris.push({
        pts: [top, eq[next], eq[i]],
        color: crystal.color,
        glow: 0.25,
        isCrystal: true
      });
      tris.push({
        pts: [bot, eq[i], eq[next]],
        color: crystal.color,
        glow: 0.25,
        isCrystal: true
      });
    }
    return tris;
  }

  function drawRing(center, radius, segments, angleZ, tiltX, tiltY, color) {
    var cz = Math.cos(angleZ), sz = Math.sin(angleZ);
    var cx = Math.cos(tiltX), sx = Math.sin(tiltX);
    var cy = Math.cos(tiltY), sy = Math.sin(tiltY);

    ctx.beginPath();
    var started = false;
    for (var i = 0; i <= segments; i++) {
      var th = (i / segments) * Math.PI * 2;
      var lx = radius * Math.cos(th);
      var ly = radius * Math.sin(th);
      var lz = 0;

      // spin in ring plane
      var x1 = lx * cz - ly * sz;
      var y1 = lx * sz + ly * cz;
      var z1 = lz;

      // tilt around X
      var y2 = y1 * cx - z1 * sx;
      var z2 = y1 * sx + z1 * cx;
      var x2 = x1;

      // tilt around Y
      var x3 = x2 * cy - z2 * sy;
      var z3 = x2 * sy + z2 * cy;
      var y3 = y2;

      var pr = project([center[0] + x3, center[1] + y3, center[2] + z3]);
      if (pr) {
        if (!started) {
          ctx.moveTo(pr.x, pr.y);
          started = true;
        } else {
          ctx.lineTo(pr.x, pr.y);
        }
      } else {
        started = false;
      }
    }
    if (started) {
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();
    }
  }

  function drawPortal(centerProj) {
    var pulse = 1.0 + 0.08 * Math.sin(time * 2.4);
    var rPx = 1.05 * pulse * centerProj.s;

    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    var grad = ctx.createRadialGradient(
      centerProj.x, centerProj.y, 0,
      centerProj.x, centerProj.y, Math.max(1, rPx)
    );
    grad.addColorStop(0, 'rgba(255, 255, 255, 0.95)');
    grad.addColorStop(0.28, 'rgba(0, 235, 255, 0.75)');
    grad.addColorStop(0.65, 'rgba(255, 65, 215, 0.45)');
    grad.addColorStop(1, 'rgba(255, 65, 215, 0)');

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(centerProj.x, centerProj.y, Math.max(1, rPx), 0, Math.PI * 2);
    ctx.fill();

    var portalCenter = [0, 0.55, 0];
    drawRing(portalCenter, 1.0, 48, time * 1.1, 0.35, 0.25, 'rgba(0, 240, 255, 0.85)');
    drawRing(portalCenter, 0.78, 42, -time * 1.6, -0.45, 0.3, 'rgba(255, 80, 220, 0.85)');
    ctx.restore();
  }

  function drawParticles(simDt) {
    var parts = scene.particles;
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    for (var i = 0; i < parts.length; i++) {
      var pt = parts[i];
      if (simDt > 0) {
        pt.y += pt.v * simDt;
        if (pt.y > 3.6) {
          pt.y = -1.9;
        }
      }
      var wx = pt.x + 0.08 * Math.sin(time * 1.5 + pt.sway);
      var wz = pt.z + 0.08 * Math.cos(time * 1.3 + pt.sway);
      var pr = project([wx, pt.y, wz]);
      if (!pr) continue;

      var rPx = Math.max(1.0, pt.size * pr.s);
      ctx.fillStyle = 'hsla(' + pt.hue + ', 100%, 68%, 0.78)';
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, rPx, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
    lastParts = parts.length;
  }

  function frame(now) {
    requestAnimationFrame(frame);

    var dt = lastNow === null ? 0.016 : (now - lastNow) / 1000;
    lastNow = now;
    if (dt < 0) dt = 0;
    if (dt > 0.05) dt = 0.05;

    if (dt > 0) {
      var instFps = 1 / dt;
      fps = fps * 0.9 + instFps * 0.1;
    }

    var simDt = paused ? 0 : dt * speed;
    if (!paused) {
      time += simDt;
      if (orbit) {
        yaw += 0.22 * simDt;
      }
    }

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);

    drawStars();
    drawGrid();

    var drawList = [];

    // Collect 36 box faces
    var faces = scene.faces;
    for (var i = 0; i < faces.length; i++) {
      var f = faces[i];
      var projPts = [];
      var sumDepth = 0;
      var valid = true;
      for (var k = 0; k < f.pts.length; k++) {
        var pr = project(f.pts[k]);
        if (!pr) {
          valid = false;
          break;
        }
        projPts.push(pr);
        sumDepth += pr.depth;
      }
      if (!valid) continue;
      drawList.push({
        type: 'poly',
        pts: f.pts,
        proj: projPts,
        depth: sumDepth / projPts.length,
        color: f.color,
        glow: f.glow,
        isCrystal: false
      });
    }

    // Collect 48 crystal triangles (6 crystals * 8 triangles)
    var crystals = scene.crystals;
    for (var c = 0; c < crystals.length; c++) {
      var tris = buildCrystalTriangles(crystals[c]);
      for (var t = 0; t < tris.length; t++) {
        var tri = tris[t];
        var tProj = [];
        var tSum = 0;
        var tValid = true;
        for (var v = 0; v < 3; v++) {
          var tpr = project(tri.pts[v]);
          if (!tpr) {
            tValid = false;
            break;
          }
          tProj.push(tpr);
          tSum += tpr.depth;
        }
        if (!tValid) continue;
        drawList.push({
          type: 'poly',
          pts: tri.pts,
          proj: tProj,
          depth: tSum / 3,
          color: tri.color,
          glow: tri.glow,
          isCrystal: true
        });
      }
    }

    // Collect portal in same depth order
    var portalProj = project([0, 0.55, 0]);
    if (portalProj) {
      drawList.push({
        type: 'portal',
        proj: portalProj,
        depth: portalProj.depth
      });
    }

    // Painter's algorithm: far to near (descending depth)
    drawList.sort(function (a, b) {
      return b.depth - a.depth;
    });

    var polyCount = 0;
    for (var d = 0; d < drawList.length; d++) {
      var item = drawList[d];
      if (item.type === 'portal') {
        drawPortal(item.proj);
        continue;
      }

      var n = faceNormal(item.pts);
      var dot = n[0] * LIGHT[0] + n[1] * LIGHT[1] + n[2] * LIGHT[2];
      var brightness = 0.42 + 0.95 * Math.max(0, dot) + item.glow;

      var r = Math.min(255, Math.max(0, Math.round(item.color[0] * brightness)));
      var g = Math.min(255, Math.max(0, Math.round(item.color[1] * brightness)));
      var b = Math.min(255, Math.max(0, Math.round(item.color[2] * brightness)));

      ctx.beginPath();
      ctx.moveTo(item.proj[0].x, item.proj[0].y);
      for (var p = 1; p < item.proj.length; p++) {
        ctx.lineTo(item.proj[p].x, item.proj[p].y);
      }
      ctx.closePath();
      ctx.fillStyle = 'rgb(' + r + ', ' + g + ', ' + b + ')';
      ctx.fill();

      ctx.lineWidth = item.isCrystal ? 1 : 0.9;
      ctx.strokeStyle = item.isCrystal ? 'rgba(255, 255, 255, 0.78)' : 'rgba(0, 225, 255, 0.45)';
      ctx.stroke();

      polyCount++;
    }
    lastPolys = polyCount;

    drawParticles(simDt);
  }

  function init(c) {
    canvas = c;
    ctx = canvas.getContext('2d');
    scene = window.Scene.build();
    resize();

    window.addEventListener('resize', resize);

    canvas.addEventListener('pointerdown', function (e) {
      dragging = true;
      dragX = e.clientX;
      dragY = e.clientY;
      if (canvas.setPointerCapture && e.pointerId !== undefined) {
        try { canvas.setPointerCapture(e.pointerId); } catch (_) {}
      }
    });

    canvas.addEventListener('pointermove', function (e) {
      if (!dragging) return;
      var dx = e.clientX - dragX;
      var dy = e.clientY - dragY;
      dragX = e.clientX;
      dragY = e.clientY;
      yaw += dx * 0.008;
      pitch = Math.max(-1.1, Math.min(1.3, pitch + dy * 0.008));
    });

    function endDrag() {
      dragging = false;
    }
    canvas.addEventListener('pointerup', endDrag);
    canvas.addEventListener('pointercancel', endDrag);

    requestAnimationFrame(frame);
  }

  function setSpeed(v) {
    if (typeof v === 'number' && !isNaN(v)) {
      speed = v;
    }
  }

  function togglePause() {
    paused = !paused;
    return paused;
  }

  function toggleOrbit() {
    orbit = !orbit;
    return orbit;
  }

  function reset() {
    yaw = DEFAULTS.yaw;
    pitch = DEFAULTS.pitch;
    dist = DEFAULTS.dist;
    fov = DEFAULTS.fov;
    target = DEFAULTS.target.slice();
    time = 0;
  }

  function getStats() {
    return {
      fps: fps,
      polys: lastPolys,
      parts: lastParts
    };
  }

  window.Engine3D = {
    init: init,
    setSpeed: setSpeed,
    togglePause: togglePause,
    toggleOrbit: toggleOrbit,
    reset: reset,
    getStats: getStats
  };
})();
