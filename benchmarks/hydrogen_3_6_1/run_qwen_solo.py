#!/usr/bin/env python3
"""Run Qwen3.8 27B alone (no cloud orchestrator) on gen_orbital and gen_portal (n=3)."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(ROOT))

from evaluate import evaluate_attempt
from suite import EXECUTOR_MODEL, LM_STUDIO_URL, TASKS, prepare_workspace
from tandem_mcp import agent, engine, sandbox, store


def run_qwen_task(task: dict, repeat: int, run_dir: Path) -> dict:
    attempt_id = f"{task['id']}__qwen_solo__r{repeat}"
    workspace = run_dir / "workspaces" / attempt_id
    prepare_workspace(task, workspace)

    t0 = time.monotonic()
    ws = sandbox.Workspace(
        str(workspace),
        write_globs=["index.html", "scene.js", "engine3d.js", "app.js"],
        allow_run=[r"^node\b"],
    )
    job_id = agent.start(
        goal=task["direct_prompt"],
        workspace=ws,
        verify=[],
        max_steps=30,
        max_repairs=0,
        model=EXECUTOR_MODEL,
        context="",
        baseline=False,
        max_seconds=task["timeout_s"],
        require_proof=False,
    )
    agent.RUNNING[job_id][0].join(float(task["timeout_s"]) + 30.0)
    elapsed = round(time.monotonic() - t0, 2)
    jdata = store.read_job(job_id) or {}
    completed = jdata.get("state") in ("verified", "unverified")
    timed_out = jdata.get("state") == "timeout"

    ev = evaluate_attempt(task["id"], jdata.get("summary") or "", workspace)
    return {
        "attempt_id": attempt_id,
        "task_id": task["id"],
        "scenario": "qwen_solo",
        "repeat": repeat,
        "completed": completed,
        "timed_out": timed_out,
        "state": jdata.get("state"),
        "steps": jdata.get("steps"),
        "artifact_valid": ev["valid"],
        "eval_reason": ev["reason"],
        "e2e_success": bool(completed and ev["valid"]),
        "wall_seconds": elapsed,
        "local_total_tokens": jdata.get("tokens", 0),
        "browser_details": ev.get("details", {}).get("browser"),
    }


def main() -> int:
    engine.connect(url=LM_STUDIO_URL, refresh=True)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "_qwen_solo"
    run_dir = ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    target_tasks = [t for t in TASKS if t["id"] in ("gen_orbital", "gen_portal")]
    attempts = []
    for rep in range(1, 4):
        for task in target_tasks:
            print(f"[{run_id}] Running {task['id']} (qwen_solo, r{rep})...", flush=True)
            res = run_qwen_task(task, rep, run_dir)
            attempts.append(res)
            print(
                f"  -> e2e={res['e2e_success']} state={res['state']} time={res['wall_seconds']}s "
                f"local={res['local_total_tokens']} ({res['eval_reason']})",
                flush=True,
            )
    payload = {"run_id": run_id, "executor": EXECUTOR_MODEL, "timestamp": datetime.now(timezone.utc).isoformat(), "attempts": attempts}
    (run_dir / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved {run_dir / 'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
