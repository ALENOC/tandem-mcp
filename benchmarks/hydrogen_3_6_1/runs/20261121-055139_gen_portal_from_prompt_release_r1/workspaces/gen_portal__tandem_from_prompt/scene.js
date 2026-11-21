// scene.js - scene content: platform, pillars, portal core, rings,
// crystals, grid floor, stars, particles. Exposes a Scene object.

(function (global) {
  "use strict";
  var E = global.Engine;

  function Scene() {
    this.t = 0;
    this.build();
  }

  Scene.prototype.build = function () {
    // ---- 6 boxes = 36 faces: two-tier platform, twin pillars, lintel, crown cap ----
    var boxes = [];
    // Tier 1 (lower, wide)
    boxes.push({ faces: E.makeBox(3.2, 0.35, 3.2), pos: E.v3(0, 0.35, 0),
      color: "#123047", stroke: "#2fd6ff", glow: "#2fd6ff" });
    // Tier 2 (upper, smaller)
    boxes.push({ faces: E.makeBox(2.2, 0.3, 2.2), pos: E.v3(0, 0.95, 0),
      color: "#16324f", stroke: "#4fe3ff", glow: "#4fe3ff" });
    // Twin pillars
    boxes.push({ faces: E.makeBox(0.35, 2.2, 0.35), pos: E.v3(-2.0, 2.6, 0),
      color: "#1a2f52", stroke: "#7d7dff", glow: "#8f7dff" });
    boxes.push({ faces: E.makeBox(0.35, 2.2, 0.35), pos: E.v3(2.0, 2.6, 0),
      color: "#1a2f52", stroke: "#7d7dff", glow: "#8f7dff" });
    // Lintel (horizontal beam)
    boxes.push({ faces: E.makeBox(2.6, 0.35, 0.5), pos: E.v3(0, 4.0, 0),
      color: "#20264f", stroke: "#b06bff", glow: "#b06bff" });
    // Crown cap (top of lintel)
    boxes.push({ faces: E.makeBox(2.9, 0.22, 0.7), pos: E.v3(0, 4.42, 0),
      color: "#2a2350", stroke: "#ff5fd0", glow: "#ff5fd0" });
    this.boxes = boxes;

    // ---- Six orbiting octahedral crystals (6 x 8 = 48 triangles) ----
    this.crystals = [];
    for (var i = 0; i < 6; i++) {
      this.crystals.push({
        faces: E.makeOctahedron(0.42),
        phase: (i / 6) * Math.PI * 2,
        radius: 3.4,
        height: 2.6 + Math.sin(i * 1.7) * 0.5,
        spin: 0.8 + i * 0.12
      });
    }

    // ---- Two counter-rotating rings around the portal core ----
    this.ringSegs = 18;
    this.ringRadius = 1.5;
    this.ringThick = 0.16;
    this.ringY = 2.6;

    // ---- 180 twinkling stars ----
    this.stars = [];
    for (var s = 0; s < 180; s++) {
      this.stars.push({
        x: Math.random(),
        y: Math.random(),
        r: 0.4 + Math.random() * 1.4,
        tw: Math.random() * Math.PI * 2,
        sp: 0.6 + Math.random() * 2.2
      });
    }

    // ---- 110 rising neon particles ----
    this.parts = [];
    var hues = [185, 200, 265, 300, 320];
    for (var p = 0; p < 110; p++) {
      this.parts.push({
        x: (Math.random() - 0.5) * 10,
        y: Math.random() * 8,
        z: (Math.random() - 0.5) * 10,
        vy: 0.4 + Math.random() * 0.9,
        h: hues[p % hues.length],
        ph: Math.random() * Math.PI * 2
      });
    }
  };

  Scene.prototype.reset = function () {
    this.t = 0;
    for (var p = 0; p < this.parts.length; p++) {
      this.parts[p].y = Math.random() * 8;
    }
  };

  Scene.prototype.update = function (dt) {
    this.t += dt;
    for (var p = 0; p < this.parts.length; p++) {
      var pt = this.parts[p];
      pt.y += pt.vy * dt;
      if (pt.y > 8.5) {
        pt.y = -0.5;
        pt.x = (Math.random() - 0.5) * 10;
        pt.z = (Math.random() - 0.5) * 10;
      }
    }
  };

  // Draw the cyber perspective grid floor in 3D.
  Scene.prototype.drawGrid = function (ren, cam, basis) {
    var ctx = ren.ctx;
    var cx = ren.w / 2, cy = ren.h / 2, sc = ren.h * 0.5;
    var ext = 14, step = 1;
    var y = -0.02;
    ctx.lineWidth = 1;
    var i, a, b, pa, pb;
    // Lines along X
    for (var z = -ext; z <= ext; z += step) {
      a = E.toCamera(cam, basis, E.v3(-ext, y, z));
      b = E.toCamera(cam, basis, E.v3(ext, y, z));
      pa = E.project(cam, a); pb = E.project(cam, b);
      if (!pa || !pb) continue;
      var fade = 1 - Math.abs(z) / (ext * 1.4);
      ctx.strokeStyle = "rgba(60,220,255," + (0.05 + fade * 0.28).toFixed(3) + ")";
      ctx.beginPath();
      ctx.moveTo(cx + pa.x * sc, cy - pa.y * sc);
      ctx.lineTo(cx + pb.x * sc, cy - pb.y * sc);
      ctx.stroke();
    }
    // Lines along Z
    for (i = -ext; i <= ext; i += step) {
      a = E.toCamera(cam, basis, E.v3(i, y, -ext));
      b = E.toCamera(cam, basis, E.v3(i, y, ext));
      pa = E.project(cam, a); pb = E.project(cam, b);
      if (!pa || !pb) continue;
      var fade2 = 1 - Math.abs(i) / (ext * 1.4);
      ctx.strokeStyle = "rgba(150,120,255," + (0.05 + fade2 * 0.28).toFixed(3) + ")";
      ctx.beginPath();
      ctx.moveTo(cx + pa.x * sc, cy - pa.y * sc);
      ctx.lineTo(cx + pb.x * sc, cy - pb.y * sc);
      ctx.stroke();
    }
  };

  Scene.prototype.drawStars = function (ren) {
    var ctx = ren.ctx;
    for (var i = 0; i < this.stars.length; i++) {
      var st = this.stars[i];
      var a = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(this.t * st.sp + st.tw));
      ctx.globalAlpha = a;
      ctx.fillStyle = "#dff6ff";
      ctx.beginPath();
      ctx.arc(st.x * ren.w, st.y * ren.h * 0.9, st.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  };

  Scene.prototype.drawParticles = function (ren, cam, basis) {
    var ctx = ren.ctx;
    var cx = ren.w / 2, cy = ren.h / 2, sc = ren.h * 0.5;
    for (var i = 0; i < this.parts.length; i++) {
      var pt = this.parts[i];
      var cp = E.toCamera(cam, basis, E.v3(pt.x, pt.y, pt.z));
      var pr = E.project(cam, cp);
      if (!pr) continue;
      var sx = cx + pr.x * sc, sy = cy - pr.y * sc;
      var size = Math.max(1.2, 6 / pr.z * 2);
      var tw = 0.5 + 0.5 * Math.sin(this.t * 3 + pt.ph);
      ctx.globalAlpha = 0.35 + tw * 0.6;
      ctx.fillStyle = "hsl(" + pt.h + ",100%,70%)";
      ctx.shadowColor = "hsl(" + pt.h + ",100%,65%)";
      ctx.shadowBlur = 8;
      ctx.beginPath();
      ctx.arc(sx, sy, size, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.shadowBlur = 0;
    ctx.globalAlpha = 1;
  };

  // Portal core: glowing neon energy disc + two counter-rotating rings.
  Scene.prototype.drawPortal = function (ren, cam, basis) {
    var ctx = ren.ctx;
    var cx = ren.w / 2, cy = ren.h / 2, sc = ren.h * 0.5;
    var core = E.toCamera(cam, basis, E.v3(0, this.ringY, 0));
    var pr = E.project(cam, core);
    if (!pr) return 0;
    var sx = cx + pr.x * sc, sy = cy - pr.y * sc;
    var baseR = (this.ringRadius * sc) / pr.z;
    var pulse = 0.85 + 0.15 * Math.sin(this.t * 2.2);

    // Energy glow disc
    var g = ctx.createRadialGradient(sx, sy, 0, sx, sy, baseR * 1.15);
    g.addColorStop(0, "rgba(255,255,255," + (0.95 * pulse).toFixed(3) + ")");
    g.addColorStop(0.35, "rgba(120,240,255," + (0.7 * pulse).toFixed(3) + ")");
    g.addColorStop(0.7, "rgba(150,110,255," + (0.35 * pulse).toFixed(3) + ")");
    g.addColorStop(1, "rgba(120,80,255,0)");
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(sx, sy, baseR * 1.15, 0, Math.PI * 2);
    ctx.fill();

    // Two counter-rotating rings (drawn as projected ellipses, tilted)
    var tilt = 0.5;
    var spinA = this.t * 0.9;
    var spinB = -this.t * 1.3;
    this.drawRing(ctx, sx, sy, baseR, tilt, spinA, "rgba(120,255,255,0.9)", 2.5);
    this.drawRing(ctx, sx, sy, baseR * 1.28, -tilt * 0.7, spinB, "rgba(255,120,230,0.85)", 2);
    return 0;
  };

  Scene.prototype.drawRing = function (ctx, sx, sy, R, tilt, spin, color, lw) {
    ctx.save();
    ctx.translate(sx, sy);
    ctx.rotate(tilt);
    ctx.strokeStyle = color;
    ctx.lineWidth = lw;
    ctx.shadowColor = color;
    ctx.shadowBlur = 14;
    ctx.beginPath();
    // Dashed rotating ring: draw arc segments offset by spin
    var segs = 24;
    for (var i = 0; i < segs; i++) {
      var a0 = spin + (i / segs) * Math.PI * 2;
      var a1 = spin + ((i + 0.6) / segs) * Math.PI * 2;
      ctx.moveTo(Math.cos(a0) * R, Math.sin(a0) * R * 0.35);
      ctx.lineTo(Math.cos(a1) * R, Math.sin(a1) * R * 0.35);
    }
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.restore();
  };

  // Main render. Returns number of filled polygons drawn.
  Scene.prototype.render = function (ren, cam, basis) {
    var polys = 0;
    // Stars (screen space)
    this.drawStars(ren);
    // Grid floor
    this.drawGrid(ren, cam, basis);
    // Structure boxes (36 faces)
    var I = E.mulMat(E.rotY(0), E.rotX(0));
    for (var i = 0; i < this.boxes.length; i++) {
      var bx = this.boxes[i];
      polys += ren.drawFaces(cam, basis, bx.faces, I, bx.pos);
    }
    // Crystals (48 triangles)
    for (var c = 0; c < this.crystals.length; c++) {
      var cr = this.crystals[c];
      var ang = this.t * 0.5 + cr.phase;
      var pos = E.v3(
        Math.cos(ang) * cr.radius,
        cr.height + Math.sin(this.t * 1.3 + cr.phase) * 0.25,
        Math.sin(ang) * cr.radius
      );
      var m = E.rotY(this.t * cr.spin);
      var faces = cr.faces;
      // color each triangle
      var col = "hsl(" + (190 + c * 20) + ",100%,65%)";
      var colArr = [];
      for (var f = 0; f < faces.length; f++) {
        colArr.push({ verts: faces[f], n: E.norm(E.cross(
          E.sub(faces[f][1], faces[f][0]), E.sub(faces[f][2], faces[f][0]))),
          color: col, stroke: "rgba(255,255,255,0.5)", glow: col });
      }
      polys += ren.drawFaces(cam, basis, colArr, m, pos);
    }
    // Portal core + rings
    polys += this.drawPortal(ren, cam, basis);
    // Particles
    this.drawParticles(ren, cam, basis);
    return polys;
  };

  global.Scene = Scene;
})(typeof window !== "undefined" ? window : this);
