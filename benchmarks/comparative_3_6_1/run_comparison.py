"""Comparative Benchmark Runner for Tandem MCP v3.6.1 (010cbb6).

Compares three scenarios under identical frozen v3.6.1 fixtures and independent
quality evaluation:
  - Scenario A (gemini_direct):   Gemini 4 Hydrogen directly with native tools.
  - Scenario B (gemini_lmstudio): Gemini 4 Hydrogen + qwen3.8-27b@iq3_s via minimal
                                  LM Studio harness (no Tandem features).
  - Scenario C (gemini_tandem):   Gemini 4 Hydrogen + Tandem MCP v3.6.1 + qwen3.8-27b@iq3_s.

Usage:
    python3 benchmarks/comparative_3_6_1/run_comparison.py --dry-run
    python3 benchmarks/comparative_3_6_1/run_comparison.py --category reading --repeats 3
    python3 benchmarks/comparative_3_6_1/run_comparison.py --task reading_grep_agent --repeats 3
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import evaluate  # noqa: E402
import metrics  # noqa: E402


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or (HERE / 'configs/suite.json')
    return json.loads(cfg_path.read_text())


def _agy_mcp_state() -> dict[str, bool]:
    out = subprocess.check_output(['agy', 'mcp', 'list'], text=True, timeout=15)
    state = {}
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 3:
            state[parts[0]] = (parts[2] == 'enabled')
    return state


def _set_agy_mcp(enable_tandem: bool) -> None:
    subprocess.run(['agy', 'mcp', 'disable', 'craft-anything'], capture_output=True, timeout=15)
    action = 'enable' if enable_tandem else 'disable'
    subprocess.run(['agy', 'mcp', action, 'tandem-mcp'], capture_output=True, timeout=15)


def _restore_agy_mcp(orig: dict[str, bool]) -> None:
    for name, was_enabled in orig.items():
        action = 'enable' if was_enabled else 'disable'
        subprocess.run(['agy', 'mcp', action, name], capture_output=True, timeout=15)


def _prepare_workspace(task: dict[str, Any], scenario: str, fixtures_dir: Path, ws_dir: Path) -> int:
    """Populate an isolated workspace with frozen fixtures for the task. Returns source bytes."""
    tid = task['id']
    source_bytes = 0
    if tid == 'reading_readme':
        dst = ws_dir / 'README.md'
        shutil.copy2(fixtures_dir / 'README_v3_6_1.md', dst)
        source_bytes = dst.stat().st_size
    elif tid == 'reading_grep_agent':
        dst = ws_dir / 'agent.py'
        shutil.copy2(fixtures_dir / 'agent_v3_6_1.py', dst)
        source_bytes = dst.stat().st_size
    elif tid == 'reading_package_survey':
        pkg = ws_dir / 'tandem_mcp_pkg'
        shutil.copytree(fixtures_dir / 'tandem_mcp_pkg', pkg)
        source_bytes = sum(p.stat().st_size for p in pkg.glob('*.py'))
    elif tid == 'reading_git_history':
        dst = ws_dir / 'git_log_30_stat.txt'
        shutil.copy2(fixtures_dir / 'git_log_30_stat.txt', dst)
        source_bytes = dst.stat().st_size
    elif tid == 'extraction_manifest':
        dst = ws_dir / 'pyproject.toml'
        shutil.copy2(fixtures_dir / 'pyproject_v3_6_1.toml', dst)
        source_bytes = dst.stat().st_size
    elif tid == 'bugfix_micro':
        for f in (fixtures_dir / 'bugfix_micro').iterdir():
            shutil.copy2(f, ws_dir / f.name)
        source_bytes = sum(p.stat().st_size for p in ws_dir.glob('*.py'))
    elif tid == 'bugfix_multifile':
        for f in (fixtures_dir / 'bugfix_multifile').iterdir():
            shutil.copy2(f, ws_dir / f.name)
        source_bytes = sum(p.stat().st_size for p in ws_dir.glob('*.py'))
    elif tid == 'gen_orbital':
        shutil.copy2(fixtures_dir / 'contracts/check_page.js', ws_dir / 'check_page.js')
        shutil.copy2(fixtures_dir / 'contracts/animation.json', ws_dir / 'contract_animation.json')
        source_bytes = (fixtures_dir / 'prompts/orbital_prompt.txt').stat().st_size
    elif tid == 'gen_portal':
        shutil.copy2(fixtures_dir / 'contracts/check_engine.js', ws_dir / 'check_engine.js')
        shutil.copy2(fixtures_dir / 'contracts/scene3d.json', ws_dir / 'contract_scene3d.json')
        source_bytes = (fixtures_dir / 'prompts/portal_prompt.txt').stat().st_size

    if scenario == 'gemini_lmstudio':
        shutil.copy2(HERE / 'lm_studio_harness.py', ws_dir / 'lm_studio_harness.py')
    return source_bytes


def _build_prompt(task: dict[str, Any], scenario: str, ws_dir: Path, fixtures_dir: Path) -> str:
    tid = task['id']
    if scenario == 'gemini_direct':
        if tid == 'reading_readme':
            return f'Working directory: {ws_dir}. Read README.md and answer concisely with exact quotes: {task["question"]}'
        if tid == 'reading_grep_agent':
            return f'Working directory: {ws_dir}. Search agent.py (use grep/rg or targeted line reads—no need to read the whole file) and answer concisely with exact quotes: {task["question"]}'
        if tid == 'reading_package_survey':
            return f'Working directory: {ws_dir}. Inspect all 8 Python files in tandem_mcp_pkg/ and state the main responsibility of each module concisely.'
        if tid == 'reading_git_history':
            return f'Working directory: {ws_dir}. Analyze git_log_30_stat.txt and answer concisely: {task["question"]}'
        if tid == 'extraction_manifest':
            return (
                f'Working directory: {ws_dir}. Read pyproject.toml and return ONLY a valid JSON object matching '
                f'{json.dumps(evaluate.MANIFEST_SCHEMA)}: {task["question"]}'
            )
        if tid in {'bugfix_micro', 'bugfix_multifile'}:
            return f'Working directory: {ws_dir}. {task["goal"]} Run `{task["verify_command"]}` to verify.'
        if tid == 'gen_orbital':
            goal = (fixtures_dir / 'prompts/orbital_prompt.txt').read_text().strip()
            return f'Working directory: {ws_dir}. {goal}\nA verification harness check_page.js is in the workspace; run `node check_page.js` after writing index.html.'
        if tid == 'gen_portal':
            goal = (fixtures_dir / 'prompts/portal_prompt.txt').read_text().strip()
            return f'Working directory: {ws_dir}. {goal}\nCreate index.html (or index.html + scene.js + engine3d.js + app.js) in {ws_dir}.'

    if scenario == 'gemini_lmstudio':
        inner = _build_prompt(task, 'gemini_direct', ws_dir, fixtures_dir)
        return (
            f'Working directory: {ws_dir}. Delegate the following task to the local Qwen model using '
            f'`python3 lm_studio_harness.py --workspace "{ws_dir}" --stats-out "{ws_dir}/lm_studio_stats.json" --prompt ...` '
            f'(do NOT solve it yourself without calling lm_studio_harness.py). Return the final answer or verification result.\n\nTask:\n{inner}'
        )

    if scenario == 'gemini_tandem':
        if tid == 'reading_readme':
            return f'Working directory: {ws_dir}. Use tandem-mcp `digest_file` on `{ws_dir}/README.md` to answer: {task["question"]}'
        if tid == 'reading_grep_agent':
            return f'Working directory: {ws_dir}. Use tandem-mcp `digest_file` with grep="too large" on `{ws_dir}/agent.py` to answer: {task["question"]}'
        if tid == 'reading_package_survey':
            return f'Working directory: {ws_dir}. Use tandem-mcp `digest_many` on `{ws_dir}/tandem_mcp_pkg` with glob="*.py" to answer: What is the main responsibility of this module?'
        if tid == 'reading_git_history':
            return f'Working directory: {ws_dir}. Use tandem-mcp `digest_command` with command="cat git_log_30_stat.txt" and cwd="{ws_dir}" to answer: {task["question"]}'
        if tid == 'extraction_manifest':
            return (
                f'Working directory: {ws_dir}. Use tandem-mcp `extract_from_file` on `{ws_dir}/pyproject.toml` with schema '
                f'`{json.dumps(evaluate.MANIFEST_SCHEMA)}` and instructions="{task["question"]}". Return ONLY the extracted JSON.'
            )
        if tid in {'bugfix_micro', 'bugfix_multifile'}:
            globs = ['math_utils.py'] if tid == 'bugfix_micro' else ['config_loader.py']
            return (
                f'Working directory: {ws_dir}. Use tandem-mcp `delegate` on workspace `{ws_dir}` with goal="{task["goal"]}", '
                f'write_globs={json.dumps(globs)}, verify_commands={json.dumps([task["verify_command"]])}, wait_seconds=300. '
                f'Inspect `job_diff` or `job_evidence` if needed and report the result.'
            )
        if tid == 'gen_orbital':
            return (
                f'Working directory: {ws_dir}. Use tandem-mcp `delegate` on workspace `{ws_dir}` using the contract in '
                f'`{ws_dir}/contract_animation.json` (set workspace to `{ws_dir}`). Inspect `job_evidence` and report.'
            )
        if tid == 'gen_portal':
            return (
                f'Working directory: {ws_dir}. Use tandem-mcp `delegate_many` on workspace `{ws_dir}` using the tasks in '
                f'`{ws_dir}/contract_scene3d.json` (set workspace to `{ws_dir}`). Inspect `job_evidence` and report.'
            )

    raise ValueError(f'Unknown task/scenario: {tid}/{scenario}')


def _read_tandem_ledger(tandem_home: Path) -> dict[str, Any]:
    ledger = tandem_home / 'ledger.jsonl'
    if not ledger.exists():
        return {'prompt_tokens': 0, 'completion_tokens': 0, 'seconds': 0.0, 'requests': 0, 'retries': 0, 'repairs': 0, 'bytes_in': 0}
    rows = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    llm = [r for r in rows if r.get('kind') == 'llm']
    retries = sum(1 for r in rows if r.get('kind') == 'retry')
    results = [r for r in rows if r.get('kind') == 'result']
    repairs = 0
    jobs_dir = tandem_home / 'jobs'
    if jobs_dir.exists():
        for jf in jobs_dir.glob('*.json'):
            try:
                jd = json.loads(jf.read_text())
                repairs += int(jd.get('repairs') or 0)
            except Exception:
                pass
    return {
        'prompt_tokens': sum(int(r.get('prompt_tokens') or 0) for r in llm),
        'completion_tokens': sum(int(r.get('completion_tokens') or 0) for r in llm),
        'seconds': sum(float(r.get('seconds') or 0.0) for r in llm),
        'requests': len(llm),
        'retries': retries,
        'repairs': repairs,
        'bytes_in': sum(int(r.get('bytes_in') or 0) for r in results),
    }


def run_single(
    task: dict[str, Any],
    scenario: str,
    repeat_idx: int,
    cfg: dict[str, Any],
    fixtures_dir: Path,
    timeout: int,
    dry_run: bool = False,
) -> dict[str, Any]:
    ws_dir = Path(tempfile.mkdtemp(prefix=f'cmp-{task["id"]}-{scenario}-r{repeat_idx}-'))
    tandem_home = Path(tempfile.mkdtemp(prefix='cmp-thome-'))
    source_bytes = _prepare_workspace(task, scenario, fixtures_dir, ws_dir)
    prompt = _build_prompt(task, scenario, ws_dir, fixtures_dir)

    if dry_run:
        return {
            'task_id': task['id'],
            'category': task['category'],
            'scenario': scenario,
            'repeat': repeat_idx,
            'dry_run': True,
            'source_bytes': source_bytes,
            'workspace': str(ws_dir),
            'prompt_chars': len(prompt),
        }

    env = os.environ.copy()
    env['TANDEM_HOME'] = str(tandem_home)
    env['TANDEM_BASE_URL'] = cfg['executor']['endpoint']

    cmd = [
        'agy',
        '--model', cfg['orchestrator']['model_id'],
        '--output-format', 'json',
        '--dangerously-skip-permissions',
        '--new-project',
        '-p', prompt,
    ]

    t0 = time.perf_counter()
    raw_status = 'FAILED'
    agy_json = None
    try:
        proc = subprocess.run(cmd, cwd=ws_dir, env=env, capture_output=True, text=True, timeout=timeout)
        wall_s = round(time.perf_counter() - t0, 2)
        raw_out = proc.stdout.strip()
        for line in reversed(raw_out.splitlines()):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    agy_json = json.loads(line)
                    break
                except Exception:
                    pass
        if agy_json and agy_json.get('status'):
            raw_status = metrics.normalize_status(agy_json['status'])
        elif proc.returncode == 0 and agy_json is not None:
            raw_status = 'COMPLETED'
        else:
            raw_status = 'FAILED'
    except subprocess.TimeoutExpired:
        wall_s = round(time.perf_counter() - t0, 2)
        raw_status = 'TIMEOUT'
        agy_json = {'status': 'TIMEOUT', 'response': '', 'num_turns': None, 'usage': None}
    except KeyboardInterrupt:
        wall_s = round(time.perf_counter() - t0, 2)
        raw_status = 'INTERRUPTED'
        agy_json = {'status': 'INTERRUPTED', 'response': '', 'num_turns': None, 'usage': None}

    conv_id = (agy_json or {}).get('conversation_id')
    answer_text = (agy_json or {}).get('response') or ''
    cloud_usage = metrics.build_cloud_usage_record(
        (agy_json or {}).get('usage'),
        num_turns=(agy_json or {}).get('num_turns'),
        collection_method='agy_cli_json_usage',
    )
    identity = metrics.verify_agy_model_identity(cfg['orchestrator']['model_id'], conv_id)

    if scenario == 'gemini_direct':
        local_compute = metrics.build_local_compute_record(0, 0, 0.0, 0, 0, 0, provenance='measured', collection_method='none_direct_cloud')
    elif scenario == 'gemini_lmstudio':
        stats_file = ws_dir / 'lm_studio_stats.json'
        if stats_file.exists():
            st = json.loads(stats_file.read_text())
            local_compute = metrics.build_local_compute_record(
                st.get('local_prompt_tokens', 0),
                st.get('local_completion_tokens', 0),
                st.get('local_inference_seconds', 0.0),
                st.get('local_requests', 0),
                st.get('retry_attempts', 0),
                0,
                provenance='measured',
                collection_method='lm_studio_harness_usage',
            )
        else:
            local_compute = metrics.build_local_compute_record(provenance='unavailable', collection_method='lm_studio_stats_missing')
    else:
        led = _read_tandem_ledger(tandem_home)
        local_compute = metrics.build_local_compute_record(
            led['prompt_tokens'],
            led['completion_tokens'],
            led['seconds'],
            led['requests'],
            led['retries'],
            led['repairs'],
            provenance='measured',
            collection_method='tandem_ledger_and_jobs',
        )

    # Measure actual tool payloads from agy transcript (never from final assistant response)
    interactions = metrics.extract_tool_interactions_from_transcript(conv_id)
    tool_context = metrics.build_tool_context_record(
        interactions,
        source_bytes=source_bytes,
        collection_method='agy_transcript_tool_calls' if interactions is not None else 'unavailable_no_transcript',
    )

    quality = evaluate.evaluate_task(task['id'], answer_text, ws_dir, fixtures_dir)
    outcome = metrics.classify_outcome(raw_status, quality)

    return {
        'task_id': task['id'],
        'category': task['category'],
        'scenario': scenario,
        'repeat': repeat_idx,
        'status': outcome['execution_status'],
        'outcome': outcome,
        'conversation_id': conv_id,
        'model_identity': identity,
        'wall_seconds': wall_s,
        'cloud_usage': cloud_usage,
        'local_compute': local_compute,
        'tool_context': tool_context,
        'quality': quality,
        'answer_preview': answer_text[:400],
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    env_chk = report.get('environment_check', {})
    orch = report.get('orchestrator', {})
    lines = [
        '# Comparative Benchmark Results — Tandem MCP v3.6.1',
        '',
        f'- **Run ID**: `{report["run_id"]}`',
        f'- **Date**: {report["date"]}',
        f'- **Tandem Commit**: `{env_chk.get("commit", {}).get("actual_commit", report.get("version_check", {}).get("actual_commit", "unknown"))}` '
        f'(clean=`{env_chk.get("git_clean", "N/A")}`, version=`{env_chk.get("imported_version", report.get("tandem_version"))}`)',
        f'- **Orchestrator**: requested=`{orch.get("model_id")}`, verified_runs=`{orch.get("verified_runs", 0)}/{orch.get("total_runs", 0)}`',
        f'- **Local executor**: `{report["executor"]["model_id"]}` via {report["executor"]["server"]} (`{report["executor"]["endpoint"]}`)',
        f'- **Cloud token collection**: `{report["cloud_tokens_collection"]}` (thinking included in `output_tokens`, not double-counted; cached tokens separate)',
        '',
        '## Aggregated Comparison',
        '',
        '| Task | Scenario | n | Completed | E2E Success | Artifact Valid | Timeouts | Cloud Tokens / Attempt (mean) | Usage Coverage | Cloud Tokens / Success | Cloud Savings vs Direct | Median Time (s) | Local Tokens (mean) |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |',
    ]
    agg = report.get('aggregates', {})
    for task_id, scen_map in agg.items():
        direct_agg = scen_map.get('gemini_direct', {})
        direct_tok = direct_agg.get('mean_cloud_tokens_per_attempt')
        direct_cov = direct_agg.get('usage_coverage_pct', 0.0)
        for scen, st in scen_map.items():
            mean_att = st.get('mean_cloud_tokens_per_attempt')
            cov = st.get('usage_coverage_pct', 0.0)
            per_succ = st.get('cloud_tokens_per_success')
            if per_succ is not None and not st.get('cloud_tokens_per_success_complete', False):
                per_succ_str = f'{per_succ} (incomplete)'
            elif per_succ is not None:
                per_succ_str = str(per_succ)
            else:
                per_succ_str = 'N/A'

            if scen == 'gemini_direct':
                sav_str = 'baseline'
            else:
                sav = metrics.compute_cloud_token_savings(
                    direct_tok, mean_att,
                    direct_status='measured' if direct_tok else 'unavailable',
                    candidate_status='measured' if mean_att else 'unavailable',
                    direct_coverage_pct=direct_cov,
                    candidate_coverage_pct=cov,
                )
                if sav['cloud_savings_pct'] is None:
                    sav_str = 'N/A'
                elif not sav['coverage_comparable']:
                    sav_str = f'{sav["cloud_savings_pct"]:+.1f}% (incomplete)'
                else:
                    sav_str = f'{sav["cloud_savings_pct"]:+.1f}%'

            lines.append(
                f'| `{task_id}` | `{scen}` | {st.get("n", 0)} | '
                f'{st.get("completed_executions", 0)} | '
                f'{st.get("end_to_end_success_rate", 0.0)}% | '
                f'{st.get("artifact_pass_rate", 0.0)}% | '
                f'{st.get("timeouts", 0)} | '
                f'{mean_att if mean_att is not None else "N/A"} | '
                f'{cov}% | '
                f'{per_succ_str} | '
                f'{sav_str} | '
                f'{st.get("median_seconds") if st.get("median_seconds") is not None else "N/A"} | '
                f'{st.get("local_tokens_mean_per_attempt") if st.get("local_tokens_mean_per_attempt") is not None else "N/A"} |'
            )
    lines.append('')
    return '\n'.join(lines)


def _save_report(run_id, run_dir, cfg, env_check, fixture_check, records):
    agg: dict[str, dict[str, Any]] = {}
    verified_runs = 0
    total_runs = 0
    for r in records:
        if r.get('dry_run'):
            continue
        total_runs += 1
        if r.get('model_identity', {}).get('identity_verified'):
            verified_runs += 1
        agg.setdefault(r['task_id'], {}).setdefault(r['scenario'], []).append(r)

    agg_summary = {
        tid: {scen: metrics.aggregate_runs(recs) for scen, recs in scens.items()}
        for tid, scens in agg.items()
    }
    report = {
        'run_id': run_id,
        'date': time.strftime('%Y-%m-%d %H:%M:%S'),
        'tandem_version': cfg['tandem_version'],
        'environment_check': env_check,
        'fixture_check': fixture_check,
        'orchestrator': {
            'name': cfg['orchestrator']['name'],
            'model_id': cfg['orchestrator']['model_id'],
            'identity_verified': (total_runs > 0 and verified_runs == total_runs),
            'verified_runs': verified_runs,
            'total_runs': total_runs,
        },
        'executor': cfg['executor'],
        'cloud_tokens_collection': 'agy_cli_json_usage',
        'records': records,
        'aggregates': agg_summary,
    }
    (run_dir / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    (run_dir / 'RESULTS.md').write_text(render_markdown_report(report))


def main():
    ap = argparse.ArgumentParser(description='Comparative benchmark runner for Tandem MCP v3.6.1')
    ap.add_argument('--config', default=str(HERE / 'configs/suite.json'))
    ap.add_argument('--task', default='', help='Comma-separated task IDs')
    ap.add_argument('--category', default='all', help='reading, extraction, bugfix, generation, or all')
    ap.add_argument('--scenario', default='all', help='gemini_direct, gemini_lmstudio, gemini_tandem, or all')
    ap.add_argument('--repeats', type=int, default=0, help='Override repeat count')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--timeout', type=int, default=0, help='Override per-run timeout in seconds')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--resume', default='', help='Existing run_id in runs/ to resume')
    ap.add_argument('--allow-dirty-commit', action='store_true')
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    fixtures_dir = HERE / 'fixtures'
    tandem_under_test = Path('/home/ale/tools/tandem-mcp')
    target_repo = tandem_under_test if tandem_under_test.exists() else REPO_ROOT
    env_check = metrics.verify_tandem_environment(
        target_repo,
        expected_commit=cfg['expected_commit'],
        expected_version=cfg['tandem_version'],
        allow_override=args.allow_dirty_commit,
    )
    fixture_check = metrics.verify_fixtures_manifest(fixtures_dir)

    tasks = cfg['tasks']
    if args.task:
        wanted = {t.strip() for t in args.task.split(',') if t.strip()}
        tasks = [t for t in tasks if t['id'] in wanted]
    if args.category != 'all':
        tasks = [t for t in tasks if t['category'] == args.category]

    scenarios = cfg['scenarios'] if args.scenario == 'all' else [s.strip() for s in args.scenario.split(',') if s.strip()]

    run_id = args.resume or time.strftime('%Y%m%d-%H%M%S')
    run_dir = HERE / 'runs' / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    results_path = run_dir / 'results.json'

    records: list[dict[str, Any]] = []
    done_keys = set()
    if args.resume and results_path.exists():
        prev = json.loads(results_path.read_text())
        records = prev.get('records', [])
        done_keys = {(r['task_id'], r['scenario'], r['repeat']) for r in records if not r.get('dry_run')}

    orig_mcp = None if args.dry_run else _agy_mcp_state()
    try:
        for task in tasks:
            n_rep = args.repeats if args.repeats > 0 else cfg['default_repeats'][task['category']]
            t_timeout = args.timeout if args.timeout > 0 else cfg['timeouts_seconds'][task['category']]
            for rep in range(1, n_rep + 1):
                order = list(scenarios)
                if len(order) > 1:
                    shift = (rep - 1) % len(order)
                    order = order[shift:] + order[:shift]
                for scen in order:
                    if (task['id'], scen, rep) in done_keys:
                        continue
                    if not args.dry_run:
                        _set_agy_mcp(enable_tandem=(scen == 'gemini_tandem'))
                    print(f'[run={run_id}] task={task["id"]} scenario={scen} repeat={rep}/{n_rep}', flush=True)
                    rec = run_single(task, scen, rep, cfg, fixtures_dir, t_timeout, dry_run=args.dry_run)
                    records.append(rec)
                    _save_report(run_id, run_dir, cfg, env_check, fixture_check, records)
    finally:
        if orig_mcp is not None:
            _restore_agy_mcp(orig_mcp)

    print(f'Completed run {run_id}. Results: {results_path}')


if __name__ == '__main__':
    main()
