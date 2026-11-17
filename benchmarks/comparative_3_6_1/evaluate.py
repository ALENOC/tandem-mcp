"""Independent quality evaluation for all 9 comparative benchmark workloads.

Never treats Tandem's `VERIFIED` state as proof of correctness. Runs the same
independent checks across Scenario A (Gemini Direct), Scenario B (Gemini + Direct
LM Studio), and Scenario C (Gemini + Tandem MCP).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA = {
    'type': 'object',
    'required': ['name', 'requires_python', 'dependencies', 'script'],
    'properties': {
        'name': {'type': 'string'},
        'requires_python': {'type': 'string'},
        'dependencies': {'type': 'array', 'items': {'type': 'string'}},
        'script': {'type': 'string'},
    },
}

PLAYWRIGHT_CORE_PATHS = [
    '/home/ale/.npm/_npx/9b9809298fe40d2c/node_modules/playwright-core',
    '/home/ale/.npm/_npx/e41f203b7505f1fb/node_modules/playwright-core',
]
CHROMIUM_BIN = '/home/ale/.cache/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell'


def _squash(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip().lower()


def _check_citations(answer_text: str, source_text: str) -> dict[str, Any]:
    """Check quoted strings (in double quotes >= 12 chars) against source_text."""
    quotes = re.findall(r'"([^"\n]{12,160})"', answer_text)
    if not quotes:
        return {'quotes_checked': 0, 'quotes_valid': 0, 'quotes_invalid': 0}
    src_sq = _squash(source_text)
    valid = sum(1 for q in quotes if _squash(q) in src_sq)
    return {
        'quotes_checked': len(quotes),
        'quotes_valid': valid,
        'quotes_invalid': len(quotes) - valid,
    }


def eval_reading_readme(answer_text: str, fixtures_dir: Path) -> dict[str, Any]:
    src = (fixtures_dir / 'README_v3_6_1.md').read_text()
    has_sandbox = 'TANDEM_SANDBOX' in answer_text
    mentions_network = 'network' in answer_text.lower()
    hallucinated_net = 'TANDEM_NET' in answer_text
    cites = _check_citations(answer_text, src)
    hits = int(has_sandbox) + int(mentions_network and not hallucinated_net)
    passed = has_sandbox and mentions_network and not hallucinated_net
    return {
        'passed': passed,
        'correctness_score': round(hits / 2.0, 2),
        'recall': round(hits / 2.0, 2),
        'has_tandem_sandbox': has_sandbox,
        'mentions_network_accurately': mentions_network and not hallucinated_net,
        'citations': cites,
        'constraint_compliance_pct': round(100.0 * hits / 2.0, 1),
    }


def eval_reading_grep_agent(answer_text: str, fixtures_dir: Path) -> dict[str, Any]:
    src = (fixtures_dir / 'agent_v3_6_1.py').read_text()
    low = answer_text.lower()
    mentions_skip = any(w in low for w in ['skip', 'not restored', 'not overwritten', 'left intact', 'untouched', 'not deleted', 'not restored', 'cannot be restored', 'leaves'])
    mentions_partial = 'partial' in low or 'too large' in low or 'snapshot' in low
    cites = _check_citations(answer_text, src)
    passed = mentions_skip and mentions_partial
    score = (int(mentions_skip) + int(mentions_partial)) / 2.0
    return {
        'passed': passed,
        'correctness_score': round(score, 2),
        'mentions_skip_or_intact': mentions_skip,
        'mentions_partial_or_too_large': mentions_partial,
        'citations': cites,
        'constraint_compliance_pct': round(100.0 * score, 1),
    }


def eval_reading_package_survey(answer_text: str, fixtures_dir: Path) -> dict[str, Any]:
    modules = ['__init__.py', '__main__.py', 'agent.py', 'digest.py', 'engine.py', 'sandbox.py', 'server.py', 'store.py']
    found = [m for m in modules if m in answer_text]
    recall = len(found) / len(modules)
    passed = len(found) >= 7
    return {
        'passed': passed,
        'correctness_score': round(recall, 2),
        'recall': round(recall, 2),
        'modules_found': len(found),
        'modules_expected': len(modules),
        'missing_modules': [m for m in modules if m not in found],
        'constraint_compliance_pct': round(100.0 * recall, 1),
    }


def eval_reading_git_history(answer_text: str, fixtures_dir: Path) -> dict[str, Any]:
    log_text = (fixtures_dir / 'git_log_30_stat.txt').read_text()
    low = answer_text.lower()
    # Check top changed files in v3.6.1 30-commit history
    key_files = ['server.py', 'agent.py', 'test_offline.py', 'digest.py', 'readme.md']
    found_files = [f for f in key_files if f in low]
    has_topics = any(w in low for w in ['release', 'security', 'sandbox', 'digest', 'test', 'rollback', '3.6'])
    cites = _check_citations(answer_text, log_text)
    passed = len(found_files) >= 2 and has_topics
    score = min(1.0, (len(found_files) / 3.0) * 0.7 + (0.3 if has_topics else 0.0))
    return {
        'passed': passed,
        'correctness_score': round(score, 2),
        'key_files_mentioned': found_files,
        'has_commit_topics': has_topics,
        'citations': cites,
        'constraint_compliance_pct': round(100.0 * score, 1),
    }


def eval_extraction_manifest(answer_text: str, fixtures_dir: Path) -> dict[str, Any]:
    data = None
    try:
        data = json.loads(answer_text.strip())
    except Exception:
        m = re.search(r'\{[\s\S]*\}', answer_text)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:
                data = None
    if not isinstance(data, dict):
        return {
            'passed': False,
            'schema_valid': False,
            'correctness_score': 0.0,
            'error': 'No valid JSON object found in response',
            'constraint_compliance_pct': 0.0,
        }
    import tomllib
    toml_data = tomllib.loads((fixtures_dir / 'pyproject_v3_6_1.toml').read_text())
    proj = toml_data.get('project', {})
    expected_deps = set(proj.get('dependencies', []))
    expected_scripts = set(proj.get('scripts', {}).keys())

    required = ['name', 'requires_python', 'dependencies', 'script']
    schema_valid = all(k in data for k in required) and isinstance(data.get('dependencies'), list)
    got_deps = set(str(d) for d in (data.get('dependencies') or []))
    got_script = str(data.get('script', ''))
    checks = {
        'name': data.get('name') == proj.get('name'),
        'requires_python': str(data.get('requires_python', '')) == str(proj.get('requires-python', '')),
        'dependencies': expected_deps.issubset(got_deps) and got_deps == expected_deps,
        'script': got_script in expected_scripts or any(s in got_script for s in expected_scripts),
    }
    hits = sum(1 for v in checks.values() if v)
    passed = schema_valid and hits == 4
    return {
        'passed': passed,
        'schema_valid': schema_valid,
        'field_checks': checks,
        'correctness_score': round(hits / 4.0, 2),
        'constraint_compliance_pct': round(100.0 * hits / 4.0, 1),
    }


def eval_bugfix_micro(ws_dir: Path, fixtures_dir: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, '-m', 'unittest', 'test_math_utils.py'],
        cwd=ws_dir, capture_output=True, text=True, timeout=30,
    )
    extra = subprocess.run(
        [sys.executable, '-c', 'from math_utils import clamp; assert clamp(-100,0,10)==0; assert clamp(0,0,10)==0; assert clamp(10,0,10)==10; assert clamp(99,0,10)==10'],
        cwd=ws_dir, capture_output=True, text=True, timeout=15,
    )
    orig_test = (fixtures_dir / 'bugfix_micro/test_math_utils.py').read_text()
    cur_test = (ws_dir / 'test_math_utils.py').read_text() if (ws_dir / 'test_math_utils.py').exists() else ''
    test_intact = orig_test == cur_test
    passed = proc.returncode == 0 and extra.returncode == 0 and test_intact
    return {
        'passed': passed,
        'unittest_ok': proc.returncode == 0,
        'edge_cases_ok': extra.returncode == 0,
        'test_file_intact': test_intact,
        'constraint_compliance_pct': 100.0 if passed else 0.0,
    }


def eval_bugfix_multifile(ws_dir: Path, fixtures_dir: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, '-m', 'unittest', 'test_config.py'],
        cwd=ws_dir, capture_output=True, text=True, timeout=30,
    )
    extra = subprocess.run(
        [sys.executable, '-c', 'from config_loader import parse_endpoint; ep=parse_endpoint({"host":"h","port":80,"tls":"false"}); assert ep.url()=="http://h:80"'],
        cwd=ws_dir, capture_output=True, text=True, timeout=15,
    )
    unchanged = all(
        (ws_dir / f).exists() and (ws_dir / f).read_text() == (fixtures_dir / 'bugfix_multifile' / f).read_text()
        for f in ['models.py', 'formatter.py', 'test_config.py']
    )
    passed = proc.returncode == 0 and extra.returncode == 0 and unchanged
    return {
        'passed': passed,
        'unittest_ok': proc.returncode == 0,
        'edge_cases_ok': extra.returncode == 0,
        'unrelated_files_intact': unchanged,
        'constraint_compliance_pct': 100.0 if passed else 0.0,
    }


def _find_playwright_core() -> str | None:
    for p in PLAYWRIGHT_CORE_PATHS:
        if Path(p).exists():
            return p
    return None


def _run_browser_check(ws_dir: Path, kind: str) -> dict[str, Any]:
    pw_path = _find_playwright_core()
    if not pw_path or not Path(CHROMIUM_BIN).exists():
        return {'browser_available': False, 'browser_passed': None}

    index_path = ws_dir / 'index.html'
    if not index_path.exists():
        return {'browser_available': True, 'browser_passed': False, 'error': 'index.html missing'}

    if kind == 'orbital':
        script = f"""
