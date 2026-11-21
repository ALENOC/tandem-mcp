#!/usr/bin/env python3
"""Controlled 3-way benchmark (A_direct, B_auto_mandatory, C_auto_first_turn) with full transcript tracing."""
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
        "num_turns": parsed.get("num_turns"),
        "response": parsed.get("response", ""),
        "conversation_id": parsed.get("conversation_id"),
    }


def _inspect_transcript(conv_id: str | None) -> dict:
    if not conv_id:
        return {"verified": False, "first_action": "non verificato", "tool_calls": [], "cloud_turns": None}
    tr = Path.home() / ".gemini/antigravity-cli/brain" / conv_id / ".system_generated/logs/transcript.jsonl"
    if not tr.is_file():
        return {"verified": False, "first_action": "non verificato", "tool_calls": [], "cloud_turns": None}
    calls = []
    planner_turns = 0
    for line in tr.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("type") == "PLANNER_RESPONSE":
            planner_turns += 1
            for tc in (obj.get("tool_calls") or []):
                nm = tc.get("name")
                if nm == "call_mcp_tool":
                    args = tc.get("args") or {}
                    nm = f"mcp:{args.get('ServerName')}/{args.get('ToolName')}"
                calls.append(nm)
    first = calls[0] if calls else ("direct_response" if planner_turns > 0 else "non verificato")
    return {"verified": True, "first_action": first, "tool_calls": calls, "cloud_turns": planner_turns}


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


