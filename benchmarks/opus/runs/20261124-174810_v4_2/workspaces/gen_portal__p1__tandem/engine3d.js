// engine3d.js - a tiny software 3D renderer on the 2D canvas context.
// No WebGL, no external libraries.

(function (global) {
  "use strict";

  // ---- vec3 math -----------------------------------------------------------
  function vec3(x, y, z) { return { x: x || 0, y: y || 0, z: z || 0 }; }
  function v3add(a, b) { return vec3(a.x + b.x, a.y + b.y, a.z + b.z); }
  function v3sub(a, b) { return vec3(a.x - b.x, a.y - b.y, a.z - b.z); }
  function v3scale(a, s) { return vec3(a.x * s, a.y * s, a.z * s); }
  function v3dot(a, b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
  function v3cross(a, b) {
    return vec3(
      a.y * b.z - a.z * b.y,
      a.z * b.x - a.x * b.z,
      a.x * b.y - a.y * b.x
    );
  }
  function v3len(a) { return Math.sqrt(v3dot(a, a)); }
  function v3norm(a) {
    var l = v3len(a) || 1;
    return vec3(a.x / l, a.y / l, a.z / l);
  }

  // ---- rotation ------------------------------------------------------------
  // Rotation about the Y axis by angle (radians).
  function rotY(p, ang) {
    var c = Math.cos(ang), s = Math.sin(ang);
    return vec3(p.x * c + p.z * s, p.y, -p.x * s + p.z * c);
  }
  // Rotation about the X axis by angle (radians).
  function rotX(p, ang) {
    var c = Math.cos(ang), s = Math.sin(ang);
    return vec3(p.x, p.y * c - p.z * s, p.y * s + p.z * c);
  }
  // Rotation about the Z axis by angle (radians).
  function rotZ(p, ang) {
    var c = Math.cos(ang), s = Math.sin(ang);
    return vec3(p.x * c - p.y * s, p.x * s + p.y * c, p.z);
  }

  // ---- camera --------------------------------------------------------------
  // lookAt builds a view transform (world -> camera space).
  function makeCamera(eye, target, up) {
    var f = v3norm(v3sub(target, eye));       // forward
    var r = v3norm(v3cross(f, up));           // right
    var u = v3cross(r, f);                    // true up
    return {
      eye: eye,
      forward: f,
      right: r,
      up: u,
      // Transform a world point into camera space.
      toCamera: function (p) {
        var d = v3sub(p, eye);
        return vec3(v3dot(d, r), v3dot(d, u), v3dot(d, f));
      }
    };
  }

  // ---- perspective projection ----------------------------------------------
  // Project a camera-space point (z = depth in front of camera) to screen.
  function project(p, cam, width, height, fov) {
    var f = (height / 2) / Math.tan(fov / 2);
    var z = p.z;
    if (z < 0.05) z = 0.05;
    return {
      x: width / 2 + (p.x * f) / z,
      y: height / 2 - (p.y * f) / z,
      z: z
    };
  }

  // ---- shading -------------------------------------------------------------
  // Lambert factor against a light direction (both normalized).
  function lambert(normal, light) {
    var d = v3dot(normal, light);
    return d > 0 ? d : 0;
  }

  // ---- color helpers -------------------------------------------------------
  function hexToRgb(hex) {
    var h = hex.replace("#", "");
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
  }
  function shade(hex, factor) {
    var c = hexToRgb(hex);
    var r = Math.min(255, Math.round(c.r * factor));
    var g = Math.min(255, Math.round(c.g * factor));
    var b = Math.min(255, Math.round(c.b * factor));
    return "rgb(" + r + "," + g + "," + b + ")";
  }

  // ---- polygon fill with painter's algorithm -------------------------------
  // polys: array of { pts: [ {x,y}... ], fill, stroke, glow, glowColor }
  // Each poly must carry a precomputed depth (z) for sorting.
  function drawPolys(ctx, polys) {
    // Painter's algorithm: far to near.
    polys.sort(function (a, b) { return b.z - a.z; });
    for (var i = 0; i < polys.length; i++) {
      var p = polys[i];
      if (p.pts.length < 3) continue;
      ctx.beginPath();
      ctx.moveTo(p.pts[0].x, p.pts[0].y);
      for (var j = 1; j < p.pts.length; j++) ctx.lineTo(p.pts[j].x, p.pts[j].y);
      ctx.closePath();
      if (p.fill) {
        ctx.fillStyle = p.fill;
        ctx.fill();
      }
      if (p.stroke) {
        ctx.save();
        if (p.glow) {
          ctx.shadowBlur = p.glow;
          ctx.shadowColor = p.glowColor || p.stroke;
        }
        ctx.strokeStyle = p.stroke;
        ctx.lineWidth = p.lw || 1.5;
        ctx.lineJoin = "round";
        ctx.stroke();
        ctx.restore();
      }
    }
  }

  // ---- box geometry --------------------------------------------------------
  // Build the 6 faces of an axis-aligned box. Returns array of faces,
  // each face = { verts: [4 world vec3], normal: vec3 }.
  function boxFaces(cx, cy, cz, sx, sy, sz) {
    var hx = sx / 2, hy = sy / 2, hz = sz / 2;
    var x0 = cx - hx, x1 = cx + hx;
    var y0 = cy - hy, y1 = cy + hy;
    var z0 = cz - hz, z1 = cz + hz;
    // Each face: 4 corners ordered CCW when viewed from outside.
    return [
      { n: vec3(0, 0, 1),  v: [vec3(x0, y0, z1), vec3(x1, y0, z1), vec3(x1, y1, z1), vec3(x0, y1, z1)] }, // +z
      { n: vec3(0, 0, -1), v: [vec3(x1, y0, z0), vec3(x0, y0, z0), vec3(x0, y1, z0), vec3(x1, y1, z0)] }, // -z
      { n: vec3(1, 0, 0),  v: [vec3(x1, y0, z1), vec3(x1, y0, z0), vec3(x1, y1, z0), vec3(x1, y1, z1)] }, // +x
      { n: vec3(-1, 0, 0), v: [vec3(x0, y0, z0), vec3(x0, y0, z1), vec3(x0, y1, z1), vec3(x0, y1, z0)] }, // -x
      { n: vec3(0, 1, 0),  v: [vec3(x0, y1, z1), vec3(x1, y1, z1), vec3(x1, y1, z0), vec3(x0, y1, z0)] }, // +y
      { n: vec3(0, -1, 0), v: [vec3(x0, y0, z0), vec3(x1, y0, z0), vec3(x1, y0, z1), vec3(x0, y0, z1)] }  // -y
    ];
  }

  // ---- octahedron geometry -------------------------------------------------
  // 8 triangular faces of a regular octahedron centered at origin, radius r.
  function octaFaces(r) {
    var t = vec3(0, r, 0), b = vec3(0, -r, 0);
    var e = vec3(r, 0, 0), w = vec3(-r, 0, 0);
    var n = vec3(0, 0, r), s = vec3(0, 0, -r);
    // 8 faces, each a triangle.
    return [
      [t, e, n], [t, n, w], [t, w, s], [t, s, e],
      [b, n, e], [b, w, n], [b, s, w], [b, e, s]
    ];
  }

  global.Engine3D = {
    vec3: vec3,
    v3add: v3add,
    v3sub: v3sub,
    v3scale: v3scale,
    v3dot: v3dot,
    v3cross: v3cross,
    v3len: v3len,
    v3norm: v3norm,
    rotX: rotX,
    rotY: rotY,
    rotZ: rotZ,
    makeCamera: makeCamera,
    project: project,
    lambert: lambert,
    hexToRgb: hexToRgb,
    shade: shade,
    drawPolys: drawPolys,
    boxFaces: boxFaces,
    octaFaces: octaFaces
  };
})(window);
