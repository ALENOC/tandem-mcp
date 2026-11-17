"""Metrics, provenance, execution status, model identity, and environment integrity.

Separates:
  1. Execution Completion vs Artifact Quality vs End-to-End Success
  2. Cloud Tokens Per Attempt (all measured runs) vs Cloud Tokens Per Successful Result
  3. Source Reduction vs Tool Context Transferred vs Measured Cloud Token Usage
  4. Local Compute Cost (LM Studio / Tandem ledger)
  5. Independent Model Identity & Tandem v3.6.1 Environment Integrity
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

CHARS_PER_TOKEN = 3.6
VALID_PROVENANCE = {'measured', 'estimated', 'derived', 'unavailable'}
VALID_STATUSES = {'COMPLETED', 'FAILED', 'TIMEOUT', 'INTERRUPTED', 'PARTIAL', 'EVALUATION_ERROR'}

# Backward-compatibility mapping for legacy status strings
LEGACY_STATUS_MAP = {
    'SUCCESS': 'COMPLETED',
    'ERROR': 'FAILED',
}


def normalize_status(raw_status: str | None) -> str:
    if not raw_status:
        return 'FAILED'
    up = str(raw_status).strip().upper()
    up = LEGACY_STATUS_MAP.get(up, up)
    return up if up in VALID_STATUSES else 'FAILED'


def classify_outcome(execution_status: str | None, quality_result: dict[str, Any] | None) -> dict[str, Any]:
    """Separate Artifact Quality, Execution Completion, and End-to-End Success.

    end_to_end_success = execution_completed AND artifact_valid.
    A TIMEOUT with a valid artifact yields:
      - artifact_valid: True
      - execution_completed: False
      - end_to_end_success: False
    """
    status = normalize_status(execution_status)
    execution_completed = (status == 'COMPLETED')
    if quality_result is None or quality_result.get('evaluated') is False:
        artifact_valid = False
        if status == 'COMPLETED':
            status = 'EVALUATION_ERROR'
            execution_completed = False
    else:
        artifact_valid = bool(quality_result.get('passed') is True)
    end_to_end_success = execution_completed and artifact_valid
    return {
        'execution_status': status,
        'execution_completed': execution_completed,
        'artifact_valid': artifact_valid,
        'end_to_end_success': end_to_end_success,
    }


def est_tokens(n_chars: int, chars_per_token: float = CHARS_PER_TOKEN) -> int:
    """Estimate token count from character/byte count (always labeled 'estimated')."""
    if n_chars <= 0:
        return 0
    return round(n_chars / chars_per_token)


def compute_source_reduction(
    input_source_bytes: int,
    summarized_output_bytes: int | None,
    chars_per_token: float = CHARS_PER_TOKEN,
    collection_method: str = 'tool_output_bytes_vs_source_bytes',
) -> dict[str, Any]:
    """Compute Source Reduction (bytes avoided vs full source).

    Must NOT be derived from the final assistant response. If summarized_output_bytes
    is None (e.g. tool output was not intercepted), returns 'unavailable'.
    Never clamps negative values to zero.
    """
    if input_source_bytes <= 0 or summarized_output_bytes is None:
        return {
            'input_source_bytes': input_source_bytes,
            'summarized_output_bytes': summarized_output_bytes,
            'source_reduction_pct': None,
            'est_tokens_saved': None,
            'provenance': 'unavailable',
            'collection_method': collection_method,
        }
    diff = input_source_bytes - summarized_output_bytes
    pct = round(100.0 * diff / input_source_bytes, 1)
    saved_tok_est = est_tokens(diff, chars_per_token) if diff >= 0 else -est_tokens(-diff, chars_per_token)
    return {
        'input_source_bytes': input_source_bytes,
        'summarized_output_bytes': summarized_output_bytes,
        'source_reduction_pct': pct,
        'est_tokens_saved': saved_tok_est,
        'provenance': 'derived',
        'est_tokens_provenance': 'estimated',
        'collection_method': collection_method,
    }


def build_tool_context_record(
    interactions: list[dict[str, Any]] | None,
    source_bytes: int = 0,
    collection_method: str = 'mcp_stdio_proxy',
) -> dict[str, Any]:
    """Record actual tool payloads transferred between orchestrator and tools."""
    if interactions is None:
        return {
            'tool_call_count': None,
            'total_request_bytes': None,
            'total_response_bytes': None,
            'truncated_calls': None,
            'interactions': [],
            'source_reduction': compute_source_reduction(source_bytes, None, collection_method=collection_method),
            'provenance': 'unavailable',
            'collection_method': collection_method,
        }
    req_b = sum(int(x.get('request_bytes') or 0) for x in interactions)
    resp_b = sum(int(x.get('response_bytes') or 0) for x in interactions)
    trunc = sum(1 for x in interactions if x.get('truncated'))
    return {
        'tool_call_count': len(interactions),
        'total_request_bytes': req_b,
        'total_response_bytes': resp_b,
        'truncated_calls': trunc,
        'interactions': interactions,
        'source_reduction': compute_source_reduction(source_bytes, resp_b, collection_method=collection_method),
        'provenance': 'measured',
        'collection_method': collection_method,
    }


def extract_tool_interactions_from_transcript(
    conversation_id: str | None,
    brain_root: Path | None = None,
) -> list[dict[str, Any]] | None:
    """Extract actual tool call request/response byte counts from agy transcript_full.jsonl."""
    if not conversation_id:
        return None
    base = brain_root or (Path.home() / '.gemini/antigravity-cli/brain')
    tpath = base / conversation_id / '.system_generated/logs/transcript_full.jsonl'
    if not tpath.exists():
        tpath = base / conversation_id / '.system_generated/logs/transcript.jsonl'
    if not tpath.exists():
        return None

    interactions: list[dict[str, Any]] = []
    pending_calls: list[dict[str, Any]] = []
    for line in tpath.read_text(errors='replace').splitlines():
        if not line.strip():
            continue
        try:
            step = json.loads(line)
        except Exception:
            continue
        stype = step.get('type')
        if stype == 'PLANNER_RESPONSE' and step.get('tool_calls'):
            for tc in step['tool_calls']:
                name = tc.get('name', 'unknown')
                args = tc.get('args') or {}
                if name == 'call_mcp_tool' and isinstance(args, dict) and args.get('ToolName'):
                    name = f"mcp:{args.get('ServerName', 'mcp')}:{args['ToolName']}"
                req_b = len(json.dumps(args).encode('utf-8', errors='replace'))
                pending_calls.append({'tool_name': name, 'request_bytes': req_b})
        elif stype in {'GENERIC', 'SYSTEM_MESSAGE'} and pending_calls:
            call_info = pending_calls.pop(0)
            content = str(step.get('content') or '')
            resp_b = len(content.encode('utf-8', errors='replace'))
            low = content.lower()
            truncated = ('truncated' in low) or ('omitted' in low)
            interactions.append({
                'tool_name': call_info['tool_name'],
                'request_bytes': call_info['request_bytes'],
                'response_bytes': resp_b,
                'truncated': truncated,
            })
    return interactions


def compute_cloud_token_savings(
    direct_cloud_tokens: float | int | None,
    candidate_cloud_tokens: float | int | None,
    direct_status: str = 'measured',
    candidate_status: str = 'measured',
    direct_coverage_pct: float = 100.0,
    candidate_coverage_pct: float = 100.0,
    collection_method: str = 'agy_cli_json_usage',
) -> dict[str, Any]:
    """Compute Actual Cloud Token Savings = (Direct - Candidate) / Direct * 100.

    - Never clamps negative savings to 0.
    - Returns None ('N/A') when either baseline or candidate is unavailable or <= 0.
    - Marks coverage_comparable=False if either side has <100% usage coverage.
    """
    if (
        direct_status != 'measured'
        or candidate_status != 'measured'
        or direct_cloud_tokens is None
        or candidate_cloud_tokens is None
        or direct_cloud_tokens <= 0
    ):
        return {
            'direct_cloud_tokens': direct_cloud_tokens,
            'candidate_cloud_tokens': candidate_cloud_tokens,
            'cloud_tokens_saved': None,
            'cloud_savings_pct': None,
            'coverage_comparable': False,
            'status': 'unavailable',
            'provenance': 'unavailable',
            'collection_method': collection_method,
        }
    diff = direct_cloud_tokens - candidate_cloud_tokens
    pct = round(100.0 * diff / direct_cloud_tokens, 1)
    comparable = (direct_coverage_pct == 100.0 and candidate_coverage_pct == 100.0)
    return {
        'direct_cloud_tokens': direct_cloud_tokens,
        'candidate_cloud_tokens': candidate_cloud_tokens,
        'cloud_tokens_saved': round(diff, 1),
        'cloud_savings_pct': pct,
        'coverage_comparable': comparable,
        'status': 'measured' if comparable else 'incomplete',
        'provenance': 'measured',
        'collection_method': collection_method,
    }


def build_cloud_usage_record(
    raw_usage: dict[str, Any] | None,
    num_turns: int | None = None,
    collection_method: str = 'agy_cli_json_usage',
) -> dict[str, Any]:
    """Normalize provider cloud token usage without double-counting thinking tokens.

    In Antigravity CLI (`agy --output-format json`), `total_tokens` equals
    `input_tokens + output_tokens`, where `thinking_tokens` is already included
    inside `output_tokens` and `cache_read_tokens` is reported separately.
    """
    if not raw_usage or not isinstance(raw_usage, dict):
        return {
            'cloud_input_tokens': None,
            'cloud_output_tokens': None,
            'cloud_reasoning_tokens': None,
            'cloud_cached_tokens': None,
            'cloud_total_tokens': None,
            'cloud_calls': num_turns,
            'thinking_included_in_output': True,
            'cloud_tokens_status': 'unavailable',
            'provenance': 'unavailable',
            'collection_method': collection_method,
        }
    inp = raw_usage.get('input_tokens')
    out = raw_usage.get('output_tokens')
    think = raw_usage.get('thinking_tokens')
    cached = raw_usage.get('cache_read_tokens')
    total = raw_usage.get('total_tokens')
    if total is None and inp is not None and out is not None:
        # Never add thinking_tokens on top of output_tokens
        total = inp + out
    status = 'measured' if (inp is not None and out is not None and total is not None) else 'unavailable'
    return {
        'cloud_input_tokens': inp,
        'cloud_output_tokens': out,
        'cloud_reasoning_tokens': think,
        'cloud_cached_tokens': cached,
        'cloud_total_tokens': total,
        'cloud_calls': num_turns,
        'thinking_included_in_output': True,
        'cloud_tokens_status': status,
        'provenance': status,
        'collection_method': collection_method,
    }


def build_local_compute_record(
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    inference_seconds: float = 0.0,
    requests: int = 0,
    retries: int = 0,
    repairs: int = 0,
    provenance: str = 'measured',
    collection_method: str = 'lm_studio_usage',
) -> dict[str, Any]:
    """Normalize local executor compute cost."""
    total = prompt_tokens + completion_tokens
    tps = round(completion_tokens / inference_seconds, 1) if inference_seconds > 0 and completion_tokens > 0 else 0.0
    return {
        'local_prompt_tokens': prompt_tokens,
        'local_completion_tokens': completion_tokens,
        'local_total_tokens': total,
        'local_inference_seconds': round(inference_seconds, 2),
        'local_tps': tps,
        'local_requests': requests,
        'retry_attempts': retries,
        'repair_attempts': repairs,
        'provenance': provenance if provenance in VALID_PROVENANCE else 'unavailable',
        'collection_method': collection_method,
    }


def verify_agy_model_identity(
    requested_model: str,
    conversation_id: str | None,
    brain_root: Path | None = None,
) -> dict[str, Any]:
    """Independently verify the provider-reported model ID from Antigravity transcript logs.

    Never marks identity_verified=True solely from the requested model ID.
    """
    base = brain_root or (Path.home() / '.gemini/antigravity-cli/brain')
    if not conversation_id:
        return {
            'requested_model_id': requested_model,
            'provider_reported_model_id': None,
            'verification_method': 'agy_transcript_jsonl',
            'identity_verified': False,
            'limitation': 'No conversation_id returned (e.g. timeout or CLI error); model identity cannot be verified.',
        }
    transcript = base / conversation_id / '.system_generated/logs/transcript.jsonl'
    if not transcript.exists():
        return {
            'requested_model_id': requested_model,
            'provider_reported_model_id': None,
            'verification_method': 'agy_transcript_jsonl',
            'identity_verified': False,
            'limitation': f'Transcript not found at {transcript}; provider model ID unavailable.',
        }
    reported = None
    for line in transcript.read_text(errors='replace').splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if row.get('model'):
            reported = str(row['model'])
            break
    if not reported:
        return {
            'requested_model_id': requested_model,
            'provider_reported_model_id': None,
            'verification_method': 'agy_transcript_jsonl',
            'identity_verified': False,
            'limitation': 'Transcript contained no provider-reported model field.',
        }
    matches = (reported == requested_model)
    return {
        'requested_model_id': requested_model,
        'provider_reported_model_id': reported,
        'verification_method': 'agy_transcript_jsonl',
        'identity_verified': matches,
        'limitation': None if matches else f'Requested {requested_model} but provider reported {reported}.',
    }


def verify_git_commit(repo_root: Path, expected_commit: str = '010cbb6', allow_override: bool = False) -> dict[str, Any]:
    """Verify the repository or worktree commit matches expected_commit (010cbb6)."""
    actual = subprocess.check_output(['git', 'rev-parse', '--short=7', 'HEAD'], cwd=repo_root, text=True).strip()
    matches = actual.startswith(expected_commit) or expected_commit.startswith(actual)
    if not matches and not allow_override:
        raise RuntimeError(f'Commit mismatch: expected {expected_commit}, got {actual}. Use --allow-dirty-commit to override.')
    return {
        'expected_commit': expected_commit,
        'actual_commit': actual,
        'matches': matches,
        'overridden': (not matches) and allow_override,
    }


def verify_tandem_environment(
    tandem_dir: Path,
    expected_commit: str = '010cbb6',
    expected_version: str = '3.6.1',
    allow_override: bool = False,
) -> dict[str, Any]:
    """Verify Tandem commit, package version, imported path, git clean status, and source hashes."""
    commit_info = verify_git_commit(tandem_dir, expected_commit=expected_commit, allow_override=allow_override)
    dirty_out = subprocess.check_output(['git', 'status', '--porcelain'], cwd=tandem_dir, text=True).strip()
    is_clean = (dirty_out == '')
    if not is_clean and not allow_override:
        raise RuntimeError(f'Tandem source tree at {tandem_dir} has uncommitted changes:\n{dirty_out}')

    pkg_dir = tandem_dir / 'tandem_mcp'
    source_hashes = {}
    for pyf in sorted(pkg_dir.glob('*.py')):
        source_hashes[pyf.name] = hashlib.sha256(pyf.read_bytes()).hexdigest()

    # Verify actual imported package path & __version__ using subprocess with tandem_dir on PYTHONPATH
    env = os.environ.copy()
    venv_site = tandem_dir / '.venv/lib'
    extra_paths = [str(tandem_dir)]
    if venv_site.exists():
        for sp in venv_site.glob('python*/site-packages'):
            extra_paths.append(str(sp))
    env['PYTHONPATH'] = os.pathsep.join(extra_paths)
    probe = subprocess.check_output(
        [sys.executable, '-c', 'import json, tandem_mcp; print(json.dumps({"version": tandem_mcp.__version__, "file": tandem_mcp.__file__}))'],
        cwd=tandem_dir, env=env, text=True,
    )
    imported = json.loads(probe.strip())
    imported_path = str(Path(imported['file']).resolve())
    path_matches = str(pkg_dir.resolve()) in imported_path
    version_matches = (imported['version'] == expected_version)
    if (not path_matches or not version_matches) and not allow_override:
        raise RuntimeError(f'Tandem import mismatch: version={imported["version"]} path={imported_path}')

    return {
        'tandem_dir': str(tandem_dir),
        'commit': commit_info,
        'git_clean': is_clean,
        'imported_version': imported['version'],
        'version_matches': version_matches,
        'imported_path': imported_path,
        'path_matches': path_matches,
        'source_hashes': source_hashes,
        'verified': bool(commit_info['matches'] and is_clean and version_matches and path_matches),
    }


def verify_fixtures_manifest(fixtures_dir: Path) -> dict[str, Any]:
    """Verify SHA-256 hashes of all frozen fixtures against manifest.json."""
    manifest_path = fixtures_dir / 'manifest.json'
    if not manifest_path.exists():
        raise FileNotFoundError(f'Missing fixture manifest: {manifest_path}')
    manifest = json.loads(manifest_path.read_text())
    mismatches = []
    checked = 0
    for rel, info in manifest.get('files', {}).items():
        fp = fixtures_dir / rel
        if not fp.exists():
            mismatches.append({'file': rel, 'reason': 'missing'})
            continue
        actual_sha = hashlib.sha256(fp.read_bytes()).hexdigest()
        if actual_sha != info['sha256']:
            mismatches.append({'file': rel, 'reason': 'sha256_mismatch', 'expected': info['sha256'], 'actual': actual_sha})
        checked += 1
    if mismatches:
        raise RuntimeError(f'Fixture integrity check failed: {mismatches}')
    return {'checked_files': checked, 'git_commit': manifest.get('git_commit'), 'ok': True}


def aggregate_runs(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate repeated runs for one (task, scenario) pair.

    - Uses end_to_end_success (execution_completed AND artifact_valid).
    - Includes ALL measured attempts (both successful and failed) in cloud token totals.
    - Reports usage coverage, missing usage count, and cloud_tokens_per_success.
    - Variability intervals (stdev/min/max) are only reported when n >= 3.
    """
    n = len(records)
    if n == 0:
        return {
            'n': 0, 'completed_executions': 0, 'end_to_end_successes': 0,
            'artifact_valid_count': 0, 'failed_executions': 0, 'timeouts': 0,
            'interrupted_or_partial': 0, 'evaluation_errors': 0,
            'end_to_end_success_rate': 0.0, 'artifact_pass_rate': 0.0, 'failure_rate': 100.0,
            'measured_usage_count': 0, 'missing_usage_count': 0, 'usage_coverage_pct': 0.0,
            'total_measured_cloud_tokens': None, 'mean_cloud_tokens_per_attempt': None,
            'cloud_tokens_per_success': None, 'cloud_tokens_per_success_complete': False,
        }

    outcomes = []
    for r in records:
        if 'outcome' in r and isinstance(r['outcome'], dict):
            outcomes.append(r['outcome'])
        else:
            outcomes.append(classify_outcome(r.get('status'), r.get('quality')))

    completed = sum(1 for o in outcomes if o['execution_completed'])
    e2e_ok = sum(1 for o in outcomes if o['end_to_end_success'])
    art_ok = sum(1 for o in outcomes if o['artifact_valid'])
    timeouts = sum(1 for o in outcomes if o['execution_status'] == 'TIMEOUT')
    interrupted = sum(1 for o in outcomes if o['execution_status'] in {'INTERRUPTED', 'PARTIAL'})
    eval_errs = sum(1 for o in outcomes if o['execution_status'] == 'EVALUATION_ERROR')
    failed = n - e2e_ok

    times = [r['wall_seconds'] for r in records if r.get('wall_seconds') is not None]
    measured_cloud = [
        r['cloud_usage']['cloud_total_tokens']
        for r in records
        if r.get('cloud_usage', {}).get('cloud_tokens_status') == 'measured'
        and r['cloud_usage'].get('cloud_total_tokens') is not None
    ]
    missing_usage = n - len(measured_cloud)
    coverage_pct = round(100.0 * len(measured_cloud) / n, 1)
    total_cloud = sum(measured_cloud) if measured_cloud else None
    mean_attempt_cloud = round(statistics.mean(measured_cloud), 1) if measured_cloud else None

    if e2e_ok > 0 and total_cloud is not None:
        tokens_per_success = round(total_cloud / e2e_ok, 1)
        tokens_per_success_complete = (missing_usage == 0)
    else:
        tokens_per_success = None
        tokens_per_success_complete = False

    local_vals = [
        r['local_compute']['local_total_tokens']
        for r in records
        if r.get('local_compute', {}).get('provenance') == 'measured'
        and r['local_compute'].get('local_total_tokens') is not None
    ]
    repairs = sum(int(r.get('local_compute', {}).get('repair_attempts') or 0) for r in records)
    compliances = [
        r['quality']['constraint_compliance_pct']
        for r in records
        if r.get('quality', {}).get('constraint_compliance_pct') is not None
    ]

    summary: dict[str, Any] = {
        'n': n,
        'completed_executions': completed,
        'end_to_end_successes': e2e_ok,
        'artifact_valid_count': art_ok,
        'failed_executions': failed,
        'timeouts': timeouts,
        'interrupted_or_partial': interrupted,
        'evaluation_errors': eval_errs,
        'end_to_end_success_rate': round(100.0 * e2e_ok / n, 1),
        'artifact_pass_rate': round(100.0 * art_ok / n, 1),
        'failure_rate': round(100.0 * failed / n, 1),
        'measured_usage_count': len(measured_cloud),
        'missing_usage_count': missing_usage,
        'usage_coverage_pct': coverage_pct,
        'total_measured_cloud_tokens': total_cloud,
        'mean_cloud_tokens_per_attempt': mean_attempt_cloud,
        'cloud_tokens_per_success': tokens_per_success,
        'cloud_tokens_per_success_complete': tokens_per_success_complete,
        'median_seconds': round(statistics.median(times), 2) if times else None,
        'mean_seconds': round(statistics.mean(times), 2) if times else None,
        'local_tokens_total': sum(local_vals) if local_vals else None,
        'local_tokens_mean_per_attempt': round(statistics.mean(local_vals), 1) if local_vals else None,
        'repair_attempts_total': repairs,
        'constraint_compliance_mean': round(statistics.mean(compliances), 1) if compliances else None,
        'statistically_representative': n >= 3,
    }
    if n >= 3 and len(times) >= 3:
        summary['seconds_stdev'] = round(statistics.stdev(times), 2)
        summary['seconds_min'] = round(min(times), 2)
        summary['seconds_max'] = round(max(times), 2)
    if n >= 3 and len(measured_cloud) >= 3:
        summary['cloud_tokens_stdev'] = round(statistics.stdev(measured_cloud), 1)
        summary['cloud_tokens_min'] = min(measured_cloud)
        summary['cloud_tokens_max'] = max(measured_cloud)
    return summary
