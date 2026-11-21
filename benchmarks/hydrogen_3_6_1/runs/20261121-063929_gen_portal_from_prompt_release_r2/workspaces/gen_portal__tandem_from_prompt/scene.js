// scene.js - Neon portal scene: monument, crystals, rings, grid, stars, particles

var STAR_COUNT = 180;
var PARTICLE_COUNT = 110;
var CRYSTAL_COUNT = 6;

function Scene() {
  this.time = 0;
  this.speed = 1;
  this.paused = false;
  this.orbitOn = true;
  this.polyCount = 0;
  this.partCount = 0;

  // --- Portal monument: 6 boxes = 36 faces ---
  // Two-tier platform, twin pillars, lintel, crown cap
  this.boxes = [
    { faces: makeBox(0, 0.25, 0, 8, 0.5, 5), color: '#1b2a4a' },   // platform tier 1
    { faces: makeBox(0, 0.75, 0, 6, 0.5, 4), color: '#243b66' },   // platform tier 2
    { faces: makeBox(-2.5, 2.75, 0, 0.8, 4, 0.8), color: '#2c4a80' }, // left pillar
    { faces: makeBox(2.5, 2.75, 0, 0.8, 4, 0.8), color: '#2c4a80' },  // right pillar
    { faces: makeBox(0, 5.0, 0, 6, 0.5, 0.8), color: '#35598f' },     // lintel
    { faces: makeBox(0, 5.45, 0, 6.6, 0.4, 1.2), color: '#3f6aa8' }   // crown cap
  ];

  // --- Six orbiting octahedral crystals (6 x 8 = 48 triangles) ---
  this.crystalRadius = 3.6;
  this.crystalSize = 0.45;

  // --- Portal core + two counter-rotating rings ---
  this.coreCenter = v3(0, 2.75, 0);
  this.ringSegments = 48;
  this.ring1Radius = 1.35;
  this.ring2Radius = 1.75;

  // --- Cyber grid floor ---
  this.gridExtent = 16;
  this.gridStep = 2;

  // --- 180 twinkling stars on a far sphere ---
  this.stars = [];
  for (var i = 0; i < STAR_COUNT; i++) {
    var theta = Math.random() * Math.PI * 2;
    var phi = Math.acos(2 * Math.random() - 1);
    var r = 70 + Math.random() * 20;
    this.stars.push({
      p: v3(r * Math.sin(phi) * Math.cos(theta),
            Math.abs(r * Math.cos(phi)) * 0.6 + 4,
            r * Math.sin(phi) * Math.sin(theta)),
      phase: Math.random() * Math.PI * 2,
      tw: 1 + Math.random() * 3,
      size: 0.8 + Math.random() * 1.6
    });
  }

  // --- 110 rising neon particles ---
  this.particles = [];
  for (var j = 0; j < PARTICLE_COUNT; j++) {
    this.particles.push(this.makeParticle(true));
  }
}

Scene.prototype.makeParticle = function (randomY) {
  return {
    x: (Math.random() - 0.5) * 14,
    y: randomY ? Math.random() * 9 : 0,
    z: (Math.random() - 0.5) * 14,
    vy: 0.4 + Math.random() * 0.9,
    hue: Math.random() < 0.5 ? 185 : 300,
    phase: Math.random() * Math.PI * 2
  };
};

Scene.prototype.update = function (dt) {
  if (this.paused) return;
  this.time += dt * this.speed;
  for (var i = 0; i < this.particles.length; i++) {
    var p = this.particles[i];
    p.y += p.vy * dt * this.speed;
    if (p.y > 9) {
      p.y = 0;
      p.x = (Math.random() - 0.5) * 14;
      p.z = (Math.random() - 0.5) * 14;
    }
  }
};

