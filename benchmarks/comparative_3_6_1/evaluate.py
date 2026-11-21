"""Independent quality evaluation for all 9 comparative benchmark workloads.

Never treats Tandem's `VERIFIED` state as proof of correctness. Runs the same
deterministic ground-truth checks and real headless Chromium multi-frame tests
across Scenario A (Gemini Direct), Scenario B (Gemini + Direct LM Studio), and
Scenario C (Gemini + Tandem MCP).
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import tomllib
from collections import Counter
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

BENCHMARKS_DIR = Path(__file__).resolve().parents[1]
if str(BENCHMARKS_DIR) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS_DIR))
from web_browser_check import run_browser_check  # noqa: E402


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
    """Ground-truth check against README_v3_6_1.md.

    In v3.6.1 README.md, `TANDEM_SANDBOX` configures sandbox mode (`secure`,
    `compatible`, `auto`) and network isolation is enforced by Bubblewrap
    namespaces (there is no `TANDEM_NET` env var in README_v3_6_1.md).
    """
    src = (fixtures_dir / 'README_v3_6_1.md').read_text()
    low = answer_text.lower()
    has_sandbox = 'TANDEM_SANDBOX' in answer_text
    has_sandbox_detail = any(w in low for w in ['secure', 'compatible', 'auto', 'bubblewrap'])
    hallucinated_net = 'TANDEM_NET' in answer_text
    cites = _check_citations(answer_text, src)
    hits = int(has_sandbox) + int(has_sandbox_detail and not hallucinated_net)
    passed = has_sandbox and has_sandbox_detail and not hallucinated_net
    return {
        'evaluated': True,
        'passed': passed,
        'correctness_score': round(hits / 2.0, 2),
        'recall': round(hits / 2.0, 2),
        'has_tandem_sandbox': has_sandbox,
        'has_sandbox_detail_without_hallucination': has_sandbox_detail and not hallucinated_net,
        'hallucinated_tandem_net': hallucinated_net,
        'citations': cites,
        'constraint_compliance_pct': round(100.0 * hits / 2.0, 1),
    }


def eval_reading_grep_agent(answer_text: str, fixtures_dir: Path) -> dict[str, Any]:
    src = (fixtures_dir / 'agent_v3_6_1.py').read_text()
    low = answer_text.lower()
    mentions_skip = any(w in low for w in [
        'skip', 'not restored', 'not overwritten', 'left intact',
        'untouched', 'not deleted', 'cannot be restored', 'leaves',
    ])
    mentions_partial = any(w in low for w in ['partial', 'too large', 'snapshot'])
    cites = _check_citations(answer_text, src)
    passed = mentions_skip and mentions_partial
    score = (int(mentions_skip) + int(mentions_partial)) / 2.0
    return {
        'evaluated': True,
        'passed': passed,
        'correctness_score': round(score, 2),
        'mentions_skip_or_intact': mentions_skip,
        'mentions_partial_or_too_large': mentions_partial,
        'citations': cites,
        'constraint_compliance_pct': round(100.0 * score, 1),
    }


def _extract_pkg_ground_truth(pkg_dir: Path) -> dict[str, list[str]]:
    """Extract public functions and key domain terms from frozen tandem_mcp_pkg/*.py via AST."""
    truth: dict[str, list[str]] = {}
    for pyf in sorted(pkg_dir.glob('*.py')):
        tree = ast.parse(pyf.read_text())
        pubs = [
            n.name for n in tree.body
            if isinstance(n, ast.FunctionDef) and not n.name.startswith('_')
        ]
        truth[pyf.name] = pubs
    return truth


_MODULE_RESPONSIBILITY_TERMS = {
    '__init__.py': ['version', '__version__'],
    '__main__.py': ['entry', 'main', 'cli', 'start'],
    'agent.py': ['delegate', 'rollback', 'snapshot', 'step', 'verify', 'guard'],
    'digest.py': ['digest', 'extract', 'quote', 'evidence', 'chunk', 'answer'],
    'engine.py': ['llm', 'chat', 'model', 'openai', 'probe', 'schema', 'lm studio'],
    'sandbox.py': ['bubblewrap', 'bwrap', 'jail', 'command', 'sandbox', 'path'],
    'server.py': ['mcp', 'tool', 'fastmcp', 'server'],
    'store.py': ['ledger', 'cache', 'job', 'log', 'lesson', 'storage', 'persist'],
}


def eval_reading_package_survey(answer_text: str, fixtures_dir: Path) -> dict[str, Any]:
    pkg_dir = fixtures_dir / 'tandem_mcp_pkg'
    ast_truth = _extract_pkg_ground_truth(pkg_dir)
    low = answer_text.lower()
    modules = sorted(ast_truth.keys())
    found_modules = [m for m in modules if m in answer_text]

    resp_hits = 0
    per_module = {}
    for m in modules:
        terms = _MODULE_RESPONSIBILITY_TERMS.get(m, []) + ast_truth.get(m, [])[:5]
        matched = [t for t in terms if t.lower() in low]
        ok = (m in answer_text) and len(matched) >= 1
        if ok:
            resp_hits += 1
        per_module[m] = {'mentioned': m in answer_text, 'matched_terms': matched[:4], 'ok': ok}

    mod_recall = len(found_modules) / len(modules)
    resp_recall = resp_hits / len(modules)
    passed = mod_recall >= 0.875 and resp_recall >= 0.75
    return {
        'evaluated': True,
        'passed': passed,
        'correctness_score': round(resp_recall, 2),
        'module_recall': round(mod_recall, 2),
        'responsibility_recall': round(resp_recall, 2),
        'modules_found': len(found_modules),
        'modules_expected': len(modules),
        'per_module': per_module,
        'constraint_compliance_pct': round(100.0 * resp_recall, 1),
    }


def parse_git_log_top_files(log_text: str, top_k: int = 5) -> list[tuple[str, int]]:
    """Deterministically compute most frequently modified files from git log --stat."""
    counts: Counter[str] = Counter()
    for line in log_text.splitlines():
        m = re.match(r'^\s+([^\s|]+)\s+\|\s+\d+', line)
        if m:
            counts[m.group(1)] += 1
    return counts.most_common(top_k)


def eval_reading_git_history(answer_text: str, fixtures_dir: Path) -> dict[str, Any]:
    log_text = (fixtures_dir / 'git_log_30_stat.txt').read_text()
    top_files = parse_git_log_top_files(log_text, top_k=5)
    low = answer_text.lower()

    matched_top = []
    for path_str, _cnt in top_files:
        basename = Path(path_str).name.lower()
        if path_str.lower() in low or basename in low:
            matched_top.append(path_str)

    top_recall = len(matched_top) / len(top_files) if top_files else 0.0
    has_topics = sum(1 for w in ['3.6', 'release', 'security', 'sandbox', 'digest', 'test', 'rollback'] if w in low) >= 2
    cites = _check_citations(answer_text, log_text)
    passed = len(matched_top) >= 3 and has_topics
    score = round(0.7 * top_recall + (0.3 if has_topics else 0.0), 2)
    return {
        'evaluated': True,
        'passed': passed,
        'correctness_score': score,
        'ground_truth_top_files': top_files,
        'matched_top_files': matched_top,
        'top_files_recall': round(top_recall, 2),
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
            'evaluated': True,
            'passed': False,
            'schema_valid': False,
            'correctness_score': 0.0,
            'error': 'No valid JSON object found in response',
            'constraint_compliance_pct': 0.0,
        }

    toml_data = tomllib.loads((fixtures_dir / 'pyproject_v3_6_1.toml').read_text())
    proj = toml_data.get('project', {})
    expected_deps = set(proj.get('dependencies', []))
    expected_scripts = set(proj.get('scripts', {}).keys())

    required = ['name', 'requires_python', 'dependencies', 'script']
    missing_fields = [k for k in required if k not in data]
    extra_fields = [k for k in data.keys() if k not in required]
    schema_valid = (not missing_fields) and isinstance(data.get('dependencies'), list) and isinstance(data.get('name'), str)
    got_deps = set(str(d) for d in (data.get('dependencies') or []))
    got_script = str(data.get('script', ''))
    checks = {
        'name': data.get('name') == proj.get('name'),
        'requires_python': str(data.get('requires_python', '')) == str(proj.get('requires-python', '')),
        'dependencies': got_deps == expected_deps,
        'script': got_script in expected_scripts or any(s in got_script for s in expected_scripts),
    }
    hits = sum(1 for v in checks.values() if v)
    passed = schema_valid and hits == 4 and not extra_fields
    return {
        'evaluated': True,
        'passed': passed,
        'schema_valid': schema_valid,
        'missing_fields': missing_fields,
        'extra_fields': extra_fields,
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
        'evaluated': True,
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
        'evaluated': True,
        'passed': passed,
        'unittest_ok': proc.returncode == 0,
        'edge_cases_ok': extra.returncode == 0,
        'unrelated_files_intact': unchanged,
        'constraint_compliance_pct': 100.0 if passed else 0.0,
    }


def _run_browser_check(ws_dir: Path, kind: str) -> dict[str, Any]:
    return run_browser_check(ws_dir, kind)


def eval_gen_orbital(ws_dir: Path, fixtures_dir: Path) -> dict[str, Any]:
    index_path = ws_dir / 'index.html'
    if not index_path.exists():
        return {'evaluated': True, 'status': 'failed', 'passed': False, 'error': 'index.html not generated', 'constraint_compliance_pct': 0.0}
    harness = ws_dir / 'check_page.js'
    harness.write_text((fixtures_dir / 'contracts/check_page.js').read_text())
    node_proc = subprocess.run(['node', 'check_page.js'], cwd=ws_dir, capture_output=True, text=True, timeout=30)
    browser = _run_browser_check(ws_dir, 'orbital')
    browser_status = browser.get('status', 'failed')
    harness_ok = node_proc.returncode == 0
    passed = harness_ok and browser_status == 'passed'
    status = 'not_evaluated' if browser_status == 'not_evaluated' else ('passed' if passed else 'failed')
    return {
        'evaluated': browser_status != 'not_evaluated',
        'status': status,
        'passed': passed,
        'harness_ok': harness_ok,
        'harness_output': (node_proc.stdout + node_proc.stderr).strip()[:300],
        'browser': browser,
        'output_bytes': index_path.stat().st_size,
        'constraint_compliance_pct': 100.0 if passed else (50.0 if (browser_status == 'passed') or harness_ok else 0.0),
    }


def eval_gen_portal(ws_dir: Path, fixtures_dir: Path) -> dict[str, Any]:
    index_path = ws_dir / 'index.html'
    if not index_path.exists():
        return {'evaluated': True, 'status': 'failed', 'passed': False, 'error': 'index.html not generated', 'constraint_compliance_pct': 0.0}
    multi_file = all((ws_dir / f).exists() for f in ['scene.js', 'engine3d.js', 'app.js'])
    harness_ok = False
    harness_out = 'missing scene.js, engine3d.js, or app.js'
    if multi_file:
        harness = ws_dir / 'check_engine.js'
        harness.write_text((fixtures_dir / 'contracts/check_engine.js').read_text())
        node_proc = subprocess.run(['node', 'check_engine.js'], cwd=ws_dir, capture_output=True, text=True, timeout=30)
        harness_ok = node_proc.returncode == 0
        harness_out = (node_proc.stdout + node_proc.stderr).strip()[:300]
    browser = _run_browser_check(ws_dir, 'portal')
    browser_status = browser.get('status', 'failed')
    passed = multi_file and harness_ok and browser_status == 'passed'
    status = 'not_evaluated' if browser_status == 'not_evaluated' else ('passed' if passed else 'failed')
    total_bytes = sum(p.stat().st_size for p in ws_dir.glob('*') if p.is_file() and p.suffix in {'.html', '.js', '.css'})
    return {
        'evaluated': browser_status != 'not_evaluated',
        'status': status,
        'passed': passed,
        'multi_file': multi_file,
        'harness_ok': harness_ok,
        'harness_output': harness_out,
        'browser': browser,
        'output_bytes': total_bytes,
        'constraint_compliance_pct': 100.0 if passed else (50.0 if (browser_status == 'passed') or harness_ok else 0.0),
    }


def evaluate_task(task_id: str, answer_text: str, ws_dir: Path, fixtures_dir: Path) -> dict[str, Any]:
    try:
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
        return {'evaluated': False, 'passed': False, 'error': f'Unknown task_id: {task_id}'}
    except Exception as exc:
        return {'evaluated': False, 'passed': False, 'error': f'Evaluation exception: {exc}'}
