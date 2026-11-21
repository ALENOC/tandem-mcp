#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import assert from 'node:assert/strict';
import { evaluateGolBehavioral } from './check_gol_behavioral.mjs';

const BASE_HTML = path.resolve(
  'benchmarks/auto_suite/runs/20261120-124523_thresh_eval/workspaces/evalt_gen_web_app__A_direct/index.html'
);

const orig = fs.readFileSync(BASE_HTML, 'utf-8');

const mutations = [
  {
    name: 'inert_clear',
    expectedFailedCheck: 'clear',
    mutate: (s) => s.replace('btnClear.addEventListener("click", () => {\n        clearGrid();', 'btnClear.addEventListener("click", () => {\n        // inert'),
  },
  {
    name: 'inert_draw',
    expectedFailedCheck: 'draw',
    mutate: (s) => s.replace('setCell(cell.x, cell.y, drawMode);', '// inert draw').replace('drawLine(lastPointerCell.x, lastPointerCell.y, cell.x, cell.y, drawMode);', '// inert drag').replace('setCell(cell.x, cell.y, drawMode);', '// inert drag2'),
  },
  {
    name: 'inert_step',
    expectedFailedCheck: 'step',
    mutate: (s) => s.replace('btnStep.addEventListener("click", () => {\n        if (isRunning) {\n          isRunning = false;\n        }\n        stepGeneration();', 'btnStep.addEventListener("click", () => {\n        // inert step'),
  },
  {
    name: 'inert_play',
    expectedFailedCheck: 'play',
    mutate: (s) => s.replace('btnPlay.addEventListener("click", () => {\n        isRunning = !isRunning;', 'btnPlay.addEventListener("click", () => {\n        if (isRunning) isRunning = false; // cannot resume'),
  },
  {
    name: 'inert_pause',
    expectedFailedCheck: 'pause',
    mutate: (s) => s.replace('btnPlay.addEventListener("click", () => {\n        isRunning = !isRunning;', 'btnPlay.addEventListener("click", () => {\n        isRunning = true; // cannot pause'),
  },
  {
    name: 'inert_randomize',
    expectedFailedCheck: 'randomize',
    mutate: (s) => s.replace('btnRandom.addEventListener("click", () => {\n        randomizeGrid();', 'btnRandom.addEventListener("click", () => {\n        // inert randomize'),
  },
  {
    name: 'inert_speed_slider',
    expectedFailedCheck: 'speedSlider',
    mutate: (s) => s.replace('targetSpeed = Number(speedSlider.value);', '// inert speed'),
  },
];

const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'gol-neg-'));
let passed = 0;

try {
  for (const m of mutations) {
    const mutated = m.mutate(orig);
    assert.notEqual(mutated, orig, `Mutation ${m.name} did not change source`);
    const dir = path.join(tmpRoot, m.name);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, 'index.html'), mutated, 'utf-8');
    const res = await evaluateGolBehavioral(dir);
    assert.equal(res.correct, false, `${m.name} unexpectedly passed`);
    assert.equal(res.checks[m.expectedFailedCheck]?.passed, false, `${m.name} did not fail check '${m.expectedFailedCheck}': ${JSON.stringify(res.checks)}`);
    console.log(`PASS negative control ${m.name}: failed '${m.expectedFailedCheck}' as expected`);
    passed++;
  }
  console.log(`${passed} negative control checks, 0 failures`);
} finally {
  fs.rmSync(tmpRoot, { recursive: true, force: true });
}
