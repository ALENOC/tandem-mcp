#!/usr/bin/env python3
"""Benchmark suite for Tandem MCP v3.6.1: Gemini 4 Hydrogen + Qwen3.8 27B."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import statistics
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluate import evaluate_attempt

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
RUNS_DIR = ROOT / "runs"

ORCHESTRATOR_MODEL = "gemini-4-hydrogen-medium"
ORCHESTRATOR_LABEL = "Gemini 4 Hydrogen (Medium)"
EXECUTOR_MODEL = "qwen3.8-27b@iq3_s"
LM_STUDIO_URL = "http://127.0.0.1:1234/v1"

TASKS: list[dict[str, Any]] = [
    {
        "id": "reading_agent_rollback",
        "name": "Targeted code QA (agent.py rollback)",
        "category": "reading",
        "timeout_s": 900,
        "fixture_type": "dir",
        "fixture": "tandem_mcp_pkg",
        "direct_prompt": (
            "In tandem_mcp_pkg/agent.py, what does rollback do when a pre-existing file entry "
            "in snapshot.json has value None, and what does it do when the value is a string/path? "
            "Cite the relevant logic concisely."
        ),
        "tandem_prompt": (
            "Use Tandem MCP (`digest_file` with grep='snapshot.json' or focused question) on "
            "tandem_mcp_pkg/agent.py to answer: what does rollback do when a pre-existing file entry "
            "in snapshot.json has value None, and what does it do when the value is a string/path? "
            "Do not read the full file directly with native tools."
        ),
    },
    {
        "id": "reading_package_survey",
        "name": "Multi-file package survey (tandem_mcp/*.py)",
        "category": "reading",
        "timeout_s": 1200,
        "fixture_type": "dir",
        "fixture": "tandem_mcp_pkg",
        "direct_prompt": (
            "Summarize the primary responsibility of each .py module in tandem_mcp_pkg/ "
            "(excluding __init__.py). List each module name and a 1-sentence summary."
        ),
        "tandem_prompt": (
            "Use Tandem MCP (`digest_many` on tandem_mcp_pkg/*.py) to summarize the primary "
            "responsibility of each .py module in tandem_mcp_pkg/ (excluding __init__.py). "
            "List each module name and a 1-sentence summary. Do not read the files directly."
        ),
    },
    {
        "id": "reading_git_log",
        "name": "Git history digestion (25 commits)",
        "category": "reading",
        "timeout_s": 900,
        "fixture_type": "file",
        "fixture": "git_log_25_stat.txt",
        "direct_prompt": (
            "From git_log_25_stat.txt, which 3 files were modified in the most commits, "
            "and what are the main themes of these 25 commits?"
        ),
        "tandem_prompt": (
            "Use Tandem MCP (`digest_file` on git_log_25_stat.txt) to determine which 3 files "
            "were modified in the most commits and the main themes of these 25 commits. "
            "Do not read git_log_25_stat.txt directly."
        ),
    },
    {
        "id": "extraction_manifest",
        "name": "Structured JSON extraction (pyproject.toml)",
        "category": "extraction",
        "timeout_s": 240,
        "fixture_type": "file",
        "fixture": "pyproject.toml",
        "direct_prompt": (
            "From pyproject.toml, return ONLY a valid JSON object with keys: "
            "\"name\", \"requires_python\", \"dependencies\" (list of strings), \"console_script\" (string)."
        ),
        "tandem_prompt": (
            "Use Tandem MCP (`extract_from_file` on pyproject.toml) to extract a JSON object with keys: "
            "\"name\", \"requires_python\", \"dependencies\" (list of strings), \"console_script\" (string). "
            "Return ONLY the JSON object."
        ),
    },
    {
        "id": "bugfix_multifile",
        "name": "Multi-file bugfix (4 modules + tests)",
        "category": "bugfix",
        "timeout_s": 600,
        "fixture_type": "dir_flat",
        "fixture": "bugfix_multifile",
        "direct_prompt": (
            "Run `python3 -m unittest test_suite.py` in the workspace, diagnose the bugs across "
            "the modules (parser.py, validator.py, etc.), fix them without modifying test_suite.py, "
            "and re-run `python3 -m unittest test_suite.py` to confirm all tests pass."
        ),
        "tandem_prompt": (
            "Use Tandem MCP (`delegate` with `python3 -m unittest test_suite.py` as acceptance check, "
            "writable=['parser.py', 'validator.py', 'service.py', 'config.py']) to diagnose and fix "
            "the bugs in this workspace without modifying test_suite.py. Inspect `job_evidence` / `job_diff` "
            "and call `job_feedback` before finishing."
        ),
    },
    {
        "id": "feature_rate_limiter",
        "name": "Bounded module + tests (rate_limiter.py)",
        "category": "feature",
        "timeout_s": 900,
        "fixture_type": "dir_flat",
        "fixture": "feature_rate_limiter",
        "direct_prompt": (
            "Read SPEC.md and implement `rate_limiter.py` and `test_rate_limiter.py` satisfying "
            "every requirement. Run `python3 -m unittest test_rate_limiter.py` to verify all tests pass."
        ),
        "tandem_prompt": (
            "Read SPEC.md (via `digest_file` or directly), then use Tandem MCP (`delegate` with "
            "writable=['rate_limiter.py', 'test_rate_limiter.py'] and acceptance check "
            "`python3 -m unittest test_rate_limiter.py`) to implement `rate_limiter.py` and "
            "`test_rate_limiter.py`. Inspect `job_evidence` and call `job_feedback` before finishing."
        ),
    },
]


def preflight() -> dict[str, Any]:
    """Verify LM Studio and agy CLI are ready."""
    req = urllib.request.Request(f"{LM_STUDIO_URL}/models", method="GET")
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    model_ids = [m.get("id") for m in data.get("data", [])]
    if EXECUTOR_MODEL not in model_ids:
        raise RuntimeError(f"Executor model {EXECUTOR_MODEL!r} not found in LM Studio models: {model_ids}")

    agy_ver = subprocess.run(["agy", "--version"], capture_output=True, text=True, check=True).stdout.strip()
    mcp_list = subprocess.run(["agy", "mcp", "list"], capture_output=True, text=True, check=True).stdout
    tandem_enabled = "tandem-mcp" in mcp_list and "enabled" in [
        line for line in mcp_list.splitlines() if "tandem-mcp" in line
    ][0]
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "lm_studio_url": LM_STUDIO_URL,
        "lm_studio_models": model_ids,
        "executor_model": EXECUTOR_MODEL,
        "orchestrator_model": ORCHESTRATOR_MODEL,
        "agy_version": agy_ver,
        "initial_tandem_mcp_enabled": tandem_enabled,
    }


def set_tandem_mcp(enabled: bool) -> None:
    cmd = ["agy", "mcp", "enable" if enabled else "disable", "tandem-mcp"]
    subprocess.run(cmd, capture_output=True, text=True, check=True)


def prepare_workspace(task: dict[str, Any], workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    src = FIXTURES / task["fixture"]
    ftype = task["fixture_type"]
    if ftype == "file":
        shutil.copy2(src, workspace / src.name)
    elif ftype == "dir":
        shutil.copytree(src, workspace / src.name, dirs_exist_ok=True)
    elif ftype == "dir_flat":
        shutil.copytree(src, workspace, dirs_exist_ok=True)
    else:
        raise ValueError(f"Unknown fixture_type: {ftype}")


def read_ledger_entries(ledger_path: Path) -> list[dict[str, Any]]:
    if not ledger_path.exists():
        return []
    entries = []
    for line in ledger_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def summarize_local_ledger(entries: list[dict[str, Any]]) -> dict[str, Any]:
    prompt_tok = sum(int(e.get("prompt_tokens", 0) or 0) for e in entries)
    comp_tok = sum(int(e.get("completion_tokens", 0) or 0) for e in entries)
    saved_tok = sum(int(e.get("saved_tokens_est", 0) or 0) for e in entries)
    return {
        "local_calls": len(entries),
        "local_prompt_tokens": prompt_tok,
        "local_completion_tokens": comp_tok,
        "local_total_tokens": prompt_tok + comp_tok,
        "estimated_saved_tokens": saved_tok,
    }


def run_attempt(
    task: dict[str, Any],
    scenario: str,
    repeat: int,
    run_dir: Path,
) -> dict[str, Any]:
    attempt_id = f"{task['id']}__{scenario}__r{repeat}"
    workspace = run_dir / "workspaces" / attempt_id
    prepare_workspace(task, workspace)

    tandem_home = run_dir / "tandem_homes" / attempt_id
    tandem_home.mkdir(parents=True, exist_ok=True)

    default_ledger = Path.home() / ".local/share/tandem-mcp/ledger.jsonl"
    before_default_count = len(read_ledger_entries(default_ledger)) if scenario == "tandem" else 0

    env = os.environ.copy()
    env["TANDEM_HOME"] = str(tandem_home)
    env["TANDEM_MODEL"] = EXECUTOR_MODEL

    prompt = task["direct_prompt"] if scenario == "direct" else task["tandem_prompt"]
    cmd = [
        "agy",
        "-p", prompt,
        "--model", ORCHESTRATOR_MODEL,
        "--output-format", "json",
        "--mode", "auto",
        "--dangerously-skip-permissions",
        "--disable-slash-commands",
    ]

    t0 = time.monotonic()
    timed_out = False
    stdout_str = ""
    stderr_str = ""
    rc = -1

    proc = subprocess.Popen(
        cmd,
        cwd=str(workspace),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout_str, stderr_str = proc.communicate(timeout=task["timeout_s"])
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout_str, stderr_str = proc.communicate()
    elapsed = round(time.monotonic() - t0, 2)

    log_dir = run_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"{attempt_id}.stdout.txt").write_text(stdout_str or "", encoding="utf-8")
    (log_dir / f"{attempt_id}.stderr.txt").write_text(stderr_str or "", encoding="utf-8")

    parsed_json: dict[str, Any] = {}
    for line in (stdout_str or "").splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed_json = json.loads(line)
            except json.JSONDecodeError:
                pass

    status = parsed_json.get("status", "TIMEOUT" if timed_out else "ERROR")
    completed = (not timed_out) and (rc == 0) and (status == "SUCCESS")
    response_text = parsed_json.get("response", "")
    usage = parsed_json.get("usage") or {}

    ev = evaluate_attempt(task["id"], response_text, workspace)
    e2e_success = bool(completed and ev["valid"])

    local_stats = {"local_calls": 0, "local_prompt_tokens": 0, "local_completion_tokens": 0, "local_total_tokens": 0, "estimated_saved_tokens": 0}
    if scenario == "tandem":
        iso_ledger = tandem_home / "ledger.jsonl"
        entries = read_ledger_entries(iso_ledger)
        if not entries and default_ledger.exists():
            all_default = read_ledger_entries(default_ledger)
            entries = all_default[before_default_count:]
        local_stats = summarize_local_ledger(entries)

    return {
        "attempt_id": attempt_id,
        "task_id": task["id"],
        "task_name": task["name"],
        "category": task["category"],
        "scenario": scenario,
        "repeat": repeat,
        "completed": completed,
        "timed_out": timed_out,
        "artifact_valid": ev["valid"],
        "eval_reason": ev["reason"],
        "e2e_success": e2e_success,
        "duration_seconds": parsed_json.get("duration_seconds", elapsed),
        "wall_seconds": elapsed,
        "num_turns": parsed_json.get("num_turns"),
        "conversation_id": parsed_json.get("conversation_id"),
        "cloud_usage": {
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "thinking_tokens": usage.get("thinking_tokens"),
            "cache_read_tokens": usage.get("cache_read_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
        "local_usage": local_stats,
    }


def aggregate_results(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for a in attempts:
        grouped.setdefault((a["task_id"], a["scenario"]), []).append(a)

    direct_means: dict[str, float] = {}
    for (tid, scen), rows in grouped.items():
        if scen == "direct":
            toks = [r["cloud_usage"]["total_tokens"] for r in rows if r["cloud_usage"]["total_tokens"] is not None]
            if toks:
                direct_means[tid] = statistics.mean(toks)

    summary = []
    for task in TASKS:
        tid = task["id"]
        for scen in ("direct", "tandem"):
            rows = grouped.get((tid, scen), [])
            if not rows:
                continue
            n = len(rows)
            e2e = sum(1 for r in rows if r["e2e_success"])
            toks = [r["cloud_usage"]["total_tokens"] for r in rows if r["cloud_usage"]["total_tokens"] is not None]
            mean_cloud = round(statistics.mean(toks), 1) if toks else None
            times = [r["wall_seconds"] for r in rows]
            med_time = round(statistics.median(times), 2) if times else None
            mean_local = round(statistics.mean(r["local_usage"]["local_total_tokens"] for r in rows), 1)
            savings_pct = None
            if scen == "tandem" and mean_cloud is not None and tid in direct_means and direct_means[tid] > 0:
                savings_pct = round((1.0 - (mean_cloud / direct_means[tid])) * 100.0, 1)
            summary.append({
                "task_id": tid,
                "task_name": task["name"],
                "scenario": scen,
                "n": n,
                "e2e_success_count": e2e,
                "e2e_success_pct": round(100.0 * e2e / n, 1),
                "mean_cloud_tokens": mean_cloud,
                "cloud_savings_vs_direct_pct": savings_pct,
                "median_wall_seconds": med_time,
                "mean_local_tokens": mean_local,
            })
    return summary


def render_markdown(run_id: str, pre: dict[str, Any], summary: list[dict[str, Any]], attempts: list[dict[str, Any]]) -> str:
    lines = [
        f"# Tandem MCP v3.6.1 Benchmark — {ORCHESTRATOR_LABEL} + {EXECUTOR_MODEL}",
        "",
        f"- **Run ID**: `{run_id}`",
        f"- **Date (UTC)**: `{pre['timestamp']}`",
        f"- **Orchestrator**: `{ORCHESTRATOR_MODEL}` (`agy` {pre['agy_version']})",
        f"- **Executor**: `{EXECUTOR_MODEL}` on LM Studio (`{LM_STUDIO_URL}`)",
        "- **Accounting**: Cloud tokens measured directly via `agy --output-format json`; local tokens measured via Tandem `ledger.jsonl`.",
        "",
        "## Summary Table",
        "",
        "| Task | Scenario | n | E2E Success | Mean Cloud Tokens | Cloud Savings vs Direct | Median Time (s) | Mean Local Tokens |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary:
        cloud_str = f"{row['mean_cloud_tokens']:,.1f}" if row["mean_cloud_tokens"] is not None else "N/A"
        if row["scenario"] == "direct":
            sav_str = "baseline"
        elif row["cloud_savings_vs_direct_pct"] is not None:
            sav_str = f"{row['cloud_savings_vs_direct_pct']:+.1f}%"
        else:
            sav_str = "N/A"
        lines.append(
            f"| `{row['task_id']}` | `{row['scenario']}` | {row['n']} | "
            f"{row['e2e_success_pct']:.1f}% ({row['e2e_success_count']}/{row['n']}) | "
            f"{cloud_str} | {sav_str} | {row['median_wall_seconds']:.2f} | {row['mean_local_tokens']:,.1f} |"
        )
    lines.extend([
        "",
        "## Per-Attempt Details",
        "",
        "| Attempt | Completed | Valid | E2E | Time (s) | Turns | Cloud Input | Cloud Output | Cloud Total | Local Total | Reason |",
        "| --- | :---: | :---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ])
    for a in attempts:
        cu = a["cloud_usage"]
        lu = a["local_usage"]
        lines.append(
            f"| `{a['attempt_id']}` | {a['completed']} | {a['artifact_valid']} | {a['e2e_success']} | "
            f"{a['wall_seconds']:.2f} | {a['num_turns'] or '-'} | "
            f"{cu['input_tokens'] or '-'} | {cu['output_tokens'] or '-'} | {cu['total_tokens'] or '-'} | "
            f"{lu['local_total_tokens']} | {a['eval_reason']} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Tandem MCP Hydrogen + Qwen3.8 27B benchmark suite.")
    parser.add_argument("--tasks", default="", help="Comma-separated task IDs (default: all)")
    parser.add_argument("--repeats", type=int, default=1, help="Repeats per task/scenario (default: 1)")
    args = parser.parse_args()

    selected_ids = {t.strip() for t in args.tasks.split(",") if t.strip()}
    selected_tasks = [t for t in TASKS if not selected_ids or t["id"] in selected_ids]
    if not selected_tasks:
        print(f"No matching tasks for {args.tasks!r}", file=sys.stderr)
        return 2

    pre = preflight()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "preflight.json").write_text(json.dumps(pre, indent=2), encoding="utf-8")

    attempts: list[dict[str, Any]] = []
    initial_enabled = pre["initial_tandem_mcp_enabled"]
    try:
        for scenario in ("direct", "tandem"):
            set_tandem_mcp(scenario == "tandem")
            for task in selected_tasks:
                for rep in range(1, args.repeats + 1):
                    print(f"[{run_id}] Running {task['id']} ({scenario}, r{rep})...", flush=True)
                    res = run_attempt(task, scenario, rep, run_dir)
                    attempts.append(res)
                    print(
                        f"  -> e2e={res['e2e_success']} time={res['wall_seconds']}s "
                        f"cloud={res['cloud_usage']['total_tokens']} local={res['local_usage']['local_total_tokens']} "
                        f"({res['eval_reason']})",
                        flush=True,
                    )
    finally:
        set_tandem_mcp(initial_enabled)

    summary = aggregate_results(attempts)
    payload = {
        "run_id": run_id,
        "preflight": pre,
        "summary": summary,
        "attempts": attempts,
    }
    (run_dir / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md = render_markdown(run_id, pre, summary, attempts)
    (run_dir / "RESULTS.md").write_text(md, encoding="utf-8")
    (ROOT / "RESULTS.md").write_text(md, encoding="utf-8")
    print(f"Saved results to {run_dir / 'RESULTS.md'} and {ROOT / 'RESULTS.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