def _ledger_stats(thome: Path) -> tuple[int, int]:
    lp = thome / "ledger.jsonl"
    if not lp.is_file():
        return 0, 0
    tot_tok = 0
    llm_calls = 0
    for line in lp.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("kind") == "llm":
            llm_calls += 1
            tot_tok += int(row.get("prompt_tokens") or 0) + int(row.get("completion_tokens") or 0)
    return llm_calls, tot_tok


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
        tr = _inspect_transcript(res["conversation_id"])
        ev = suite_def.evaluate_case(case, ws, res["response"], before_hashes)
        in_budget = (not res["timed_out"]) and res["status"] == "SUCCESS"
        ctok = (res["usage"] or {}).get("total_tokens")
        return {
            "case_id": case["id"],
            "family": case["family"],
            "mode": mode,
            "budget_s": budget_s,
            "planner_deadline_s": budget_s,
            "artifact_correct": ev["correct"],
            "delivered_in_budget": in_budget,
            "completed_in_budget": in_budget,
            "success_in_budget": bool(ev["correct"] and in_budget),
            "timed_out": res["timed_out"],
            "timeout_source": "planner" if res["timed_out"] else "none",
            "wall_seconds": res["elapsed"],
            "cloud_tokens": ctok,
            "cloud_usage_scope": "session_aggregate" if ctok is not None else "missing",
            "cloud_turns": tr["cloud_turns"] or res.get("num_turns"),
            "first_action": tr["first_action"],
            "tool_calls": tr["tool_calls"],
            "job_id": None,
            "job_state": None,
            "local_inferences": 0,
            "local_tokens": 0,
            "router_recommendation": None,
            "executed_route": "direct" if tr["verified"] else "non verificato",
            "fallback": "none",
            "reason": ev["reason"],
            "workspace": str(ws),
        }

    policy = "mandatory_route" if mode == "B_auto_mandatory" else "first_turn"
    os.environ["TANDEM_AUTO_POLICY"] = policy
    thome = run_dir / "tandem_homes" / f"{case['id']}__{mode}"
    _init_tandem_home(thome)
    uv, _th, mcp_url = host_runner.start_local_http_mcp()
    t0 = time.monotonic()
    timed_out = False
    cloud_tokens = None
    response_text = ""
    job_id = None
    job_state = None
    conv_id = None
    num_turns = None

    try:
        subprocess.run(["agy", "mcp", "add", "--type", "http", "tandem-mcp", mcp_url], check=True, capture_output=True)
        subprocess.run(["agy", "mcp", "enable", "tandem-mcp"], check=True, capture_output=True)

        if mode == "B_auto_mandatory":
            instr = (
                f"Work in workspace: {ws.resolve()}\n\nusa Tandem: {case['prompt']}\n\n"
                f"Time budget: {int(budget_s)}s. First call `auto_route(request=..., workspace=..., budget_seconds={int(budget_s)})` ONCE, "
                "then follow the selected route (`deterministic`, `direct_or_targeted`, or `delegate_local`). "
                "If you call `delegate`, stop immediately with the `job_id` so the host waits locally."
            )
        else:
            instr = (
                f"Work in workspace: {ws.resolve()}\n\nusa Tandem: {case['prompt']}\n\n"
                f"Time budget: {int(budget_s)}s. Choose and execute the best first action directly in turn 1: "
                "handle reads, deterministic counts, edits/refactors on existing code, or tight-budget web apps directly; "
                "delegate via `delegate` mainly for substantial from-scratch verifiable coding with >=240s budget (or >=1200s for full web apps). "
                "`auto_route` is optional. If you call `delegate`, stop immediately with the `job_id` so the host waits locally."
            )

        planner_deadline_s = budget_s
        plan_res = _run_agy_single(instr, ws, planner_deadline_s)
        conv_id = plan_res.get("conversation_id")
        num_turns = plan_res.get("num_turns")
        if plan_res["usage"] and "total_tokens" in plan_res["usage"]:
            cloud_tokens = int(plan_res["usage"]["total_tokens"])
        response_text = plan_res["response"] or ""
        timed_out = plan_res["timed_out"]
        timeout_source = "planner" if timed_out else "none"

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
    local_infs, local_tokens = _ledger_stats(thome)
    decisions = _read_router_decisions(thome)
    tr = _inspect_transcript(conv_id)
    ev = suite_def.evaluate_case(case, ws, response_text, before_hashes)
    in_budget = (not timed_out) and (job_state in (None, "verified"))

    # Classify actual executed route from observed actions
    tcs = tr["tool_calls"]
    if timed_out:
        exec_route = "timeout"
    elif job_id is not None:
        exec_route = "local_delegate"
    elif any("digest_" in x or "extract_from_file" in x for x in tcs):
        exec_route = "local_digest"
    elif any(x == "run_command" for x in tcs):
        exec_route = "deterministic_cmd"
    elif tr["verified"]:
        exec_route = "direct_or_targeted"
    else:
        exec_route = "non verificato"

    return {
        "case_id": case["id"],
        "family": case["family"],
        "mode": mode,
        "policy": policy,
        "budget_s": budget_s,
        "planner_deadline_s": planner_deadline_s,
        "artifact_correct": ev["correct"],
        "delivered_in_budget": in_budget,
        "completed_in_budget": in_budget,
        "success_in_budget": bool(ev["correct"] and in_budget),
        "timed_out": timed_out,
        "timeout_source": timeout_source,
        "wall_seconds": elapsed,
        "cloud_tokens": cloud_tokens,
        "cloud_usage_scope": "session_aggregate" if cloud_tokens is not None else "missing",
        "cloud_turns": tr["cloud_turns"] or num_turns,
        "first_action": tr["first_action"],
        "tool_calls": tcs,
        "job_id": job_id,
        "job_state": job_state,
        "local_inferences": local_infs,
        "local_tokens": local_tokens,
        "router_recommendation": (decisions[-1] or {}).get("route") if decisions else None,
        "executed_route": exec_route,
        "fallback": "none",
        "reason": ev["reason"],
        "workspace": str(ws),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    cases = [c for c in suite_def.CASES if c["split"] == "eval_v2"]
    if args.smoke:
        cases = [c for c in cases if c["id"] == "eval2_extract_csv_sum"]

    tag = "smoke" if args.smoke else "eval_v2"
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + f"_auto_{tag}"
    run_dir = SUITE_ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    orders = [
        ["A_direct", "B_auto_mandatory", "C_auto_first_turn"],
        ["B_auto_mandatory", "C_auto_first_turn", "A_direct"],
        ["C_auto_first_turn", "A_direct", "B_auto_mandatory"],
    ]
    records = []
    try:
        for idx, case in enumerate(cases):
            for mode in orders[idx % len(orders)]:
                print(f"[{run_id}] {case['id']} ({case['family']}) -> {mode}...", flush=True)
                rec = run_attempt(case, mode, run_dir)
                records.append(rec)
                print(
                    f"  -> ok_budget={rec['success_in_budget']} art={rec['artifact_correct']} first={rec['first_action']} "
                    f"exec={rec['executed_route']} turns={rec['cloud_turns']} cloud={rec['cloud_tokens']} "
                    f"local={rec['local_tokens']} wall={rec['wall_seconds']}s",
                    flush=True,
                )
                payload = {
                    "run_id": run_id,
                    "split": tag,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "models": {"cloud": ORCHESTRATOR_MODEL, "local": EXECUTOR_MODEL},
                    "frozen_sha256": {
                        "server.py": sha(REPO_ROOT / "tandem_mcp/server.py"),
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
