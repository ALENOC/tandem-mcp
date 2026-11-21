"""Comparative Benchmark Runner for Tandem MCP v3.6.1 (010cbb6).

Compares direct execution, a minimal local harness, and Tandem on frozen
fixtures with independently evaluated quality. CLI and models are configurable.

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
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import evaluate  # noqa: E402
import metrics  # noqa: E402
import orchestrators
from lm_studio_harness import run_bounded  # noqa: E402

BENCHMARKS_DIR = REPO_ROOT / 'benchmarks'
if str(BENCHMARKS_DIR) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS_DIR))
from suite_common import (  # noqa: E402
    read_ledger_entries,
    summarize_local_ledger,
    write_agy_session_settings,
)


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or (HERE / 'configs/suite.json')
    return json.loads(cfg_path.read_text())


def check_runtime(cfg: dict, scenarios: list[str]) -> dict:
    """Fail before launching the suite if its required services are unavailable."""
    cli = cfg['orchestrator'].get('cli', 'agy')
    orchestrators.validate(cfg['orchestrator'])
    if shutil.which(cli) is None:
        raise RuntimeError(f'{cli} CLI is not installed')
    if any(orchestrators.legacy_scenario(s) != 'gemini_direct' for s in scenarios):
        endpoint = cfg['executor']['endpoint'].rstrip('/')
        try:
            with urllib.request.urlopen(f'{endpoint}/models', timeout=5) as response:
                models = json.load(response)
        except Exception as exc:
            raise RuntimeError(f'Cannot reach local executor at {endpoint}: {exc}') from exc
        ids = [item.get('id') for item in models.get('data', [])]
        if cfg['executor']['model_id'] not in ids:
            raise RuntimeError(f'Required executor model {cfg["executor"]["model_id"]} is unavailable; found {ids}')
    return {'ok': True}


def _agy_mcp_state() -> dict[str, bool]:
    out = subprocess.check_output(['agy', 'mcp', 'list'], text=True, timeout=15)
    state = {}
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 3:
            state[parts[0]] = (parts[2] == 'enabled')
    return state


def _set_agy_mcp(enable_tandem: bool) -> None:
    subprocess.run(['agy', 'mcp', 'disable', 'craft-anything'], capture_output=True, timeout=15, check=True)
    action = 'enable' if enable_tandem else 'disable'
    subprocess.run(['agy', 'mcp', action, 'tandem-mcp'], capture_output=True, timeout=15, check=True)


def _restore_agy_mcp(orig: dict[str, bool]) -> None:
    for name, was_enabled in orig.items():
        action = 'enable' if was_enabled else 'disable'
        subprocess.run(['agy', 'mcp', action, name], capture_output=True, timeout=15)


def _prepare_workspace(task: dict[str, Any], scenario: str, fixtures_dir: Path, ws_dir: Path) -> int:
    """Populate an isolated workspace with frozen fixtures for the task. Returns source bytes."""
    scenario = orchestrators.legacy_scenario(scenario)
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


def _build_prompt(task: dict[str, Any], scenario: str, ws_dir: Path, fixtures_dir: Path,
                  timeout: int = 600, executor: dict | None = None) -> str:
    scenario = orchestrators.legacy_scenario(scenario)
    tid = task['id']
    executor = executor or load_config()['executor']
    local_timeout = max(1, timeout - min(30, timeout / 10))
    if orchestrators.legacy_scenario(scenario) == 'gemini_direct':
        if tid == 'reading_readme':
            return f'Working directory: {ws_dir}. Read README.md and answer concisely with exact quotes: {task["question"]}'
        if tid == 'reading_grep_agent':
            return f'Working directory: {ws_dir}. Search agent.py (use grep/rg or targeted line reads-no need to read the whole file) and answer concisely with exact quotes: {task["question"]}'
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
        inner = _build_prompt(task, 'gemini_direct', ws_dir, fixtures_dir, timeout, executor)
        return (
            f'Working directory: {ws_dir}. Delegate the following task to the configured local model using '
            f'`python3 lm_studio_harness.py --workspace "{ws_dir}" --stats-out "{ws_dir}/lm_studio_stats.json" '
            f'--endpoint "{executor["endpoint"]}" --model "{executor["model_id"]}" '
            f'--timeout {int(local_timeout)} --prompt ...` '
            f'(do NOT solve it yourself without calling lm_studio_harness.py). Call it exactly once, wait for its exit, '
            f'and return its final answer or failure. Never return while it is still running or start another copy.\n\nTask:\n{inner}'
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
                f'write_globs={json.dumps(globs)}, verify_commands={json.dumps([task["verify_command"]])}, '
                f'max_seconds={int(local_timeout)}, wait_seconds=30. '
                f'Poll the same job with job_status(wait_seconds=30) until terminal or the {int(local_timeout)}s budget expires; '
                f'then job_stop it if still running. Never start a duplicate job after an MCP timeout. '
                f'Inspect `job_diff` or `job_evidence` and report the result.'
            )
        if tid == 'gen_orbital':
            return (
                f'Working directory: {ws_dir}. Use tandem-mcp `delegate` on workspace `{ws_dir}` using the contract in '
                f'`{ws_dir}/contract_animation.json` (set workspace to `{ws_dir}`, max_seconds={int(local_timeout)}, wait_seconds=30). '
                f'If the job is still running, poll the same job with `job_status(job_id, wait_seconds=30)` '
                f'within a total budget of {int(local_timeout)} seconds; stop it if still running at the deadline. '
                f'Never submit a duplicate delegation after a tool timeout; '
                f'then inspect `job_evidence` and report the result.'
            )
        if tid == 'gen_portal':
            return (
                f'Working directory: {ws_dir}. Use tandem-mcp `delegate_many` on workspace `{ws_dir}` using the tasks in '
                f'`{ws_dir}/contract_scene3d.json` (set workspace to `{ws_dir}`, max_steps=26, max_repairs=3, workers=1, wait_seconds=30). '
                f'Poll the same batch with `job_status(job_id, wait_seconds=30)` within a total budget of '
                f'{int(local_timeout)} seconds; stop it if still running at the deadline. '
                f'Never submit a duplicate batch after a tool timeout; '
                f'then inspect `job_evidence` and report the result.'
            )

    raise ValueError(f'Unknown task/scenario: {tid}/{scenario}')


def _read_tandem_ledger(tandem_home: Path) -> dict[str, Any]:
    entries = read_ledger_entries(tandem_home / 'ledger.jsonl')
    if not entries:
        return {'prompt_tokens': 0, 'completion_tokens': 0, 'seconds': 0.0, 'requests': 0, 'retries': 0, 'repairs': 0, 'bytes_in': 0}
    summary = summarize_local_ledger(entries)
    llm = [r for r in entries if r.get('kind') == 'llm']
    results = [r for r in entries if r.get('kind') == 'result']
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
        'prompt_tokens': summary['local_prompt_tokens'] or 0,
        'completion_tokens': summary['local_completion_tokens'] or 0,
        'seconds': sum(float(r.get('seconds') or 0.0) for r in llm),
        'requests': summary['local_calls'] or 0,
        'retries': summary['retries'],
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
    run_dir: Path | None = None,
) -> dict[str, Any]:
    if timeout <= 0:
        raise ValueError('per-run timeout must be positive')
    ws_dir = Path(tempfile.mkdtemp(prefix=f'cmp-{task["id"]}-{scenario}-r{repeat_idx}-'))
    tandem_home = Path(tempfile.mkdtemp(prefix='cmp-thome-'))
    source_bytes = _prepare_workspace(task, scenario, fixtures_dir, ws_dir)
    prompt = _build_prompt(task, scenario, ws_dir, fixtures_dir, timeout, cfg['executor'])

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
    env['TANDEM_MODEL'] = cfg['executor']['model_id']
    env['TANDEM_TIMEOUT'] = str(min(timeout, 300))

    cmd = orchestrators.command(cfg['orchestrator'], prompt, timeout, scenario, env)
    if cfg['orchestrator'].get('cli', 'agy') == 'agy':
        settings_base = run_dir if run_dir is not None else ws_dir
        session_settings = write_agy_session_settings(
            settings_base / 'settings' / f'{task["id"]}__{scenario}__r{repeat_idx}.settings.json',
            enable_tandem=(orchestrators.legacy_scenario(scenario) == 'gemini_tandem'),
            tandem_env={k: env[k] for k in ('TANDEM_HOME', 'TANDEM_BASE_URL', 'TANDEM_MODEL', 'TANDEM_TIMEOUT') if k in env},
            python_bin=sys.executable,
            repo_root=REPO_ROOT,
        )
        cmd = cmd[:-2] + ['--settings', str(session_settings)] + cmd[-2:]

    t0 = time.perf_counter()
    raw_status = 'FAILED'
    agy_json = None
    raw_out, raw_err = '', ''
    try:
        proc = run_bounded(cmd, cwd=ws_dir, env=env, timeout=timeout)
        wall_s = round(time.perf_counter() - t0, 2)
        raw_out = proc.stdout.strip()
        raw_err = proc.stderr
        agy_json = orchestrators.parse_output(cfg['orchestrator'], raw_out)
        if agy_json and agy_json.get('status'):
            raw_status = metrics.normalize_status(agy_json['status'])
        elif proc.returncode == 0 and agy_json is not None:
            raw_status = 'COMPLETED'
        else:
            raw_status = 'FAILED'
        if proc.returncode != 0 and raw_status == 'COMPLETED':
            raw_status = 'FAILED'
    except subprocess.TimeoutExpired as exc:
        raw_out, raw_err = exc.output or '', exc.stderr or ''
        wall_s = round(time.perf_counter() - t0, 2)
        raw_status = 'TIMEOUT'
        agy_json = {'status': 'TIMEOUT', 'response': '', 'num_turns': None, 'usage': None}
    except KeyboardInterrupt:
        wall_s = round(time.perf_counter() - t0, 2)
        raw_status = 'INTERRUPTED'
        agy_json = {'status': 'INTERRUPTED', 'response': '', 'num_turns': None, 'usage': None}
    except OSError as exc:
        wall_s = round(time.perf_counter() - t0, 2)
        raw_err = str(exc)

    if run_dir is not None:
        log_dir = run_dir / 'logs' / task['id'] / scenario / f'r{repeat_idx}'
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / 'stdout.txt').write_text(raw_out)
        (log_dir / 'stderr.txt').write_text(raw_err)

    conv_id = (agy_json or {}).get('conversation_id')
    answer_text = (agy_json or {}).get('response') or ''
    cloud_usage = metrics.build_cloud_usage_record(
        (agy_json or {}).get('usage'),
        num_turns=(agy_json or {}).get('num_turns'),
        collection_method=orchestrators.collection_method(cfg['orchestrator']),
    )
    identity = (metrics.verify_agy_model_identity(cfg['orchestrator']['model_id'], conv_id)
                if cfg['orchestrator'].get('cli', 'agy') == 'agy' else
                {'requested_model': cfg['orchestrator']['model_id'], 'identity_verified': False,
                 'provenance': 'unavailable', 'reason': 'CLI events do not attest model identity'})

    if orchestrators.legacy_scenario(scenario) == 'gemini_direct':
        local_compute = metrics.build_local_compute_record(0, 0, 0.0, 0, 0, 0, provenance='measured', collection_method='none_direct_cloud')
    elif orchestrators.legacy_scenario(scenario) == 'gemini_lmstudio':
        stats_file = ws_dir / 'lm_studio_stats.json'
        if stats_file.exists():
            st = json.loads(stats_file.read_text())
            if raw_status == 'COMPLETED' and st.get('status') != 'COMPLETED':
                raw_status = 'TIMEOUT' if st.get('status') == 'TIMEOUT' else 'PARTIAL'
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
            if raw_status == 'COMPLETED':
                raw_status = 'PARTIAL'
    else:
        led = _read_tandem_ledger(tandem_home)
        if raw_status == 'COMPLETED' and led['requests'] == 0:
            raw_status = 'PARTIAL'
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
    interactions = (metrics.extract_tool_interactions_from_transcript(conv_id)
                    if cfg['orchestrator'].get('cli', 'agy') == 'agy' else None)
    tool_context = metrics.build_tool_context_record(
        interactions,
        source_bytes=source_bytes,
        collection_method='agy_transcript_tool_calls' if interactions is not None else 'unavailable_no_transcript',
    )

    quality = evaluate.evaluate_task(task['id'], answer_text, ws_dir, fixtures_dir)
    outcome = metrics.classify_outcome(raw_status, quality)

    if task['category'] == 'generation' and run_dir is not None:
        art_dir = run_dir / 'artifacts' / task['id'] / scenario / f'r{repeat_idx}'
        art_dir.mkdir(parents=True, exist_ok=True)
        for fp in ws_dir.iterdir():
            if fp.is_file() and fp.suffix in {'.html', '.js', '.css'} and fp.name not in {'lm_studio_harness.py', 'check_page.js', 'check_engine.js'}:
                shutil.copy2(fp, art_dir / fp.name)

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
        'workspace': str(ws_dir),
        'timeout_seconds': timeout,
        'error_preview': raw_err[-2000:] if raw_status != 'COMPLETED' else '',
        'quota_exhausted': raw_status != 'COMPLETED' and orchestrators.quota_exhausted(raw_out + '\n' + raw_err),
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    env_chk = report.get('environment_check', {})
    orch = report.get('orchestrator', {})
    lines = [
        '# Comparative Benchmark Results - Tandem MCP v3.6.1',
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
        direct_agg = scen_map.get('direct', scen_map.get('gemini_direct', {}))
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

            if orchestrators.legacy_scenario(scen) == 'gemini_direct':
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
        'cloud_tokens_collection': orchestrators.collection_method(cfg['orchestrator']),
        'records': records,
        'aggregates': agg_summary,
    }
    (run_dir / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    (run_dir / 'RESULTS.md').write_text(render_markdown_report(report))


def main():
    ap = argparse.ArgumentParser(description='Comparative benchmark runner for Tandem MCP v3.6.1')
    ap.add_argument('--config', default=str(HERE / 'configs/suite.json'))
    ap.add_argument('--orchestrator-cli', choices=['agy', 'codex'])
    ap.add_argument('--orchestrator-model')
    ap.add_argument('--executor-model')
    ap.add_argument('--task', default='', help='Comma-separated task IDs')
    ap.add_argument('--category', default='all', help='reading, extraction, bugfix, generation, or all')
    ap.add_argument('--scenario', default='all', help='direct, lmstudio, tandem, or all (legacy aliases accepted)')
    ap.add_argument('--repeats', type=int, default=0, help='Override repeat count')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--timeout', type=int, default=0, help='Positive per-run timeout; 0 uses category defaults')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--resume', default='', help='Existing run_id in runs/ to resume')
    ap.add_argument('--allow-dirty-commit', action='store_true')
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    if args.orchestrator_cli:
        cfg['orchestrator']['cli'] = args.orchestrator_cli
    if args.orchestrator_model:
        cfg['orchestrator']['model_id'] = args.orchestrator_model
        cfg['orchestrator']['name'] = args.orchestrator_model
    if args.executor_model:
        cfg['executor']['model_id'] = args.executor_model
    orchestrators.validate(cfg['orchestrator'])
    cfg['scenarios'] = [orchestrators.neutral_scenario(s) for s in cfg['scenarios']]
    if args.timeout < 0 or any(v <= 0 for v in cfg['timeouts_seconds'].values()):
        ap.error('timeouts must be positive (use --timeout 0 for category defaults)')
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

    scenarios = cfg['scenarios'] if args.scenario == 'all' else [orchestrators.neutral_scenario(s.strip()) for s in args.scenario.split(',') if s.strip()]
    if not tasks or not scenarios or set(scenarios) - set(cfg['scenarios']):
        ap.error('select at least one valid task and scenario')

    run_id = args.resume or time.strftime('%Y%m%d-%H%M%S')
    run_dir = HERE / 'runs' / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    results_path = run_dir / 'results.json'
    config_path = run_dir / 'config.json'
    if args.resume and config_path.exists() and json.loads(config_path.read_text()) != cfg:
        ap.error('Cannot resume with a different configuration')
    config_path.write_text(json.dumps(cfg, indent=2) + '\n')
    if not args.dry_run:
        try:
            runtime = check_runtime(cfg, scenarios)
        except RuntimeError as exc:
            (run_dir / 'preflight.json').write_text(json.dumps({'ok': False, 'error': str(exc)}, indent=2) + '\n')
            ap.exit(1, f'Benchmark preflight failed: {exc}\nDiagnostics: {run_dir / "preflight.json"}\n')
        (run_dir / 'preflight.json').write_text(json.dumps(runtime, indent=2) + '\n')

    records: list[dict[str, Any]] = []
    done_keys = set()
    if args.resume and results_path.exists():
        prev = json.loads(results_path.read_text())
        records = prev.get('records', [])
        done_keys = {(r['task_id'], r['scenario'], r['repeat']) for r in records if not r.get('dry_run')}

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
                print(f'[run={run_id}] task={task["id"]} scenario={scen} repeat={rep}/{n_rep}', flush=True)
                rec = run_single(task, scen, rep, cfg, fixtures_dir, t_timeout, dry_run=args.dry_run, run_dir=run_dir)
                quota_attempt = 0
                while rec.get('quota_exhausted'):
                    quota_attempt += 1
                    retry_dir = run_dir / 'quota_retries' / task['id'] / scen / f'r{rep}' / str(time.time_ns())
                    retry_dir.mkdir(parents=True, exist_ok=True)
                    (retry_dir / 'record.json').write_text(json.dumps(rec, indent=2) + '\n')
                    log_dir = run_dir / 'logs' / task['id'] / scen / f'r{rep}'
                    if log_dir.exists():
                        shutil.copytree(log_dir, retry_dir / 'logs')
                    print('Usage quota exhausted; retrying the same attempt in 300 seconds. Ctrl-C stops.', flush=True)
                    for _ in range(5):
                        time.sleep(60)
                    rec = run_single(task, scen, rep, cfg, fixtures_dir, t_timeout, run_dir=run_dir)
                records.append(rec)
                _save_report(run_id, run_dir, cfg, env_check, fixture_check, records)
                print(f'  -> {rec.get("status", "DRY_RUN")} in {rec.get("wall_seconds", 0)}s', flush=True)
                if rec.get('status') == 'INTERRUPTED':
                    raise KeyboardInterrupt

    print(f'Completed run {run_id}. Results: {results_path}')


if __name__ == '__main__':
    main()
