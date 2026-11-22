// engine3d.js - hand-written software 3D renderer (no WebGL, no libraries)
// Math helpers, perspective projection, painter's-algorithm triangle/quad fill with flat shading.

(function (global) {
  'use strict';

  // ---- Vector / matrix helpers (column-major 4x4) ----

  function mat4Identity() {
    return [
      1, 0, 0, 0,
      0, 1, 0, 0,
      0, 0, 1, 0,
      0, 0, 0, 1
    ];
  }

  function mat4Multiply(a, b) {
    // result = a * b
    var out = new Array(16);
    for (var c = 0; c < 4; c++) {
      for (var r = 0; r < 4; r++) {
        var sum = 0;
        for (var k = 0; k < 4; k++) {
          sum += a[k * 4 + r] * b[c * 4 + k];
        }
        out[c * 4 + r] = sum;
      }
    }
    return out;
  }

  function mat4Perspective(fovY, aspect, near, far) {
    var f = 1 / Math.tan(fovY / 2);
    var nf = 1 / (near - far);
    var out = [
      f / aspect, 0, 0, 0,
      0, f, 0, 0,
      0, 0, (far + near) * nf, -1,
      0, 0, 2 * far * near * nf, 0
    ];
    return out;
  }

  function mat4Translate(x, y, z) {
    var m = mat4Identity();
    m[12] = x; m[13] = y; m[14] = z;
    return m;
  }

  function mat4RotateY(angle) {
    var c = Math.cos(angle), s = Math.sin(angle);
    var m = mat4Identity();
    m[0] = c; m[2] = -s;
    m[8] = s; m[10] = c;
    return m;
  }

  function mat4RotateX(angle) {
    var c = Math.cos(angle), s = Math.sin(angle);
    var m = mat4Identity();
    m[5] = c; m[6] = s;
    m[9] = -s; m[10] = c;
    return m;
  }

  function mat4Scale(x, y, z) {
    var m = mat4Identity();
    m[0] = x; m[5] = y; m[10] = z;
    return m;
  }

  // Transform a point [x,y,z] by a 4x4 matrix, returns [x,y,z,w]
  function transformPoint(m, p) {
    var x = p[0], y = p[1], z = p[2];
    return [
      m[0] * x + m[4] * y + m[8] * z + m[12],
      m[1] * x + m[5] * y + m[9] * z + m[13],
      m[2] * x + m[6] * y + m[10] * z + m[14],
      m[3] * x + m[7] * y + m[11] * z + m[15]
    ];
  }

  // Transform a direction (no translation) by a 4x4 matrix
  function transformDir(m, d) {
    var x = d[0], y = d[1], z = d[2];
    return [
      m[0] * x + m[4] * y + m[8] * z,
      m[1] * x + m[5] * y + m[9] * z,
      m[2] * x + m[6] * y + m[10] * z
    ];
  }

  // ---- Renderer ----

  function Renderer(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.width = 0;
    this.height = 0;
    this.dpr = 1;
    this.fov = Math.PI / 3;
    this.near = 0.1;
    this.far = 200;
    this.eye = [0, 0, 0];
    this.view = mat4Identity();
    this.proj = mat4Identity();
    this.count = 0; // polygons drawn this frame
  }

  Renderer.prototype.resize = function (w, h, dpr) {
    this.width = w;
    this.height = h;
    this.dpr = dpr || 1;
    this.canvas.width = Math.max(1, Math.floor(w * this.dpr));
    this.canvas.height = Math.max(1, Math.floor(h * this.dpr));
    this.canvas.style.width = w + 'px';
    this.canvas.style.height = h + 'px';
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this.proj = mat4Perspective(this.fov, w / h, this.near, this.far);
  };

  // Build a look-at view matrix (world -> camera)
  Renderer.prototype.lookAt = function (eye, center, up) {
    var ex = eye[0], ey = eye[1], ez = eye[2];
    var cx = center[0] - ex, cy = center[1] - ey, cz = center[2] - ez;
    var len = Math.sqrt(cx * cx + cy * cy + cz * cz) || 1;
    var f = [cx / len, cy / len, cz / len];
    // right = normalize(cross(f, up))
    var rx = f[1] * up[2] - f[2] * up[1];
    var ry = f[2] * up[0] - f[0] * up[2];
    var rz = f[0] * up[1] - f[1] * up[0];
    var rl = Math.sqrt(rx * rx + ry * ry + rz * rz) || 1;
    rx /= rl; ry /= rl; rz /= rl;
    // up' = cross(right, f)
    var ux = ry * f[2] - rz * f[1];
    var uy = rz * f[0] - rx * f[2];
    var uz = rx * f[1] - ry * f[0];
    // view matrix (column-major): rows of rotation are right, up, -forward
    this.view = [
      rx, ux, -f[0], 0,
      ry, uy, -f[1], 0,
      rz, uz, -f[2], 0,
      -(rx * ex + ry * ey + rz * ez),
      -(ux * ex + uy * ey + uz * ez),
      (f[0] * ex + f[1] * ey + f[2] * ez),
      0, 0, 0, 1
    ];
    this.eye = eye;
  };

  // Project a world point to screen. Returns null if behind camera.
  // out: {x, y, z (view-space depth, positive in front), w}
  Renderer.prototype.project = function (p) {
    var v = transformPoint(this.view, p);
    var clip = transformPoint(this.proj, v);
    if (clip[3] <= 0) return null;
    var nx = clip[0] / clip[3];
    var ny = clip[1] / clip[3];
    var x = (nx * 0.5 + 0.5) * this.width;
    var y = (1 - (ny * 0.5 + 0.5)) * this.height;
    return { x: x, y: y, z: v[2], w: clip[3] };
  };

  // Begin a frame: clear count, set up composite
  Renderer.prototype.begin = function () {
    this.count = 0;
    this.ctx.globalCompositeOperation = 'source-over';
  };

  // Fill a polygon (triangle or quad) with flat shading + optional edge stroke.
  // pts: array of world points [x,y,z]. color: css fill. edge: css stroke or null.
  Renderer.prototype.poly = function (pts, color, edge) {
    var n = pts.length;
    var scr = new Array(n);
    var depth = 0;
    for (var i = 0; i < n; i++) {
      var s = this.project(pts[i]);
      if (!s) return; // behind camera
      scr[i] = s;
      depth += s.z;
    }
    depth /= n;
    var ctx = this.ctx;
    ctx.beginPath();
    ctx.moveTo(scr[0].x, scr[0].y);
    for (var j = 1; j < n; j++) ctx.lineTo(scr[j].x, scr[j].y);
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.fill();
    if (edge) {
      ctx.strokeStyle = edge;
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
    this.count++;
    return depth;
  };

  // Draw a polyline (world points) as a stroke. Returns depth (avg) or null.
  Renderer.prototype.line = function (pts, color, width) {
    var n = pts.length;
    var scr = new Array(n);
    var depth = 0;
    for (var i = 0; i < n; i++) {
      var s = this.project(pts[i]);
      if (!s) return null;
      scr[i] = s;
      depth += s.z;
    }
    depth /= n;
    var ctx = this.ctx;
    ctx.beginPath();
    ctx.moveTo(scr[0].x, scr[0].y);
    for (var j = 1; j < n; j++) ctx.lineTo(scr[j].x, scr[j].y);
    ctx.strokeStyle = color;
    ctx.lineWidth = width || 2;
    ctx.stroke();
    this.count++;
    return depth;
  };

  // Draw a small screen-space dot (already projected).
  Renderer.prototype.dot = function (x, y, r, color) {
    var ctx = this.ctx;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    this.count++;
  };

  global.Engine3D = {
    mat4Identity: mat4Identity,
    mat4Multiply: mat4Multiply,
    mat4Perspective: mat4Perspective,
    mat4Translate: mat4Translate,
    mat4RotateY: mat4RotateY,
    mat4RotateX: mat4RotateX,
    mat4Scale: mat4Scale,
    transformPoint: transformPoint,
    transformDir: transformDir,
    Renderer: Renderer
  };

})(typeof window !== 'undefined' ? window : this);