const pw = require({json.dumps(pw_path)});
(async () => {{
  const browser = await pw.chromium.launch({{ executablePath: {json.dumps(CHROMIUM_BIN)}, headless: true }});
  const page = await browser.newPage({{ viewport: {{ width: 1280, height: 720 }} }});
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => {{ if (m.type() === 'error') errors.push(m.text()); }});
  await page.goto('file://' + {json.dumps(str(index_path.resolve()))});
  await page.waitForTimeout(450);
  const info = await page.evaluate(() => {{
    const c = document.getElementById('sky') || document.querySelector('canvas');
    return {{
      hasCanvas: !!c,
      w: c ? c.width : 0,
      h: c ? c.height : 0,
      hasPlay: !!document.getElementById('btnPlay'),
      hasTrails: !!document.getElementById('btnTrails'),
      hasReset: !!document.getElementById('btnReset'),
      hasSpeed: !!document.getElementById('speed'),
      simTime: (document.getElementById('simTime') || {{}}).textContent || ''
    }};
  }});
  await page.mouse.click(640, 360);
  await page.waitForTimeout(200);
  await browser.close();
  console.log(JSON.stringify({{ errors, info }}));
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    else:
        script = f"""
const pw = require({json.dumps(pw_path)});
(async () => {{
  const browser = await pw.chromium.launch({{ executablePath: {json.dumps(CHROMIUM_BIN)}, headless: true }});
  const page = await browser.newPage({{ viewport: {{ width: 1280, height: 720 }} }});
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => {{ if (m.type() === 'error') errors.push(m.text()); }});
  await page.goto('file://' + {json.dumps(str(index_path.resolve()))});
  await page.waitForTimeout(450);
  const info = await page.evaluate(() => {{
    const c = document.getElementById('c') || document.querySelector('canvas');
    return {{
      hasCanvas: !!c,
      w: c ? c.width : 0,
      h: c ? c.height : 0,
      hasPause: !!document.getElementById('btnPause'),
      hasOrbit: !!document.getElementById('btnOrbit'),
      hasReset: !!document.getElementById('btnReset'),
      hasSpeed: !!document.getElementById('speed'),
      polys: (document.getElementById('polys') || {{}}).textContent || '',
      parts: (document.getElementById('parts') || {{}}).textContent || ''
    }};
  }});
  await browser.close();
  console.log(JSON.stringify({{ errors, info }}));
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    proc = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        return {'browser_available': True, 'browser_passed': False, 'error': proc.stderr[:400]}
    try:
        parsed = json.loads(proc.stdout.strip().splitlines()[-1])
        info = parsed['info']
        errs = parsed['errors']
        ok = bool(info.get('hasCanvas') and info.get('w', 0) > 0 and len(errs) == 0)
        return {'browser_available': True, 'browser_passed': ok, 'console_errors': errs, 'dom_info': info}
    except Exception as exc:
        return {'browser_available': True, 'browser_passed': False, 'error': str(exc)}


def eval_gen_orbital(ws_dir: Path, fixtures_dir: Path) -> dict[str, Any]:
    index_path = ws_dir / 'index.html'
    if not index_path.exists():
        return {'passed': False, 'error': 'index.html not generated', 'constraint_compliance_pct': 0.0}
    harness = ws_dir / 'check_page.js'
    if not harness.exists():
        harness.write_text((fixtures_dir / 'contracts/check_page.js').read_text())
    node_proc = subprocess.run(['node', 'check_page.js'], cwd=ws_dir, capture_output=True, text=True, timeout=30)
    browser = _run_browser_check(ws_dir, 'orbital')
    browser_ok = True if browser.get('browser_passed') is None else bool(browser.get('browser_passed'))
    passed = node_proc.returncode == 0 and browser_ok
    return {
        'passed': passed,
        'harness_ok': node_proc.returncode == 0,
        'harness_output': (node_proc.stdout + node_proc.stderr).strip()[:300],
        'browser': browser,
        'output_bytes': index_path.stat().st_size,
        'constraint_compliance_pct': 100.0 if passed else (50.0 if browser_ok or node_proc.returncode == 0 else 0.0),
    }


def eval_gen_portal(ws_dir: Path, fixtures_dir: Path) -> dict[str, Any]:
    index_path = ws_dir / 'index.html'
    if not index_path.exists():
        return {'passed': False, 'error': 'index.html not generated', 'constraint_compliance_pct': 0.0}
    multi_file = all((ws_dir / f).exists() for f in ['scene.js', 'engine3d.js', 'app.js'])
    harness_ok = None
    harness_out = ''
    if multi_file:
        harness = ws_dir / 'check_engine.js'
        if not harness.exists():
            harness.write_text((fixtures_dir / 'contracts/check_engine.js').read_text())
        node_proc = subprocess.run(['node', 'check_engine.js'], cwd=ws_dir, capture_output=True, text=True, timeout=30)
        harness_ok = node_proc.returncode == 0
        harness_out = (node_proc.stdout + node_proc.stderr).strip()[:300]
    browser = _run_browser_check(ws_dir, 'portal')
    browser_ok = True if browser.get('browser_passed') is None else bool(browser.get('browser_passed'))
    passed = browser_ok and (True if harness_ok is None else harness_ok)
    total_bytes = sum(p.stat().st_size for p in ws_dir.glob('*') if p.is_file() and p.suffix in {'.html', '.js', '.css'})
    return {
        'passed': passed,
        'multi_file': multi_file,
        'harness_ok': harness_ok,
        'harness_output': harness_out,
        'browser': browser,
        'output_bytes': total_bytes,
        'constraint_compliance_pct': 100.0 if passed else (50.0 if browser_ok else 0.0),
    }


def evaluate_task(task_id: str, answer_text: str, ws_dir: Path, fixtures_dir: Path) -> dict[str, Any]:
    if task_id == 'reading_readme':
        return eval_reading_readme(answer_text, fixtures_dir)
    if task_id == 'reading_grep_agent':
        return eval_reading_grep_agent(answer_text, fixtures_dir)
    if task_id == 'reading_package_survey':
        return eval_reading_package_survey(answer_text, fixtures_dir)
    if task_id == 'reading_git_history':
        return eval_reading_git_history(answer_text, fixtures_dir)
    if task_id == 'extraction_manifest':
        return eval_extraction_manifest(answer_text, fixtures_dir)
    if task_id == 'bugfix_micro':
        return eval_bugfix_micro(ws_dir, fixtures_dir)
    if task_id == 'bugfix_multifile':
        return eval_bugfix_multifile(ws_dir, fixtures_dir)
    if task_id == 'gen_orbital':
        return eval_gen_orbital(ws_dir, fixtures_dir)
    if task_id == 'gen_portal':
        return eval_gen_portal(ws_dir, fixtures_dir)
    raise ValueError(f'Unknown task_id: {task_id}')
