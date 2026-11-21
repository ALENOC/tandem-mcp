"""tandem:ui_test: declarative UI acceptance tests written by the orchestrator, run by Tandem in headless Chromium.

A verify command of the form ``tandem:ui_test {json}`` is not run in the shell: Tandem runs the JSON
scenario against the page itself. The scenario lives inside the contract, so the executor can neither
read it as a file to edit nor weaken it. Steps (one action each):

    {"click": "#btnPause"}            CSS selector, or "text:<regex>" for a control by its label
    {"input": "#speed", "value": "3"} set a value and fire input/change
    {"key": "Space"}                  press a key
    {"wait": 500}                     milliseconds
    {"expect": "moving"|"static"}     canvas (or the whole view) changes or not over 0.8 s; "region": [x0,y0,x1,y1]
                                      limits it to part of the view (fractions), e.g. to ignore twinkling stars
    {"snapshot": "before"}            remember the view (optional region)
    {"differs": "before", "min": 0.05} share of pixels changed since the snapshot (tol 30, optional max)
    {"exists": "#c"}                  element present
    {"text": "#fps", "match": "^\\d+"} visible text matches a regex
    {"js": "window.state.t > 0"}      expression is truthy
    {"color": "#0b1020", "min": 0.3}  fraction of pixels near a color (tol 48, optional region [x0,y0,x1,y1])

Top-level keys: entry (default index.html), wait_ms (default 1000), viewport [w, h], allow_errors.
JavaScript errors fail the test unless allow_errors is true.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import web_check

PREFIX = 'tandem:ui_test'
_SCRIPT = Path(__file__).resolve().with_name('_ui_test.mjs')
_STEP_KEYS = {'click', 'input', 'key', 'wait', 'expect', 'exists', 'text', 'js', 'color', 'snapshot', 'differs'}
# steps that observe the result; a scenario made only of actions proves nothing
_ASSERT_KEYS = {'expect', 'exists', 'text', 'js', 'color', 'differs'}


def is_ui_test(command: str) -> bool:
    return str(command or '').strip().startswith(PREFIX)


def label(command: str) -> str:
    """Short name of a check for receipts read by the orchestrator: a scenario is not echoed back in full."""
    if not is_ui_test(command):
        return str(command)
    try:
        return f'{PREFIX} ({len(parse(command)["steps"])} steps)'
    except ValueError:
        return f'{PREFIX} (invalid)'


def parse(command: str) -> dict:
    """Return the scenario of a tandem:ui_test command, raising ValueError when it is malformed."""
    raw = str(command).strip()[len(PREFIX):].strip()
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f'tandem:ui_test needs a JSON object after the prefix: {exc}') from None
    if not isinstance(spec, dict) or not isinstance(spec.get('steps'), list) or not spec['steps']:
        raise ValueError('tandem:ui_test needs {"steps": [...]} with at least one step')
    for step in spec['steps']:
        if not isinstance(step, dict) or not (set(step) & _STEP_KEYS):
            raise ValueError(f'tandem:ui_test step {step!r} has no known action ({", ".join(sorted(_STEP_KEYS))})')
    if not any(set(s) & _ASSERT_KEYS for s in spec['steps']):
        raise ValueError('tandem:ui_test must assert something (expect, exists, text, js or color), not only act')
    return spec


def run(command: str, ws_root: str | Path, timeout_s: float = 90.0) -> tuple[int, str]:
    """Run the scenario. Returns (exit, report): 0 passed, 1 failed, 2 not_evaluated."""
    try:
        spec = parse(command)
    except ValueError as exc:
        return 1, f'FAIL: {exc}'
    node = shutil.which('node')
    chrome = web_check.find_chromium()
    if not node:
        return 2, 'not_evaluated: node executable not found for tandem:ui_test.'
    if not chrome:
        return 2, 'not_evaluated: Chromium executable not found for tandem:ui_test.'
    try:
        proc = subprocess.run([node, str(_SCRIPT), str(Path(ws_root).resolve()), chrome, json.dumps(spec)],
                              capture_output=True, text=True, timeout=max(15.0, float(timeout_s)))
    except subprocess.TimeoutExpired:
        return 2, f'not_evaluated: tandem:ui_test timed out after {int(timeout_s)}s.'
    lines = (proc.stdout or '').strip().splitlines()
    try:
        data = json.loads(lines[-1]) if lines else {}
    except json.JSONDecodeError:
        data = {}
    status = data.get('status')
    if status == 'not_evaluated' or (not data and proc.returncode == 2):
        return 2, f'not_evaluated: {data.get("reason") or (proc.stderr or "").strip()[-200:]}'
    steps = data.get('steps') or []
    if status == 'passed' and proc.returncode == 0:
        return 0, f'OK: ui_test passed {len(steps)} steps with 0 JS errors.'
    out = ['FAIL: ui_test']
    for s in steps:
        mark = 'ok ' if s.get('ok') else 'BAD'
        out.append(f'  {mark} step {s.get("i")} {json.dumps(s.get("step"))[:120]}: {s.get("detail")}')
    for e in (data.get('errors') or [])[:4]:
        out.append(f'  BAD js error: {e}')
    if not steps and not data.get('errors'):
        out.append(f'  probe exited {proc.returncode}: {(proc.stderr or proc.stdout or "").strip()[-300:]}')
    return 1, '\n'.join(out)
