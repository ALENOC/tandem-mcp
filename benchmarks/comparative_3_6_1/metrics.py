"""Metrics, provenance, fixture integrity, and aggregation for comparative benchmarks.

Separates:
  A. Context Reduction (text/bytes transferred to cloud)
  B. Actual Cloud Token Savings (real provider usage metadata; never estimated from artifact size)
  C. Local Compute Cost (LM Studio / Tandem ledger tokens, time, TPS, retries, repairs)

Every metric carries explicit provenance:
  - 'measured'
  - 'estimated'
  - 'derived'
  - 'unavailable'
"""
from __future__ import annotations

import hashlib
import json
import statistics
import subprocess
from pathlib import Path
from typing import Any

CHARS_PER_TOKEN = 3.6
VALID_PROVENANCE = {'measured', 'estimated', 'derived', 'unavailable'}


def est_tokens(n_chars: int, chars_per_token: float = CHARS_PER_TOKEN) -> int:
    """Estimate token count from character/byte count (always labeled 'estimated')."""
    if n_chars <= 0:
        return 0
    return round(n_chars / chars_per_token)


def compute_context_reduction(
    input_source_bytes: int,
    context_bytes_to_cloud: int,
    chars_per_token: float = CHARS_PER_TOKEN,
    collection_method: str = 'byte_count',
) -> dict[str, Any]:
    """Compute Context Reduction (bytes avoided vs full source).

    Never clamps negative values to zero: if more bytes were transferred to the
    cloud than the source size, context_reduction_pct is negative.
    """
    if input_source_bytes <= 0:
        return {
            'input_source_bytes': input_source_bytes,
            'context_bytes_to_cloud': context_bytes_to_cloud,
            'context_reduction_pct': None,
            'est_tokens_saved': None,
            'provenance': 'unavailable',
            'collection_method': collection_method,
        }
    pct = round(100.0 * (input_source_bytes - context_bytes_to_cloud) / input_source_bytes, 1)
    saved_tok_est = est_tokens(input_source_bytes - context_bytes_to_cloud, chars_per_token) if input_source_bytes >= context_bytes_to_cloud else -est_tokens(context_bytes_to_cloud - input_source_bytes, chars_per_token)
    return {
        'input_source_bytes': input_source_bytes,
        'context_bytes_to_cloud': context_bytes_to_cloud,
        'context_reduction_pct': pct,
        'est_tokens_saved': saved_tok_est,
        'provenance': 'derived',
        'est_tokens_provenance': 'estimated',
        'collection_method': collection_method,
    }


def compute_cloud_token_savings(
    direct_cloud_tokens: int | None,
    candidate_cloud_tokens: int | None,
    direct_status: str = 'measured',
    candidate_status: str = 'measured',
    collection_method: str = 'agy_cli_json_usage',
) -> dict[str, Any]:
    """Compute Actual Cloud Token Savings = (Direct - Candidate) / Direct * 100.

    - Never clamps negative savings to 0.
    - Returns None ('N/A' in reports) when either baseline or candidate is unavailable.
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
            'status': 'unavailable',
            'provenance': 'unavailable',
            'collection_method': collection_method,
        }
    diff = direct_cloud_tokens - candidate_cloud_tokens
    pct = round(100.0 * diff / direct_cloud_tokens, 1)
    return {
        'direct_cloud_tokens': direct_cloud_tokens,
        'candidate_cloud_tokens': candidate_cloud_tokens,
        'cloud_tokens_saved': diff,
        'cloud_savings_pct': pct,
        'status': 'measured',
        'provenance': 'measured',
        'collection_method': collection_method,
    }


def build_cloud_usage_record(raw_usage: dict[str, Any] | None, num_turns: int | None = None, collection_method: str = 'agy_cli_json_usage') -> dict[str, Any]:
    """Normalize provider cloud token usage with explicit provenance."""
    if not raw_usage or not isinstance(raw_usage, dict):
        return {
            'cloud_input_tokens': None,
            'cloud_output_tokens': None,
            'cloud_reasoning_tokens': None,
            'cloud_cached_tokens': None,
            'cloud_total_tokens': None,
            'cloud_calls': num_turns,
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
        total = inp + out
    status = 'measured' if (inp is not None and out is not None and total is not None) else 'unavailable'
    return {
        'cloud_input_tokens': inp,
        'cloud_output_tokens': out,
        'cloud_reasoning_tokens': think,
        'cloud_cached_tokens': cached,
        'cloud_total_tokens': total,
        'cloud_calls': num_turns,
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

    Variability intervals (min/max/stdev) are only reported when n >= 3.
    """
    n = len(records)
    if n == 0:
        return {'n': 0, 'success_rate': 0.0, 'failure_rate': 100.0}
    successes = [r for r in records if r.get('quality', {}).get('passed')]
    n_ok = len(successes)
    times = [r['wall_seconds'] for r in records if r.get('wall_seconds') is not None]
    cloud_ok = [
        r['cloud_usage']['cloud_total_tokens']
        for r in successes
        if r.get('cloud_usage', {}).get('cloud_tokens_status') == 'measured'
        and r['cloud_usage'].get('cloud_total_tokens') is not None
    ]
    local_ok = [
        r['local_compute']['local_total_tokens']
        for r in successes
        if r.get('local_compute', {}).get('local_total_tokens') is not None
    ]
    repairs = sum(r.get('local_compute', {}).get('repair_attempts', 0) for r in records)
    compliances = [
        r['quality']['constraint_compliance_pct']
        for r in records
        if r.get('quality', {}).get('constraint_compliance_pct') is not None
    ]

    summary: dict[str, Any] = {
        'n': n,
        'successes': n_ok,
        'success_rate': round(100.0 * n_ok / n, 1),
        'failure_rate': round(100.0 * (n - n_ok) / n, 1),
        'median_seconds': round(statistics.median(times), 2) if times else None,
        'mean_seconds': round(statistics.mean(times), 2) if times else None,
        'cloud_tokens_per_success_mean': round(statistics.mean(cloud_ok), 1) if cloud_ok else None,
        'cloud_tokens_per_success_median': round(statistics.median(cloud_ok), 1) if cloud_ok else None,
        'local_tokens_per_success_mean': round(statistics.mean(local_ok), 1) if local_ok else None,
        'repair_attempts_total': repairs,
        'constraint_compliance_mean': round(statistics.mean(compliances), 1) if compliances else None,
        'statistically_representative': n >= 3,
    }
    if n >= 3 and len(times) >= 3:
        summary['seconds_stdev'] = round(statistics.stdev(times), 2)
        summary['seconds_min'] = round(min(times), 2)
        summary['seconds_max'] = round(max(times), 2)
    if n >= 3 and len(cloud_ok) >= 3:
        summary['cloud_tokens_stdev'] = round(statistics.stdev(cloud_ok), 1)
        summary['cloud_tokens_min'] = min(cloud_ok)
        summary['cloud_tokens_max'] = max(cloud_ok)
    return summary
