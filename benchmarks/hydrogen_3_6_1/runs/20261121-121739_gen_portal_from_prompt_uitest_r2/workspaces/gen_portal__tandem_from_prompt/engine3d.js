// engine3d.js - minimal software 3D renderer
// Provides perspective projection, 3D rotation, backface culling,
// painter's z-sort and flat lighting.

(function (global) {
  "use strict";

  const Engine = {};

  // --- Vector / matrix helpers -------------------------------------------

  // Rotate a point around the Y axis (radians).
  function rotY(p, a) {
    const c = Math.cos(a), s = Math.sin(a);
    return { x: p.x * c + p.z * s, y: p.y, z: -p.x * s + p.z * c };
  }

  // Rotate a point around the X axis (radians).
  function rotX(p, a) {
    const c = Math.cos(a), s = Math.sin(a);
    return { x: p.x, y: p.y * c - p.z * s, z: p.y * s + p.z * c };
  }

  // Rotate a point around the Z axis (radians).
  function rotZ(p, a) {
    const c = Math.cos(a), s = Math.sin(a);
    return { x: p.x * c - p.y * s, y: p.x * s + p.y * c, z: p.z };
  }

  // Full 3D rotation: yaw (Y), pitch (X), roll (Z).
  function rotate3D(p, yaw, pitch, roll) {
    let q = rotY(p, yaw);
    q = rotX(q, pitch);
    q = rotZ(q, roll);
    return q;
  }

  // --- Camera ------------------------------------------------------------

  function makeCamera() {
    return {
      yaw: 0.6,
      pitch: -0.35,
      roll: 0,
      dist: 14,
      fov: 1.0,
      cx: 0,
      cy: 0,
      cz: 0
    };
  }

  // Transform a world point into camera space.
  function toCamera(p, cam) {
    let q = { x: p.x - cam.cx, y: p.y - cam.cy, z: p.z - cam.cz };
    q = rotY(q, -cam.yaw);
    q = rotX(q, -cam.pitch);
    q = rotZ(q, -cam.roll);
    return q;
  }

  // Perspective projection of a camera-space point.
  // Returns { x, y, z, w } where x,y are screen pixels, z is depth,
  // w is the perspective divide factor (1/z).
  function project(p, cam, width, height) {
    const q = toCamera(p, cam);
    const z = q.z + cam.dist;
    if (z <= 0.1) return null;
    const f = (height * 0.5) / Math.tan(cam.fov * 0.5);
    const sx = width * 0.5 + (q.x * f) / z;
    const sy = height * 0.5 - (q.y * f) / z;
    return { x: sx, y: sy, z: z, w: 1 / z };
  }

  // --- Geometry ----------------------------------------------------------

  // Build a box (axis-aligned) centered at (cx,cy,cz) with half extents.
  // Returns 6 faces, each face = { verts:[{x,y,z}x4], color, normal }.
  function makeBox(cx, cy, cz, sx, sy, sz, color) {
    const x0 = cx - sx, x1 = cx + sx;
    const y0 = cy - sy, y1 = cy + sy;
    const z0 = cz - sz, z1 = cz + sz;
    const faces = [];
    // +Z
    faces.push({ verts: [{x:x0,y:y0,z:z1},{x:x1,y:y0,z:z1},{x:x1,y:y1,z:z1},{x:x0,y:y1,z:z1}], color, normal: {x:0,y:0,z:1} });
    // -Z
    faces.push({ verts: [{x:x1,y:y0,z:z0},{x:x0,y:y0,z:z0},{x:x0,y:y1,z:z0},{x:x1,y:y1,z:z0}], color, normal: {x:0,y:0,z:-1} });
    // +X
    faces.push({ verts: [{x:x1,y:y0,z:z1},{x:x1,y:y0,z:z0},{x:x1,y:y1,z:z0},{x:x1,y:y1,z:z1}], color, normal: {x:1,y:0,z:0} });
    // -X
    faces.push({ verts: [{x:x0,y:y0,z:z0},{x:x0,y:y0,z:z1},{x:x0,y:y1,z:z1},{x:x0,y:y1,z:z0}], color, normal: {x:-1,y:0,z:0} });
    // +Y (top)
    faces.push({ verts: [{x:x0,y:y1,z:z1},{x:x1,y:y1,z:z1},{x:x1,y:y1,z:z0},{x:x0,y:y1,z:z0}], color, normal: {x:0,y:1,z:0} });
    // -Y (bottom)
    faces.push({ verts: [{x:x0,y:y0,z:z0},{x:x1,y:y0,z:z0},{x:x1,y:y0,z:z1},{x:x0,y:y0,z:z1}], color, normal: {x:0,y:-1,z:0} });
    return faces;
  }

  // Build an octahedron centered at origin with radius r.
  // 8 triangular faces.
  function makeOctahedron(cx, cy, cz, r, color) {
    const A = { x: cx, y: cy + r, z: cz };
    const B = { x: cx + r, y: cy, z: cz };
    const C = { x: cx, y: cy, z: cz + r };
    const D = { x: cx - r, y: cy, z: cz };
    const E = { x: cx, y: cy, z: cz - r };
    const F = { x: cx, y: cy - r, z: cz };
    const faces = [];
    // top pyramid
    faces.push({ verts: [A, B, C], color, normal: normalize({x:1,y:1,z:1}) });
    faces.push({ verts: [A, C, D], color, normal: normalize({x:-1,y:1,z:1}) });
    faces.push({ verts: [A, D, E], color, normal: normalize({x:-1,y:1,z:-1}) });
    faces.push({ verts: [A, E, B], color, normal: normalize({x:1,y:1,z:-1}) });
    // bottom pyramid
    faces.push({ verts: [F, C, B], color, normal: normalize({x:1,y:-1,z:1}) });
    faces.push({ verts: [F, D, C], color, normal: normalize({x:-1,y:-1,z:1}) });
    faces.push({ verts: [F, E, D], color, normal: normalize({x:-1,y:-1,z:-1}) });
    faces.push({ verts: [F, B, E], color, normal: normalize({x:1,y:-1,z:-1}) });
    return faces;
  }

  function normalize(v) {
    const l = Math.hypot(v.x, v.y, v.z) || 1;
    return { x: v.x / l, y: v.y / l, z: v.z / l };
  }

  // --- Rendering ---------------------------------------------------------

  // Flat lighting: dot product of face normal with a fixed light direction.
  const LIGHT = normalize({ x: -0.4, y: 0.8, z: 0.5 });

  function shade(color, n) {
    // n is the world-space normal; brightness from light.
    let d = n.x * LIGHT.x + n.y * LIGHT.y + n.z * LIGHT.z;
    d = 0.35 + 0.65 * Math.max(0, d);
    const r = Math.min(255, Math.floor(color.r * d));
    const g = Math.min(255, Math.floor(color.g * d));
    const b = Math.min(255, Math.floor(color.b * d));
    return "rgb(" + r + "," + g + "," + b + ")";
  }

  // Render a list of faces. Each face: { verts (world), color {r,g,b}, normal }.
  // Applies backface culling, painter's z-sort and flat lighting.
  function renderFaces(ctx, faces, cam, width, height) {
    const polys = [];
    for (let i = 0; i < faces.length; i++) {
      const face = faces[i];
      const proj = [];
      let ok = true;
      let depth = 0;
      for (let j = 0; j < face.verts.length; j++) {
        const p = project(face.verts[j], cam, width, height);
        if (!p) { ok = false; break; }
        proj.push(p);
        depth += p.z;
      }
      if (!ok) continue;
      depth /= proj.length;

      // Backface culling: compute screen-space winding (signed area).
      let area = 0;
      for (let j = 0; j < proj.length; j++) {
        const a = proj[j];
        const b = proj[(j + 1) % proj.length];
        area += a.x * b.y - b.x * a.y;
      }
      // Keep faces with positive (counter-clockwise) winding in screen space.
      if (area <= 0) continue;

      polys.push({ proj, depth, color: face.color, normal: face.normal });
    }

    // Painter's algorithm: sort far to near.
    polys.sort(function (a, b) { return b.depth - a.depth; });

    for (let i = 0; i < polys.length; i++) {
      const poly = polys[i];
      ctx.beginPath();
      ctx.moveTo(poly.proj[0].x, poly.proj[0].y);
      for (let j = 1; j < poly.proj.length; j++) {
        ctx.lineTo(poly.proj[j].x, poly.proj[j].y);
      }
      ctx.closePath();
      ctx.fillStyle = shade(poly.color, poly.normal);
      ctx.fill();
      ctx.strokeStyle = "rgba(0,0,0,0.25)";
      ctx.lineWidth = 0.5;
      ctx.stroke();
    }
    return polys.length;
  }

  Engine.makeCamera = makeCamera;
  Engine.project = project;
  Engine.toCamera = toCamera;
  Engine.rotate3D = rotate3D;
  Engine.rotY = rotY;
  Engine.rotX = rotX;
  Engine.rotZ = rotZ;
  Engine.makeBox = makeBox;
  Engine.makeOctahedron = makeOctahedron;
  Engine.normalize = normalize;
  Engine.shade = shade;
  Engine.renderFaces = renderFaces;
  Engine.LIGHT = LIGHT;

  global.Engine = Engine;
})(typeof window !== "undefined" ? window : this);
