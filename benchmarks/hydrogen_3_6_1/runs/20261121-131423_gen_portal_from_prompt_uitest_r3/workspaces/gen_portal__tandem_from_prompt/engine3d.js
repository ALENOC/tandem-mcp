/* engine3d.js - self-contained software 3D renderer (no dependencies) */
(function (global) {
  "use strict";

  function normalize(v) {
    var l = Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) || 1;
    return [v[0] / l, v[1] / l, v[2] / l];
  }
  function cross(a, b) {
    return [
      a[1] * b[2] - a[2] * b[1],
      a[2] * b[0] - a[0] * b[2],
      a[0] * b[1] - a[1] * b[0]
    ];
  }
  function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }

  // ---- Camera: orbit around a target point ----
  function makeCamera() {
    return {
      theta: 0.7,      // azimuth
      phi: 0.42,       // elevation
      radius: 30,
      fov: 55 * Math.PI / 180,
      target: [0, 3, 0]
    };
  }

  // Build camera basis (right, up, forward) from orbit params.
  function cameraBasis(cam) {
    var cp = Math.cos(cam.phi), sp = Math.sin(cam.phi);
    var ct = Math.cos(cam.theta), st = Math.sin(cam.theta);
    var pos = [
      cam.target[0] + cam.radius * cp * st,
      cam.target[1] + cam.radius * sp,
      cam.target[2] + cam.radius * cp * ct
    ];
    var fwd = normalize([
      cam.target[0] - pos[0],
      cam.target[1] - pos[1],
      cam.target[2] - pos[2]
    ]);
    var right = normalize(cross(fwd, [0, 1, 0]));
    var up = cross(right, fwd);
    return { pos: pos, fwd: fwd, right: right, up: up };
  }

  // Project a world point to screen. Returns null if behind camera.
  function project(p, basis, width, height, fov) {
    var dx = p[0] - basis.pos[0];
    var dy = p[1] - basis.pos[1];
    var dz = p[2] - basis.pos[2];
    var z = dx * basis.fwd[0] + dy * basis.fwd[1] + dz * basis.fwd[2];
    if (z <= 0.0001) return null;
    var focal = (height / 2) / Math.tan(fov / 2);
    var x = dx * basis.right[0] + dy * basis.right[1] + dz * basis.right[2];
    var y = dx * basis.up[0] + dy * basis.up[1] + dz * basis.up[2];
    var s = focal / z;
    return {
      x: width / 2 + x * s,
      y: height / 2 - y * s,
      z: z
    };
  }

  // ---- Geometry helpers ----
  function faceNormal(a, b, c) {
    var u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    var v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
    return normalize(cross(u, v));
  }

  // Lambert + ambient shading of a base color by a face normal.
  function shade(base, normal, lightDir) {
    var d = Math.max(0, dot(normal, lightDir));
    var l = 0.28 + 0.72 * d;
    return [
      Math.min(255, base[0] * l),
      Math.min(255, base[1] * l),
      Math.min(255, base[2] * l)
    ];
  }

  // Painter's algorithm: sort faces far -> near by average depth.
  function sortFaces(faces) {
    faces.sort(function (a, b) { return b.depth - a.depth; });
    return faces;
  }

  // Draw a filled polygon with neon glow.
  function drawPoly(ctx, pts, fill, stroke, glow, glowColor, lineWidth) {
    if (pts.length < 3) return;
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (var i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
    ctx.closePath();
    ctx.fillStyle = fill;
    ctx.fill();
    if (stroke) {
      ctx.save();
      ctx.shadowColor = glowColor || stroke;
      ctx.shadowBlur = glow || 0;
      ctx.strokeStyle = stroke;
      ctx.lineWidth = lineWidth || 1;
      ctx.stroke();
      ctx.restore();
    }
  }

  // Draw a glowing point (for stars / particles).
  function drawGlow(ctx, x, y, r, color, alpha) {
    ctx.save();
    ctx.globalAlpha = alpha == null ? 1 : alpha;
    ctx.shadowColor = color;
    ctx.shadowBlur = r * 3;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  global.Engine3D = {
    normalize: normalize,
    cross: cross,
    dot: dot,
    makeCamera: makeCamera,
    cameraBasis: cameraBasis,
    project: project,
    faceNormal: faceNormal,
    shade: shade,
    sortFaces: sortFaces,
    drawPoly: drawPoly,
    drawGlow: drawGlow
  };
})(window);