Scene.prototype.draw = function (renderer) {
  var t = this.time;
  var ctx = renderer.ctx;
  this.polyCount = 0;
  this.partCount = 0;

  // --- Cyber perspective grid floor ---
  ctx.lineWidth = 1;
  for (var g = -this.gridExtent; g <= this.gridExtent; g += this.gridStep) {
    var pulse = 0.25 + 0.15 * Math.sin(t * 2 + g * 0.5);
    ctx.globalAlpha = pulse;
    renderer.drawLine(v3(g, 0.01, -this.gridExtent), v3(g, 0.01, this.gridExtent), '#00e5ff', 1);
    renderer.drawLine(v3(-this.gridExtent, 0.01, g), v3(this.gridExtent, 0.01, g), '#00e5ff', 1);
  }
  ctx.globalAlpha = 1;

  // --- Portal monument boxes (36 faces) ---
  for (var b = 0; b < this.boxes.length; b++) {
    var box = this.boxes[b];
    renderer.drawFaces(box.faces, box.color, 0.95);
  }

  // --- Portal core glow inside the arch ---
  var core = this.coreCenter;
  var corePulse = 0.75 + 0.25 * Math.sin(t * 3);
  var cp = renderer.project(core);
  if (cp) {
    var scale = renderer.width / 14;
    var grad = ctx.createRadialGradient(cp.x, cp.y, 0, cp.x, cp.y, 2.2 * scale * corePulse);
    grad.addColorStop(0, 'rgba(255,255,255,0.95)');
    grad.addColorStop(0.35, 'rgba(0,229,255,0.55)');
    grad.addColorStop(0.7, 'rgba(124,77,255,0.22)');
    grad.addColorStop(1, 'rgba(124,77,255,0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cp.x, cp.y, 2.2 * scale * corePulse, 0, Math.PI * 2);
    ctx.fill();
  }

  // --- Two counter-rotating 3D neon rings around the core ---
  var r1 = t * 1.4;
  var r2 = -t * 1.0;
  for (var s = 0; s < this.ringSegments; s++) {
    var a0 = (s / this.ringSegments) * Math.PI * 2;
    var a1 = ((s + 1) / this.ringSegments) * Math.PI * 2;
    // Ring 1: rotates in XZ plane, tilted
    var p1a = v3(core.x + Math.cos(a0) * this.ring1Radius,
                 core.y + Math.sin(a0) * this.ring1Radius * 0.35 * Math.sin(r1),
                 core.z + Math.sin(a0) * this.ring1Radius * Math.cos(r1));
    var p1b = v3(core.x + Math.cos(a1) * this.ring1Radius,
                 core.y + Math.sin(a1) * this.ring1Radius * 0.35 * Math.sin(r1),
                 core.z + Math.sin(a1) * this.ring1Radius * Math.cos(r1));
    renderer.drawLine(p1a, p1b, '#00e5ff', 2);
    // Ring 2: counter-rotating, different tilt
    var p2a = v3(core.x + Math.cos(a0) * this.ring2Radius * Math.cos(r2),
                 core.y + Math.sin(a0) * this.ring2Radius,
                 core.z + Math.sin(a0) * this.ring2Radius * Math.sin(r2));
    var p2b = v3(core.x + Math.cos(a1) * this.ring2Radius * Math.cos(r2),
                 core.y + Math.sin(a1) * this.ring2Radius,
                 core.z + Math.sin(a1) * this.ring2Radius * Math.sin(r2));
    renderer.drawLine(p2a, p2b, '#ff2ec4', 2);
  }

  // --- Six orbiting octahedral crystals (48 triangles) ---
  for (var c = 0; c < CRYSTAL_COUNT; c++) {
    var ang = t * 0.8 + (c / CRYSTAL_COUNT) * Math.PI * 2;
    var cx = Math.cos(ang) * this.crystalRadius;
    var cy = 2.75 + Math.sin(t * 1.5 + c) * 0.5;
    var cz = Math.sin(ang) * this.crystalRadius;
    var faces = makeOctahedron(cx, cy, cz, this.crystalSize);
    renderer.drawFaces(faces, c % 2 === 0 ? '#7c4dff' : '#00e5ff', 0.9);
  }

  // --- 180 twinkling stars ---
  for (var st = 0; st < this.stars.length; st++) {
    var star = this.stars[st];
    var tw = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * star.tw + star.phase));
    renderer.drawPoint(star.p, 'rgba(255,255,255,' + tw.toFixed(3) + ')', star.size);
  }

  // --- 110 rising neon particles ---
  for (var pp = 0; pp < this.particles.length; pp++) {
    var pt = this.particles[pp];
    var flick = 0.5 + 0.5 * Math.sin(t * 4 + pt.phase);
    renderer.drawPoint(v3(pt.x, pt.y, pt.z),
      'hsla(' + pt.hue + ',100%,70%,' + (0.3 + 0.6 * flick).toFixed(3) + ')', 2.2);
  }
  this.partCount = this.particles.length;
};
