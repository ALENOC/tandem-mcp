#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import assert from 'node:assert/strict';
import { evaluatePendulumV2 } from './check_pendulum_v2.mjs';

const BASE_HTML = path.resolve(
  'benchmarks/auto_suite/runs/20261120-154823_receipt_ab/workspaces/web_pendulum__p3__A_direct/index.html'
);
const orig = fs.readFileSync(BASE_HTML, 'utf-8');
const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'pendulum-v2-test-'));

try {
  // 1. Positive control
  const dPos = path.join(tmpRoot, 'pos');
  fs.mkdirSync(dPos, { recursive: true });
  fs.writeFileSync(path.join(dPos, 'index.html'), orig, 'utf-8');
  const rPos = await evaluatePendulumV2(dPos);
  assert.equal(rPos.correct, true, `Positive control failed: ${JSON.stringify(rPos)}`);
  console.log('PASS positive control:', rPos.checks.reset.semantics);

  // 2. Negative control: inert Reset
  const dInert = path.join(tmpRoot, 'inert_reset');
  fs.mkdirSync(dInert, { recursive: true });
  const mInert = orig.replace(
    'resetBtn.addEventListener("click", () => {\n        resetSimulation();\n      });',
    'resetBtn.addEventListener("click", () => {\n        // inert reset\n      });'
  );
  assert.notEqual(mInert, orig);
  fs.writeFileSync(path.join(dInert, 'index.html'), mInert, 'utf-8');
  const rInert = await evaluatePendulumV2(dInert);
  assert.equal(rInert.correct, false, 'Inert reset unexpectedly passed');
  assert.equal(rInert.checks.reset.passed, false);
  assert.equal(rInert.checks.reset.semantics, 'defect_inert', `Expected defect_inert, got ${JSON.stringify(rInert.checks.reset)}`);
  console.log('PASS negative control inert_reset:', rInert.checks.reset);

  // 3. Negative control: arbitrary Reset
  const dArb = path.join(tmpRoot, 'arbitrary_reset');
  fs.mkdirSync(dArb, { recursive: true });
  const mArb = orig.replace(
    'resetBtn.addEventListener("click", () => {\n        resetSimulation();\n      });',
    'resetBtn.addEventListener("click", () => {\n        state.t1 = 0.15; state.t2 = -0.35; state.w1 = 0; state.w2 = 0; trail1.length = 0; trail2.length = 0; render();\n      });'
  );
  assert.notEqual(mArb, orig);
  fs.writeFileSync(path.join(dArb, 'index.html'), mArb, 'utf-8');
  const rArb = await evaluatePendulumV2(dArb);
  assert.equal(rArb.correct, false, 'Arbitrary reset unexpectedly passed');
  assert.equal(rArb.checks.reset.passed, false);
  assert.equal(rArb.checks.reset.semantics, 'defect_arbitrary', `Expected defect_arbitrary, got ${JSON.stringify(rArb.checks.reset)}`);
  console.log('PASS negative control arbitrary_reset:', rArb.checks.reset);

  console.log('3 checks, 0 failures');
} finally {
  fs.rmSync(tmpRoot, { recursive: true, force: true });
}
