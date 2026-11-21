// engine3d.js - Software 3D renderer with perspective projection, backface culling, painter's algorithm

// --- Vector3 helpers ---
function v3(x, y, z) { return { x: x || 0, y: y || 0, z: z || 0 }; }
function v3add(a, b) { return v3(a.x + b.x, a.y + b.y, a.z + b.z); }
function v3sub(a, b) { return v3(a.x - b.x, a.y - b.y, a.z - b.z); }
function v3scale(a, s) { return v3(a.x * s, a.y * s, a.z * s); }
function v3dot(a, b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
function v3cross(a, b) {
  return v3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x);
}
function v3len(a) { return Math.sqrt(a.x * a.x + a.y * a.y + a.z * a.z); }
function v3norm(a) { var l = v3len(a) || 1; return v3(a.x / l, a.y / l, a.z / l); }

// --- Matrix4 (column-major, OpenGL-style) ---
function mat4Identity() {
  return [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1];
}
function mat4Multiply(a, b) {
  var r = new Array(16);
  for (var c = 0; c < 4; c++) for (var row = 0; row < 4; row++) {
    r[c * 4 + row] = a[row] * b[c * 4] + a[4 + row] * b[c * 4 + 1] + a[8 + row] * b[c * 4 + 2] + a[12 + row] * b[c * 4 + 3];
  }
  return r;
}
function mat4Perspective(fov, aspect, near, far) {
  var f = 1 / Math.tan(fov / 2);
  var nf = 1 / (near - far);
  return [
    f / aspect, 0, 0, 0,
    0, f, 0, 0,
    0, 0, (far + near) * nf, -1,
    0, 0, 2 * far * near * nf, 0
  ];
}
function mat4LookAt(eye, target, up) {
  var z = v3norm(v3sub(eye, target));
  var x = v3norm(v3cross(up, z));
  var y = v3cross(z, x);
  return [
    x.x, y.x, z.x, 0,
    x.y, y.y, z.y, 0,
    x.z, y.z, z.z, 0,
    -v3dot(x, eye), -v3dot(y, eye), -v3dot(z, eye), 1
  ];
}
function mat4Translate(x, y, z) {
  return [1,0,0,0, 0,1,0,0, 0,0,1,0, x,y,z,1];
}
function mat4RotateX(a) {
  var c = Math.cos(a), s = Math.sin(a);
  return [1,0,0,0, 0,c,s,0, 0,-s,c,0, 0,0,0,1];
}
function mat4RotateY(a) {
  var c = Math.cos(a), s = Math.sin(a);
  return [c,0,-s,0, 0,1,0,0, s,0,c,0, 0,0,0,1];
}
function mat4RotateZ(a) {
  var c = Math.cos(a), s = Math.sin(a);
  return [c,s,0,0, -s,c,0,0, 0,0,1,0, 0,0,0,1];
}
function mat4Scale(sx, sy, sz) {
  return [sx,0,0,0, 0,sy,0,0, 0,0,sz,0, 0,0,0,1];
}
function mat4TransformPoint(m, p) {
  var x = p.x, y = p.y, z = p.z;
  return v3(
    m[0]*x + m[4]*y + m[8]*z + m[12],
    m[1]*x + m[5]*y + m[9]*z + m[13],
    m[2]*x + m[6]*y + m[10]*z + m[14]
  );
}
function mat4TransformDir(m, d) {
  return v3(
    m[0]*d.x + m[4]*d.y + m[8]*d.z,
    m[1]*d.x + m[5]*d.y + m[9]*d.z,
    m[2]*d.x + m[6]*d.y + m[10]*d.z
  );
}

// --- Geometry generators ---
function makeBox(cx, cy, cz, sx, sy, sz) {
  // Returns 6 faces (quads), each face = [v0, v1, v2, v3] (CCW from outside)
  var hx = sx / 2, hy = sy / 2, hz = sz / 2;
  var x0 = cx - hx, x1 = cx + hx;
  var y0 = cy - hy, y1 = cy + hy;
  var z0 = cz - hz, z1 = cz + hz;
  return [
    // front (+z)
    [v3(x0,y0,z1), v3(x1,y0,z1), v3(x1,y1,z1), v3(x0,y1,z1)],
    // back (-z)
    [v3(x1,y0,z0), v3(x0,y0,z0), v3(x0,y1,z0), v3(x1,y1,z0)],
    // right (+x)
    [v3(x1,y0,z1), v3(x1,y0,z0), v3(x1,y1,z0), v3(x1,y1,z1)],
    // left (-x)
    [v3(x0,y0,z0), v3(x0,y0,z1), v3(x0,y1,z1), v3(x0,y1,z0)],
    // top (+y)
    [v3(x0,y1,z1), v3(x1,y1,z1), v3(x1,y1,z0), v3(x0,y1,z0)],
    // bottom (-y)
    [v3(x0,y0,z0), v3(x1,y0,z0), v3(x1,y0,z1), v3(x0,y0,z1)]
  ];
}

function makeOctahedron(cx, cy, cz, r) {
  // 8 triangular faces
  var t = v3(cx, cy + r, cz);
  var b = v3(cx, cy - r, cz);
  var e = v3(cx + r, cy, cz);
  var w = v3(cx - r, cy, cz);
  var n = v3(cx, cy, cz + r);
  var s = v3(cx, cy, cz - r);
  return [
    [t, e, n], [t, n, w], [t, w, s], [t, s, e],
    [b, n, e], [b, w, n], [b, s, w], [b, e, s]
  ];
}

