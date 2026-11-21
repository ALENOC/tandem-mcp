#!/usr/bin/env python3
"""Run threshold discovery on dev_t (Direct vs Forced Delegate) and frozen validation on eval_t (Direct vs Delegate vs Auto)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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

import run_suite_v2 as v2  # noqa: E402
import suite_def  # noqa: E402
import thresh_suite  # noqa: E402
from suite import EXECUTOR_MODEL, LM_STUDIO_URL, ORCHESTRATOR_MODEL  # noqa: E402
from tandem_mcp import host_runner, store  # noqa: E402


def run_forced_delegate(case: dict, run_dir: Path) -> dict:
    """Mode D: mandatory delegation to Qwen via Tandem MCP (host-managed, 0 cloud polling)."""
    ws = run_dir / "workspaces" / f"{case['id']}__D_delegate"
    if ws.exists():
        import shutil
        shutil.rmtree(ws)
    ws.mkdir(parents=True, exist_ok=True)
    case["builder"](ws)
    before_hashes = suite_def.snapshot_before(ws)
    budget_s = float(case["budget_s"])

    os.environ["TANDEM_AUTO_POLICY"] = "first_turn"
    thome = run_dir / "tandem_homes" / f"{case['id']}__D_delegate"
    v2._init_tandem_home(thome)
    uv, _th, mcp_url = host_runner.start_local_http_mcp()
    t0 = time.monotonic()
    timed_out = False
    timeout_source = "none"
    cloud_tokens = None
    response_text = ""
    job_id = None
    job_state = None
    conv_id = None
    num_turns = None

    try:
        subprocess.run(["agy", "mcp", "add", "--type", "http", "tandem-mcp", mcp_url], check=True, capture_output=True)
        subprocess.run(["agy", "mcp", "enable", "tandem-mcp"], check=True, capture_output=True)
        instr = (
            f"Work in workspace: {ws.resolve()}\n\nRequest:\n{case['prompt']}\n\n"
            "MANDATORY: Delegate this task via Tandem MCP `delegate` ONCE with clear `write_globs`, "
            "`verify_commands`, and atomic `constraints`. As soon as `delegate` returns the `job_id`, "
            "stop immediately and reply with that `job_id` so the host waits locally."
        )
        plan_res = v2._run_agy_single(instr, ws, budget_s)
        conv_id = plan_res.get("conversation_id")
        num_turns = plan_res.get("num_turns")
        if plan_res["usage"] and "total_tokens" in plan_res["usage"]:
            cloud_tokens = int(plan_res["usage"]["total_tokens"])
        response_text = plan_res["response"] or ""
        timed_out = plan_res["timed_out"]
        if timed_out:
            timeout_source = "planner"

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
            if hres.timed_out:
                timed_out = True
                timeout_source = "host_watcher"
            response_text = hres.receipt or response_text
    finally:
        uv.should_exit = True

    elapsed = round(time.monotonic() - t0, 2)
    local_infs, local_tokens = v2._ledger_stats(thome)
    tr = v2._inspect_transcript(conv_id)
    ev = suite_def.evaluate_case(case, ws, response_text, before_hashes)
    in_budget = (not timed_out) and (job_state in (None, "verified"))
    repairs = 0
    if job_id:
        jd = store.read_job(job_id) or {}
        repairs = int(jd.get("repairs") or 0)

    return {
        "case_id": case["id"],
        "family": case["family"],
        "size_hint": case.get("size_hint"),
        "mode": "D_delegate",
        "budget_s": budget_s,
        "planner_deadline_s": budget_s,
        "artifact_correct": ev["correct"],
        "delivered_in_budget": in_budget,
        "success_in_budget": bool(ev["correct"] and in_budget),
        "timed_out": timed_out,
        "timeout_source": timeout_source,
        "wall_seconds": elapsed,
        "cloud_tokens": cloud_tokens,
        "cloud_usage_scope": "session_aggregate" if cloud_tokens is not None else "missing",
        "cloud_turns": tr["cloud_turns"] or num_turns,
        "first_action": tr["first_action"],
        "tool_calls": tr["tool_calls"],
        "job_id": job_id,
        "job_state": job_state,
        "repairs": repairs,
        "local_inferences": local_infs,
        "local_tokens": local_tokens,
        "executed_route": "timeout" if timed_out else ("local_delegate" if job_id else "non verificato"),
        "fallback": "none",
        "reason": ev["reason"],
        "workspace": str(ws),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["dev", "eval"], required=True)
    args = parser.parse_args()

    split = "dev_t" if args.phase == "dev" else "eval_t"
    cases = [c for c in thresh_suite.THRESH_CASES if c["split"] == split]
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + f"_thresh_{args.phase}"
    run_dir = SUITE_ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()

    records = []
    try:
        for idx, case in enumerate(cases):
            if args.phase == "dev":
                order = ["A_direct", "D_delegate"] if idx % 2 == 0 else ["D_delegate", "A_direct"]
            else:
                orders = [
                    ["A_direct", "D_delegate", "C_auto_first_turn"],
                    ["D_delegate", "C_auto_first_turn", "A_direct"],
                    ["C_auto_first_turn", "A_direct", "D_delegate"],
                ]
                order = orders[idx % 3]

            for mode in order:
                print(f"[{run_id}] {case['id']} ({case['size_hint']}) -> {mode}...", flush=True)
                if mode == "D_delegate":
                    rec = run_forced_delegate(case, run_dir)
                else:
                    rec = v2.run_attempt(case, mode, run_dir)
                    rec["size_hint"] = case.get("size_hint")
                    rec["repairs"] = 0
                records.append(rec)
                print(
                    f"  -> ok_budget={rec['success_in_budget']} art={rec['artifact_correct']} "
                    f"cloud={rec['cloud_tokens']} local={rec['local_tokens']} wall={rec['wall_seconds']}s "
                    f"exec={rec['executed_route']} ({rec['reason']})",
                    flush=True,
                )
                payload = {
                    "run_id": run_id,
                    "phase": args.phase,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "models": {"cloud": ORCHESTRATOR_MODEL, "local": EXECUTOR_MODEL},
                    "frozen_sha256": {
                        "server.py": sha(REPO_ROOT / "tandem_mcp/server.py"),
                        "thresh_suite.py": sha(SUITE_ROOT / "thresh_suite.py"),
                    },
                    "records": records,
                }
                (run_dir / "results.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    finally:
        v2._restore_agy_mcp()

    print("Saved", run_dir / "results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
