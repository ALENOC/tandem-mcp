#!/usr/bin/env python3
"""Run 3-way comparison (A: direct, B: tandem_forced, C: auto) on dev or frozen eval split."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SUITE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SUITE_ROOT.parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(SUITE_ROOT))
sys.path.insert(0, str(REPO_ROOT / "benchmarks/hydrogen_3_6_1"))

os.environ["TANDEM_PROFILE"] = "lean"
os.environ["TANDEM_WAIT_SECONDS"] = "0"
os.environ["TANDEM_HOST_MANAGED"] = "1"

import suite_def  # noqa: E402
from suite import EXECUTOR_MODEL, LM_STUDIO_URL, ORCHESTRATOR_MODEL  # noqa: E402
from tandem_mcp import engine, host_runner, store  # noqa: E402


def _restore_agy_mcp() -> None:
    subprocess.run(
        [
            "agy", "mcp", "add",
            "--env", "TANDEM_HOST_MANAGED=1",
            "--env", "TANDEM_WAIT_SECONDS=0",
            "--env", "TANDEM_PROFILE=lean",
            "tandem-mcp",
            "/home/ale/tools/tandem-mcp/.venv/bin/python",
            "/home/ale/tools/tandem-mcp/main.py",
        ],
        capture_output=True,
    )
    subprocess.run(["agy", "mcp", "enable", "tandem-mcp"], capture_output=True)


def _run_agy_single(prompt: str, ws: Path, timeout_s: float) -> dict:
    t0 = time.monotonic()
    timed_out = False
    rc, stdout, stderr = -1, "", ""
    try:
        proc = subprocess.run(
            [
                "agy", "-p", prompt,
                "--model", ORCHESTRATOR_MODEL,
                "--output-format", "json",
                "--mode", "auto",
                "--dangerously-skip-permissions",
                "--disable-slash-commands",
            ],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        rc, stdout, stderr = proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
    elapsed = round(time.monotonic() - t0, 2)
    parsed = {}
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                pass
    return {
        "timed_out": timed_out,
        "rc": rc,
        "elapsed": elapsed,
        "status": parsed.get("status", "TIMEOUT" if timed_out else "ERROR"),
        "usage": parsed.get("usage") or {},
        "response": parsed.get("response", ""),
        "conversation_id": parsed.get("conversation_id"),
    }


def _init_tandem_home(thome: Path) -> None:
    thome.mkdir(parents=True, exist_ok=True)
    store.DATA = thome
    store.JOBS = thome / "jobs"
    store.CACHE = thome / "cache"
    store.LEDGER = thome / "ledger.jsonl"
    store.LESSONS = thome / "lessons.jsonl"
    store.MODELS = thome / "models.json"
    store.init()
    engine.connect(url=LM_STUDIO_URL, refresh=True)


def _ledger_local_tokens(thome: Path) -> int:
    lp = thome / "ledger.jsonl"
    if not lp.is_file():
        return 0
    tot = 0
    for line in lp.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("kind") == "llm":
            tot += int(row.get("prompt_tokens") or 0) + int(row.get("completion_tokens") or 0)
    return tot


def _read_router_decisions(thome: Path) -> list[dict]:
    rp = thome / "router_log.jsonl"
    if not rp.is_file():
        return []
    return [json.loads(l) for l in rp.read_text(encoding="utf-8").splitlines() if l.strip()]


def run_attempt(case: dict, mode: str, run_dir: Path) -> dict:
    ws = run_dir / "workspaces" / f"{case['id']}__{mode}"
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True, exist_ok=True)
    case["builder"](ws)
    before_hashes = suite_def.snapshot_before(ws)
    budget_s = float(case["budget_s"])

    if mode == "A_direct":
        subprocess.run(["agy", "mcp", "disable", "tandem-mcp"], check=True, capture_output=True)
        p_text = f"Work in workspace: {ws.resolve()}\n\n{case['prompt']}"
        res = _run_agy_single(p_text, ws, budget_s)
        ev = suite_def.evaluate_case(case, ws, res["response"], before_hashes)
        return {
            "case_id": case["id"],
            "family": case["family"],
            "split": case["split"],
            "mode": mode,
            "budget_s": budget_s,
            "completed": (not res["timed_out"]) and res["status"] == "SUCCESS",
            "correct": ev["correct"],
            "verified_path": ev["correct"],
            "timed_out": res["timed_out"],
            "wall_seconds": res["elapsed"],
            "cloud_tokens": int((res["usage"] or {}).get("total_tokens") or 0),
            "cloud_calls": 1,
            "local_tokens": 0,
            "router_decision": None,
            "fallback_used": False,
            "eval_reason": ev["reason"],
            "workspace": str(ws),
        }

    # Mode B (tandem_forced) or Mode C (auto)
    thome = run_dir / "tandem_homes" / f"{case['id']}__{mode}"
    _init_tandem_home(thome)
    uv, _th, mcp_url = host_runner.start_local_http_mcp()
    t0 = time.monotonic()
    timed_out = False
    cloud_tokens = 0
    cloud_calls = 0
    response_text = ""
    job_id = None
    job_state = None
    fallback_used = False

    try:
        subprocess.run(["agy", "mcp", "add", "--type", "http", "tandem-mcp", mcp_url], check=True, capture_output=True)
        subprocess.run(["agy", "mcp", "enable", "tandem-mcp"], check=True, capture_output=True)

        if mode == "B_tandem_forced":
            if case["read_only"]:
                instr = (
                    f"Work in workspace: {ws.resolve()}\n\nRequest:\n{case['prompt']}\n\n"
                    "MANDATORY: Use Tandem MCP (`digest_file`, `digest_many`, `digest_command`, or `extract_from_file`) "
                    "to read/analyze via local Qwen instead of reading files directly. Do not modify files."
                )
            else:
                instr = (
                    f"Work in workspace: {ws.resolve()}\n\nRequest:\n{case['prompt']}\n\n"
                    "MANDATORY: Delegate coding/edits via Tandem MCP `delegate` ONCE with clear `write_globs`, "
                    "`verify_commands`, and atomic `constraints`. As soon as `delegate` returns the `job_id`, "
                    "stop immediately and reply with that `job_id` (the host will wait locally)."
                )
        else:
            instr = (
                f"Work in workspace: {ws.resolve()}\n\nusa Tandem: {case['prompt']}\n\n"
                f"Time budget: {int(budget_s)}s. First call `auto_route(request=..., workspace=..., budget_seconds={int(budget_s)})` ONCE, "
                "then execute ONLY the route it selects (`deterministic`, `direct_or_targeted`, or `delegate_local`). "
                "If you call `delegate`, stop immediately with the `job_id` without running tests yourself so the host waits locally."
            )

        plan_res = _run_agy_single(instr, ws, min(240.0, budget_s))
        cloud_calls += 1
        cloud_tokens += int((plan_res["usage"] or {}).get("total_tokens") or 0)
        response_text = plan_res["response"] or ""
        timed_out = plan_res["timed_out"]

        # Check if a delegate job was started in thome/jobs
        jobs_dir = thome / "jobs"
        started_jobs = sorted([p.name for p in jobs_dir.iterdir() if p.is_dir()]) if jobs_dir.is_dir() else []
        if started_jobs and not timed_out:
            job_id = started_jobs[-1]
            rem = max(10.0, budget_s - (time.monotonic() - t0))
            hres = host_runner.run_host_managed(
                attach_job_id=job_id,
                poll_interval_s=2.0,
                timeout_s=rem,
                review_on_failure=False,
            )
            job_state = hres.state
            timed_out = timed_out or hres.timed_out
            response_text = hres.receipt or response_text
    finally:
        uv.should_exit = True

    elapsed = round(time.monotonic() - t0, 2)
    local_tokens = _ledger_local_tokens(thome)
    decisions = _read_router_decisions(thome)
    ev = suite_def.evaluate_case(case, ws, response_text, before_hashes)
    completed = (not timed_out) and (job_state in (None, "verified"))
    return {
        "case_id": case["id"],
        "family": case["family"],
        "split": case["split"],
        "mode": mode,
        "budget_s": budget_s,
        "completed": completed,
        "correct": ev["correct"],
        "verified_path": bool(completed and ev["correct"]),
        "timed_out": timed_out,
        "wall_seconds": elapsed,
        "cloud_tokens": cloud_tokens,
        "cloud_calls": cloud_calls,
        "local_tokens": local_tokens,
        "job_id": job_id,
        "job_state": job_state,
        "router_decision": decisions[-1] if decisions else None,
        "fallback_used": fallback_used,
        "eval_reason": ev["reason"],
        "workspace": str(ws),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "eval"], required=True)
    args = parser.parse_args()

    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    cases = [c for c in suite_def.CASES if c["split"] == args.split]
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + f"_auto_suite_{args.split}"
    run_dir = SUITE_ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    orders = [
        ["A_direct", "B_tandem_forced", "C_auto"],
        ["B_tandem_forced", "C_auto", "A_direct"],
        ["C_auto", "A_direct", "B_tandem_forced"],
    ]
    records = []
    try:
        for idx, case in enumerate(cases):
            order = orders[idx % len(orders)]
            for mode in order:
                print(f"[{run_id}] {case['id']} ({case['family']}) -> {mode}...", flush=True)
                rec = run_attempt(case, mode, run_dir)
                records.append(rec)
                print(f"  -> correct={rec['correct']} wall={rec['wall_seconds']}s cloud={rec['cloud_tokens']} local={rec['local_tokens']} route={(rec.get('router_decision') or {}).get('route')} ({rec['eval_reason']})", flush=True)
                payload = {
                    "run_id": run_id,
                    "split": args.split,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "models": {"cloud": ORCHESTRATOR_MODEL, "local": EXECUTOR_MODEL},
                    "frozen_sha256": {
                        "router.py": sha(REPO_ROOT / "tandem_mcp/router.py"),
                        "suite_def.py": sha(SUITE_ROOT / "suite_def.py"),
                    },
                    "records": records,
                }
                (run_dir / "results.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    finally:
        _restore_agy_mcp()

    print("Saved", run_dir / "results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
