(function () {
  const DEFAULTS = {
    yaw: 0.55,
    pitch: 0.34,
    dist: 9.6,
    fov: 580,
    target: [0, 0.35, 0]
  };

  const lightLen = Math.hypot(0.45, 0.8, -0.4);
  const LIGHT = [0.45 / lightLen, 0.8 / lightLen, -0.4 / lightLen];

  let canvas = null;
  let ctx = null;
  let scene = null;
  let W = 0;
  let H = 0;
  let dpr = 1;

  let yaw = DEFAULTS.yaw;
  let pitch = DEFAULTS.pitch;
  let dist = DEFAULTS.dist;
  let fov = DEFAULTS.fov;
  let target = DEFAULTS.target.slice();

  let time = 0;
  let speed = 1.0;
  let paused = false;
  let orbit = true;

  let lastNow = 0;
  let fps = 60;
  let lastPolys = 0;
  let lastParts = 0;

  let dragging = false;
  let dragX = 0;
  let dragY = 0;

  function resize() {
    if (!canvas) return;
    W = window.innerWidth;
    H = window.innerHeight;
    dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';
  }

  function project(pt) {
    const x = pt[0] - target[0];
    const y = pt[1] - target[1];
    const z = pt[2] - target[2];

    const cosY = Math.cos(yaw);
    const sinY = Math.sin(yaw);
    const x1 = x * cosY - z * sinY;
    const z1 = x * sinY + z * cosY;

    const cosP = Math.cos(pitch);
    const sinP = Math.sin(pitch);
    const y2 = y * cosP + z1 * sinP;
    const z2 = -y * sinP + z1 * cosP;

    const depth = z2 + dist;
    if (depth < 0.2) return null;

    const view = Math.min(W / 1180, H / 720);
    const s = (fov * view) / depth;

    return {
      x: W / 2 + x1 * s,
      y: H / 2 - y2 * s,
      depth: depth,
      s: s
    };
  }

  function faceNormal(p0, p1, p2) {
    const ax = p1[0] - p0[0], ay = p1[1] - p0[1], az = p1[2] - p0[2];
    const bx = p2[0] - p0[0], by = p2[1] - p0[1], bz = p2[2] - p0[2];
    const nx = ay * bz - az * by;
    const ny = az * bx - ax * bz;
    const nz = ax * by - ay * bx;
    const len = Math.hypot(nx, ny, nz) || 1;
    return [nx / len, ny / len, nz / len];
  }

  function drawGrid() {
    const segs = 8;
    for (let i = -12; i <= 12; i++) {
      const major = i % 4 === 0;
      ctx.strokeStyle = major ? 'rgba(40, 235, 255, 0.36)' : 'rgba(20, 140, 200, 0.14)';
      ctx.lineWidth = major ? 1.2 : 0.8;

      // Line along Z
      ctx.beginPath();
      let started = false;
      for (let s = 0; s <= segs; s++) {
        const z = -12 + (24 * s) / segs;
        const p = project([i, -2.0, z]);
        if (!p) { started = false; continue; }
        if (!started) { ctx.moveTo(p.x, p.y); started = true; }
        else ctx.lineTo(p.x, p.y);
      }
      ctx.stroke();

      // Line along X
      ctx.beginPath();
      started = false;
      for (let s = 0; s <= segs; s++) {
        const x = -12 + (24 * s) / segs;
        const p = project([x, -2.0, i]);
        if (!p) { started = false; continue; }
        if (!started) { ctx.moveTo(p.x, p.y); started = true; }
        else ctx.lineTo(p.x, p.y);
      }
      ctx.stroke();
    }
  }

  function drawRing(radius, tiltX, tiltZ, spinAngle, color) {
    const steps = 48;
    const cy = 0.55;
    const cosX = Math.cos(tiltX), sinX = Math.sin(tiltX);
    const cosZ = Math.cos(tiltZ), sinZ = Math.sin(tiltZ);

    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    let started = false;

    for (let i = 0; i <= steps; i++) {
      const a = spinAngle + (i / steps) * Math.PI * 2;
      const lx = radius * Math.cos(a);
      const ly = radius * Math.sin(a);
      const lz = 0;

      // Tilt around X then Z
      const y1 = ly * cosX - lz * sinX;
      const z1 = ly * sinX + lz * cosX;
      const x2 = lx * cosZ - y1 * sinZ;
      const y2 = lx * sinZ + y1 * cosZ;

      const p = project([x2, cy + y2, z1]);
      if (!p) { started = false; continue; }
      if (!started) { ctx.moveTo(p.x, p.y); started = true; }
      else ctx.lineTo(p.x, p.y);
    }
    ctx.stroke();
  }

  function drawPortal(centerProj) {
    const pulse = 1 + 0.08 * Math.sin(time * 2.5);
    const rPx = Math.max(4, 1.05 * pulse * centerProj.s);

    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    const grad = ctx.createRadialGradient(centerProj.x, centerProj.y, 0, centerProj.x, centerProj.y, rPx);
    grad.addColorStop(0, 'rgba(255, 255, 255, 0.95)');
    grad.addColorStop(0.32, 'rgba(40, 230, 255, 0.72)');
    grad.addColorStop(0.68, 'rgba(255, 70, 215, 0.42)');
    grad.addColorStop(1, 'rgba(255, 70, 215, 0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(centerProj.x, centerProj.y, rPx, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    drawRing(1.0, 0.35, 0.25, time * 1.15, 'rgba(60, 235, 255, 0.9)');
    drawRing(0.78, -0.45, -0.3, -time * 1.55, 'rgba(255, 80, 220, 0.9)');
  }

  function render() {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);

    // 1. Stars
    for (let i = 0; i < scene.stars.length; i++) {
      const st = scene.stars[i];
      const p = project(st.p);
      if (!p) continue;
      const alpha = 0.25 + 0.75 * (0.5 + 0.5 * Math.sin(time * st.rate + st.phase));
      ctx.fillStyle = 'rgba(210, 235, 255, ' + alpha.toFixed(3) + ')';
      ctx.fillRect(p.x - st.size * 0.5, p.y - st.size * 0.5, st.size, st.size);
    }

    // 2. Cyber grid floor
    drawGrid();

    // 3. Collect depth-sorted geometry (faces + crystal triangles + portal)
    const drawList = [];

    for (let i = 0; i < scene.faces.length; i++) {
      const f = scene.faces[i];
      const pts = f.pts;
      const proj = [];
      let sumD = 0;
      let valid = true;
      for (let k = 0; k < 4; k++) {
        const pr = project(pts[k]);
        if (!pr) { valid = false; break; }
        proj.push(pr);
        sumD += pr.depth;
      }
      if (!valid) continue;

      const n = faceNormal(pts[0], pts[1], pts[2]);
      const dot = Math.max(0, n[0] * LIGHT[0] + n[1] * LIGHT[1] + n[2] * LIGHT[2]);
      const brightness = 0.42 + 0.95 * dot + f.glow;

      drawList.push({
        type: 'poly',
        depth: sumD / 4,
        pts: proj,
        color: f.color,
        brightness: brightness,
        stroke: 'rgba(60, 220, 255, 0.45)',
        lineWidth: 1
      });
    }

    const hh = 0.42;
    const hw = 0.24;
    for (let i = 0; i < scene.crystals.length; i++) {
      const c = scene.crystals[i];
      const a = c.angle + 0.35 * time;
      const cx = 2.45 * Math.cos(a);
      const cz = 2.45 * Math.sin(a);
      const cy = 0.5 + 0.28 * Math.sin(1.4 * time + c.phase);
      const rot = time * c.spin;

      const top = [cx, cy + hh, cz];
      const bot = [cx, cy - hh, cz];
      const eq = [];
      for (let k = 0; k < 4; k++) {
        const ang = rot + (k * Math.PI) / 2;
        eq.push([cx + hw * Math.cos(ang), cy, cz + hw * Math.sin(ang)]);
      }

      for (let k = 0; k < 4; k++) {
        const next = (k + 1) % 4;
        const tris = [
          [top, eq[next], eq[k]],
          [bot, eq[k], eq[next]]
        ];
        for (let t = 0; t < 2; t++) {
          const tri = tris[t];
          const p0 = project(tri[0]);
          const p1 = project(tri[1]);
          const p2 = project(tri[2]);
          if (!p0 || !p1 || !p2) continue;

          const n = faceNormal(tri[0], tri[1], tri[2]);
          const dot = Math.max(0, n[0] * LIGHT[0] + n[1] * LIGHT[1] + n[2] * LIGHT[2]);
          const brightness = 0.42 + 0.95 * dot + 0.25;

          drawList.push({
            type: 'poly',
            depth: (p0.depth + p1.depth + p2.depth) / 3,
            pts: [p0, p1, p2],
            color: c.color,
            brightness: brightness,
            stroke: 'rgba(255, 255, 255, 0.65)',
            lineWidth: 0.9
          });
        }
      }
    }

    const portalProj = project([0, 0.55, 0]);
    if (portalProj) {
      drawList.push({
        type: 'portal',
        depth: portalProj.depth,
        center: portalProj
      });
    }

    drawList.sort((a, b) => b.depth - a.depth);

    let polyCount = 0;
    for (let i = 0; i < drawList.length; i++) {
      const item = drawList[i];
      if (item.type === 'portal') {
        drawPortal(item.center);
      } else {
        const r = Math.min(255, Math.max(0, Math.round(item.color[0] * item.brightness)));
        const g = Math.min(255, Math.max(0, Math.round(item.color[1] * item.brightness)));
        const b = Math.min(255, Math.max(0, Math.round(item.color[2] * item.brightness)));

        ctx.fillStyle = 'rgb(' + r + ',' + g + ',' + b + ')';
        ctx.strokeStyle = item.stroke;
        ctx.lineWidth = item.lineWidth;

        ctx.beginPath();
        ctx.moveTo(item.pts[0].x, item.pts[0].y);
        for (let k = 1; k < item.pts.length; k++) {
          ctx.lineTo(item.pts[k].x, item.pts[k].y);
        }
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        polyCount++;
      }
    }

    // 4. Particles drawn last as additive dots
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';
    for (let i = 0; i < scene.particles.length; i++) {
      const pt = scene.particles[i];
      const px = pt.x + Math.sin(time * 1.4 + pt.sway) * 0.12;
      const pz = pt.z + Math.cos(time * 1.1 + pt.sway) * 0.12;
      const pr = project([px, pt.y, pz]);
      if (!pr) continue;

      const alpha = 0.45 + 0.4 * Math.sin(time * 2.2 + pt.sway);
      const rPx = Math.max(1.2, pt.size * pr.s);
      ctx.fillStyle = 'hsla(' + pt.hue + ', 100%, 68%, ' + alpha.toFixed(3) + ')';
      ctx.beginPath();
      ctx.arc(pr.x, pr.y, rPx, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();

    lastPolys = polyCount;
    lastParts = scene.particles.length;
  }

  function loop(now) {
    const rawDt = lastNow ? (now - lastNow) / 1000 : 0.016;
    lastNow = now;
    if (rawDt > 0) {
      fps = fps * 0.9 + (1 / rawDt) * 0.1;
    }

    const dt = Math.min(0.05, Math.max(0, rawDt));

    if (!paused) {
      time += dt * speed;
      if (orbit) {
        yaw += 0.22 * dt * speed;
      }
      for (let i = 0; i < scene.particles.length; i++) {
        const pt = scene.particles[i];
        pt.y += pt.v * dt * speed;
        if (pt.y > 3.6) pt.y = -1.9;
      }
    }

    render();
    window.requestAnimationFrame(loop);
  }

  function init(c) {
    canvas = c;
    ctx = canvas.getContext('2d');
    resize();
    window.addEventListener('resize', resize);

    canvas.addEventListener('pointerdown', function (e) {
      dragging = true;
      dragX = e.clientX;
      dragY = e.clientY;
      if (canvas.setPointerCapture) canvas.setPointerCapture(e.pointerId);
    });

    canvas.addEventListener('pointermove', function (e) {
      if (!dragging) return;
      const dx = e.clientX - dragX;
      const dy = e.clientY - dragY;
      dragX = e.clientX;
      dragY = e.clientY;
      yaw += dx * 0.008;
      pitch = Math.max(-1.4, Math.min(1.4, pitch + dy * 0.008));
    });

    const endDrag = function () { dragging = false; };
    canvas.addEventListener('pointerup', endDrag);
    canvas.addEventListener('pointercancel', endDrag);

    scene = window.Scene.build();
    lastNow = 0;
    window.requestAnimationFrame(loop);
  }

  function setSpeed(s) {
    speed = s;
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
