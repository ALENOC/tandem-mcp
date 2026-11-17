(function () {
  function makeBox(cx, cy, cz, sx, sy, sz, color, glow) {
    const hx = sx / 2;
    const hy = sy / 2;
    const hz = sz / 2;
    const x0 = cx - hx, x1 = cx + hx;
    const y0 = cy - hy, y1 = cy + hy;
    const z0 = cz - hz, z1 = cz + hz;

    return [
      { pts: [[x0, y0, z0], [x0, y1, z0], [x1, y1, z0], [x1, y0, z0]], color: color.slice(), glow }, // front (-z)
      { pts: [[x1, y0, z1], [x1, y1, z1], [x0, y1, z1], [x0, y0, z1]], color: color.slice(), glow }, // back (+z)
      { pts: [[x0, y0, z1], [x0, y1, z1], [x0, y1, z0], [x0, y0, z0]], color: color.slice(), glow }, // left (-x)
      { pts: [[x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]], color: color.slice(), glow }, // right (+x)
      { pts: [[x0, y1, z0], [x0, y1, z1], [x1, y1, z1], [x1, y1, z0]], color: color.slice(), glow }, // top (+y)
      { pts: [[x0, y0, z1], [x0, y0, z0], [x1, y0, z0], [x1, y0, z1]], color: color.slice(), glow }  // bottom (-y)
    ];
  }

  function build() {
    const faces = [].concat(
      makeBox(0, -1.45, 0, 5.6, 0.4, 3.6, [24, 34, 68], 0.06),
      makeBox(0, -1.05, 0, 4.2, 0.4, 2.4, [30, 44, 82], 0.09),
      makeBox(-1.25, 0.42, 0, 0.5, 2.55, 0.5, [28, 42, 78], 0.11),
      makeBox(1.25, 0.42, 0, 0.5, 2.55, 0.5, [28, 42, 78], 0.11),
      makeBox(0, 1.95, 0, 3.4, 0.5, 0.7, [34, 50, 90], 0.14),
      makeBox(0, 2.32, 0, 2.2, 0.24, 0.5, [42, 62, 95], 0.3)
    );

    const crystals = [];
    for (let i = 0; i < 6; i++) {
      crystals.push({
        angle: (i * Math.PI) / 3,
        color: i % 2 === 0 ? [40, 225, 255] : [255, 70, 215],
        spin: 0.95 + i * 0.12,
        phase: i * 1.7
      });
    }

    const stars = [];
    for (let i = 0; i < 180; i++) {
      let x, y, z;
      do {
        const u = Math.random() * 2 - 1;
        const theta = Math.random() * Math.PI * 2;
        const r = Math.sqrt(1 - u * u);
        x = 42 * r * Math.cos(theta);
        y = 42 * u;
        z = 42 * r * Math.sin(theta);
      } while (y < -4);

      stars.push({
        p: [x, y, z],
        size: 0.5 + Math.random() * 1.2,
        rate: 0.7 + Math.random() * 2.4,
        phase: Math.random() * Math.PI * 2
      });
    }

    const particles = [];
    for (let i = 0; i < 110; i++) {
      const ang = Math.random() * Math.PI * 2;
      const rad = Math.sqrt(Math.random()) * 3.4;
      particles.push({
        x: Math.cos(ang) * rad,
        y: -1.9 + Math.random() * 5.4,
        z: Math.sin(ang) * rad,
        v: 0.35 + Math.random() * 0.75,
        sway: Math.random() * Math.PI * 2,
        hue: i % 2 === 0 ? 188 : 312,
        size: 0.02 + Math.random() * 0.035
      });
    }

    return { faces, crystals, stars, particles };
  }

  window.Scene = { build: build };
})();