// --- Camera ---
function Camera() {
  this.azimuth = 0.6;
  this.elevation = 0.35;
  this.distance = 14;
  this.target = v3(0, 2, 0);
  this.fov = Math.PI / 3;
  this.near = 0.1;
  this.far = 200;
  this.aspect = 1;
}
Camera.prototype.getEye = function () {
  var ce = Math.cos(this.elevation), se = Math.sin(this.elevation);
  var ca = Math.cos(this.azimuth), sa = Math.sin(this.azimuth);
  return v3(
    this.target.x + this.distance * ce * sa,
    this.target.y + this.distance * se,
    this.target.z + this.distance * ce * ca
  );
};
Camera.prototype.getViewMatrix = function () {
  return mat4LookAt(this.getEye(), this.target, v3(0, 1, 0));
};
Camera.prototype.getProjectionMatrix = function () {
  return mat4Perspective(this.fov, this.aspect, this.near, this.far);
};

// --- Renderer ---
function Renderer(canvas) {
  this.canvas = canvas;
  this.ctx = canvas.getContext('2d');
  this.width = 0;
  this.height = 0;
  this.camera = new Camera();
  this.viewMat = mat4Identity();
  this.projMat = mat4Identity();
  this.polyCount = 0;
}
Renderer.prototype.resize = function (w, h) {
  this.width = w;
  this.height = h;
  this.canvas.width = w;
  this.canvas.height = h;
  this.camera.aspect = w / h;
};
Renderer.prototype.beginFrame = function () {
  this.viewMat = this.camera.getViewMatrix();
  this.projMat = this.camera.getProjectionMatrix();
  this.polyCount = 0;
};
Renderer.prototype.project = function (p) {
  // Transform to view space
  var vp = mat4TransformPoint(this.viewMat, p);
  // Apply perspective
  var proj = mat4TransformPoint(this.projMat, vp);
  if (proj.z <= 0) return null;
  var sx = (proj.x / proj.z) * 0.5 * this.width + this.width * 0.5;
  var sy = -(proj.y / proj.z) * 0.5 * this.height + this.height * 0.5;
  return { x: sx, y: sy, z: vp.z };
};
Renderer.prototype.drawFaces = function (faces, color, alpha) {
  // faces: array of faces, each face = array of v3 vertices
  // Backface culling + painter's algorithm
  var visible = [];
  for (var i = 0; i < faces.length; i++) {
    var f = faces[i];
    if (f.length < 3) continue;
    // Compute face normal in world space
    var e1 = v3sub(f[1], f[0]);
    var e2 = v3sub(f[2], f[0]);
    var normal = v3cross(e1, e2);
    // Vector from face center to camera eye
    var cx = 0, cy = 0, cz = 0;
    for (var j = 0; j < f.length; j++) { cx += f[j].x; cy += f[j].y; cz += f[j].z; }
    cx /= f.length; cy /= f.length; cz /= f.length;
    var toCam = v3sub(this.camera.getEye(), v3(cx, cy, cz));
    // Backface culling: skip if normal faces away from camera
    if (v3dot(normal, toCam) <= 0) continue;
    // Compute average depth for sorting
    var avgZ = 0;
    for (var k = 0; k < f.length; k++) {
      var vp = mat4TransformPoint(this.viewMat, f[k]);
      avgZ += vp.z;
    }
    avgZ /= f.length;
    visible.push({ verts: f, depth: avgZ });
  }
  // Painter's algorithm: sort back to front (larger z = farther in our convention)
  visible.sort(function (a, b) { return b.depth - a.depth; });
  // Draw
  var ctx = this.ctx;
  for (var m = 0; m < visible.length; m++) {
    var face = visible[m];
    var pts = [];
    var allVisible = true;
    for (var n = 0; n < face.verts.length; n++) {
      var sp = this.project(face.verts[n]);
      if (!sp) { allVisible = false; break; }
      pts.push(sp);
    }
    if (!allVisible) continue;
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (var p = 1; p < pts.length; p++) ctx.lineTo(pts[p].x, pts[p].y);
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.globalAlpha = alpha !== undefined ? alpha : 1;
    ctx.fill();
    ctx.strokeStyle = color;
    ctx.lineWidth = 0.5;
    ctx.stroke();
    this.polyCount++;
  }
  ctx.globalAlpha = 1;
};
Renderer.prototype.drawLine = function (a, b, color, width) {
  var pa = this.project(a);
  var pb = this.project(b);
  if (!pa || !pb) return;
  var ctx = this.ctx;
  ctx.beginPath();
  ctx.moveTo(pa.x, pa.y);
  ctx.lineTo(pb.x, pb.y);
  ctx.strokeStyle = color;
  ctx.lineWidth = width || 1;
  ctx.stroke();
};
Renderer.prototype.drawPoint = function (p, color, size) {
  var sp = this.project(p);
  if (!sp) return;
  var ctx = this.ctx;
  ctx.beginPath();
  ctx.arc(sp.x, sp.y, size || 1, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();
};
