// scene.js
// Geometry builders for the neon portal scene.
// Exposes window.Scene with box(), octahedron() and the assembled scene graph.

(function (global) {
  "use strict";
  var E = global.Engine3D;

  // A box centered at (cx,cy,cz) with half-extents (hx,hy,hz).
  // Returns { faces: [ {verts:[4 world pts], normal} x6 ] }
  function box(cx, cy, cz, hx, hy, hz) {
    var x0 = cx - hx, x1 = cx + hx;
    var y0 = cy - hy, y1 = cy + hy;
    var z0 = cz - hz, z1 = cz + hz;
    var V = E.v3;
    // each face: 4 corners in CCW order when viewed from outside
    var faces = [
      { n: V(0, 0, 1),  v: [V(x0, y0, z1), V(x1, y0, z1), V(x1, y1, z1), V(x0, y1, z1)] }, // front
      { n: V(0, 0, -1), v: [V(x1, y0, z0), V(x0, y0, z0), V(x0, y1, z0), V(x1, y1, z0)] }, // back
      { n: V(1, 0, 0),  v: [V(x1, y0, z1), V(x1, y0, z0), V(x1, y1, z0), V(x1, y1, z1)] }, // right
      { n: V(-1, 0, 0), v: [V(x0, y0, z0), V(x0, y0, z1), V(x0, y1, z1), V(x0, y1, z0)] }, // left
      { n: V(0, 1, 0),  v: [V(x0, y1, z1), V(x1, y1, z1), V(x1, y1, z0), V(x0, y1, z0)] }, // top
      { n: V(0, -1, 0), v: [V(x0, y0, z0), V(x1, y0, z0), V(x1, y0, z1), V(x0, y0, z1)] }  // bottom
    ];
    return { faces: faces };
  }

  // An octahedron centered at origin with radius r.
  // 8 triangles. Returns { tris: [ [a,b,c] x8 ] }
  function octahedron(r) {
    var V = E.v3;
    var px = V(r, 0, 0), nx = V(-r, 0, 0);
    var py = V(0, r, 0), ny = V(0, -r, 0);
    var pz = V(0, 0, r), nz = V(0, 0, -r);
    return {
      tris: [
        [px, py, pz], [pz, py, nx], [nx, py, pz], [ny, px, pz],
        [py, nz, px], [nx, nz, py], [ny, pz, nx], [px, nz, ny]
      ]
    };
  }

  // Build the full static scene graph.
  // Returns { boxes: [ {box, base:{r,g,b}, glow} ], boxFaces, crystalTris }
  function buildScene() {
    var boxes = [];

    // Two-tier platform: lower wide box + upper smaller box.
    boxes.push({ box: box(0, -1.0, 0, 3.2, 0.5, 3.2), base: { r: 13, g: 16, b: 48 }, glow: 0, edge: true });
    boxes.push({ box: box(0, -0.35, 0, 2.2, 0.35, 2.2), base: { r: 13, g: 16, b: 48 }, glow: 0, edge: true });

    // Twin pillars (magenta tones).
    boxes.push({ box: box(-2.0, 1.2, 0, 0.35, 1.55, 0.35), base: { r: 120, g: 20, b: 120 }, glow: 0, edge: true, pillar: true });
    boxes.push({ box: box(2.0, 1.2, 0, 0.35, 1.55, 0.35), base: { r: 120, g: 20, b: 120 }, glow: 0, edge: true, pillar: true });

    // Lintel across the tops of the pillars.
    boxes.push({ box: box(0, 2.75, 0, 2.35, 0.3, 0.4), base: { r: 120, g: 20, b: 120 }, glow: 0, edge: true, pillar: true });

    // Crown cap above the lintel.
    boxes.push({ box: box(0, 3.15, 0, 1.6, 0.25, 0.5), base: { r: 150, g: 30, b: 150 }, glow: 0, edge: true, pillar: true });

    var boxFaces = boxes.length * 6; // 6 boxes * 6 faces = 36
    var crystalTris = 6 * 8;         // 6 crystals * 8 tris = 48

    return { boxes: boxes, boxFaces: boxFaces, crystalTris: crystalTris };
  }

  global.Scene = { box: box, octahedron: octahedron, buildScene: buildScene };
})(window);
