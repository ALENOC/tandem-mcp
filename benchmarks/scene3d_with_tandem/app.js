(function () {
  'use strict';

  var canvas = document.getElementById('c');
  var hudRefs = {
    fpsEl: document.getElementById('fps'),
    polysEl: document.getElementById('polys'),
    partsEl: document.getElementById('parts'),
    playBtn: document.getElementById('playBtn'),
    orbitBtn: document.getElementById('orbitBtn'),
    resetBtn: document.getElementById('resetBtn'),
    spd: document.getElementById('spd'),
    spdVal: document.getElementById('spdVal')
  };

  var engine = new window.PortalEngine(canvas, hudRefs);
  engine.start();
})();
