#!/usr/bin/env python3
"""Run ONE real paired Orbital comparison: Gemini direct vs Tandem host-managed."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(ROOT))

os.environ["TANDEM_PROFILE"] = "lean"
os.environ["TANDEM_WAIT_SECONDS"] = "0"

from evaluate import evaluate_attempt
from suite import EXECUTOR_MODEL, LM_STUDIO_URL, ORCHESTRATOR_MODEL, TASKS, prepare_workspace
from tandem_mcp import engine, host_runner, store


def _restore_agy_mcp() -> None:
    subprocess.run(
        [
            "agy", "mcp", "add", "tandem-mcp",
            "/home/ale/tools/tandem-mcp/.venv/bin/python",
            "/home/ale/tools/tandem-mcp/main.py",
        ],
        capture_output=True,
    )
    subprocess.run(["agy", "mcp", "enable", "tandem-mcp"], capture_output=True)


def run_direct_orbital(task: dict, run_dir: Path) -> dict:
    ws = run_dir / "workspaces" / "gen_orbital__direct__r1"
    prepare_workspace(task, ws)
    subprocess.run(["agy", "mcp", "disable", "tandem-mcp"], check=True, capture_output=True)
    t0 = time.monotonic()
    proc = subprocess.run(
        [
            "agy", "-p", task["direct_prompt"],
            "--model", ORCHESTRATOR_MODEL,
            "--output-format", "json",
            "--mode", "auto",
            "--dangerously-skip-permissions",
            "--disable-slash-commands",
        ],
        cwd=str(ws),
        capture_output=True,
        text=True,
        timeout=600,
    )
    elapsed = round(time.monotonic() - t0, 2)
    parsed = {}
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                pass
    ev = evaluate_attempt("gen_orbital", parsed.get("response", ""), ws)
    return {
        "mode": "direct",
        "e2e_success": bool(proc.returncode == 0 and parsed.get("status") == "SUCCESS" and ev["valid"]),
        "artifact_valid": ev["valid"],
        "eval_reason": ev["reason"],
        "wall_seconds": elapsed,
        "cloud_calls": [{"phase": "direct", "status": parsed.get("status"), "duration_seconds": parsed.get("duration_seconds"), "usage": parsed.get("usage") or {}, "conversation_id": parsed.get("conversation_id")}],
        "cloud_calls_during_wait": 0,
        "local_tokens": 0,
        "browser": ev.get("details", {}).get("browser"),
        "workspace": str(ws),
    }


def run_host_managed_orbital(task: dict, run_dir: Path) -> dict:
    ws = run_dir / "workspaces" / "gen_orbital__host_managed__r1"
    prepare_workspace(task, ws)
    tandem_home = run_dir / "tandem_homes" / "gen_orbital__host_managed__r1"
    tandem_home.mkdir(parents=True, exist_ok=True)

    # Point store & engine to isolated run tandem_home
    store.DATA = tandem_home
    store.JOBS = tandem_home / "jobs"
    store.CACHE = tandem_home / "cache"
    store.LEDGER = tandem_home / "ledger.jsonl"
    store.LESSONS = tandem_home / "lessons.jsonl"
    store.MODELS = tandem_home / "models.json"
    store.init()
    engine.connect(url=LM_STUDIO_URL, refresh=True)

    contract_sha = hashlib.sha256((ws / "animation.json").read_bytes()).hexdigest()
    plan_prompt = (
        f"Build Orbital animation in {ws.resolve()}. Call `delegate_contract` ONCE with "
        f"workspace={str(ws.resolve())!r}, contract_file='animation.json', sha256='{contract_sha}'. "
        "As soon as `delegate_contract` returns the running job ID, stop immediately and reply with that job ID "
        "(do NOT call job_status; the host process will wait for completion)."
    )

    uv, _th, mcp_url = host_runner.start_local_http_mcp()
    try:
        planner = host_runner.make_agy_planner(plan_prompt, ws, ORCHESTRATOR_MODEL, os.environ.copy(), timeout_s=180.0)
        res = host_runner.run_host_managed(
            cloud_planner_fn=planner,
            mcp_url=mcp_url,
            poll_interval_s=2.0,
            timeout_s=2400.0,
            review_on_failure=False,
        )
    finally:
        uv.should_exit = True

    ev = evaluate_attempt("gen_orbital", res.receipt, ws)
    return {
        "mode": "tandem_host_managed",
        "job_id": res.job_id,
        "job_state": res.state,
        "e2e_success": bool(res.state == "verified" and ev["valid"]),
        "artifact_valid": ev["valid"],
        "eval_reason": ev["reason"],
        "wall_seconds": res.wall_seconds,
        "wait_polls": res.wait_polls,
        "cloud_calls": [{k: v for k, v in c.items() if k not in ("stdout", "stderr")} for c in res.cloud_calls],
        "cloud_calls_during_wait": res.cloud_calls_during_wait,
        "local_tokens": res.local_tokens,
        "timed_out": res.timed_out,
        "cancelled": res.cancelled,
        "receipt": res.receipt,
        "browser": ev.get("details", {}).get("browser"),
        "workspace": str(ws),
    }


def main() -> int:
    task = next(t for t in TASKS if t["id"] == "gen_orbital")
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "_orbital_host"
    run_dir = ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    results = []
    try:
        print(f"[{run_id}] Running gen_orbital (direct)...", flush=True)
        r_dir = run_direct_orbital(task, run_dir)
        results.append(r_dir)
        print(f"  -> direct e2e={r_dir['e2e_success']} time={r_dir['wall_seconds']}s cloud={r_dir['cloud_calls'][0]['usage'].get('total_tokens')}", flush=True)

        print(f"[{run_id}] Running gen_orbital (tandem_host_managed)...", flush=True)
        r_hm = run_host_managed_orbital(task, run_dir)
        results.append(r_hm)
        c_tok = sum((c.get("usage") or {}).get("total_tokens") or 0 for c in r_hm["cloud_calls"])
        print(f"  -> host_managed e2e={r_hm['e2e_success']} time={r_hm['wall_seconds']}s cloud={c_tok} wait_cloud_calls={r_hm['cloud_calls_during_wait']} local={r_hm['local_tokens']} ({r_hm['eval_reason']})", flush=True)
    finally:
        _restore_agy_mcp()

    payload = {"run_id": run_id, "timestamp": datetime.now(timezone.utc).isoformat(), "results": results}
    (run_dir / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved {run_dir / 'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
