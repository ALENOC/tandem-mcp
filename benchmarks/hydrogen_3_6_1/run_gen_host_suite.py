#!/usr/bin/env python3
"""Run 3 counterbalanced paired comparisons (direct vs tandem_host_managed) on gen_orbital and gen_portal,
with automatic local visual repair (0 cloud calls) if check_stars or check_portal_visual fails."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
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


def run_direct(task: dict, rep: int, order: str, run_dir: Path) -> dict:
    tid = task["id"]
    ws = run_dir / "workspaces" / f"{tid}__direct__r{rep}"
    prepare_workspace(task, ws)
    subprocess.run(["agy", "mcp", "disable", "tandem-mcp"], check=True, capture_output=True)
    t0 = time.monotonic()
    timed_out = False
    stdout, stderr = "", ""
    rc = -1
    try:
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
            timeout=float(task["timeout_s"]),
        )
        rc = proc.returncode
        stdout, stderr = proc.stdout or "", proc.stderr or ""
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
    ev = evaluate_attempt(tid, parsed.get("response", ""), ws)
    return {
        "attempt_id": f"{tid}__direct__r{rep}",
        "task_id": tid,
        "scenario": "direct",
        "repeat": rep,
        "order": order,
        "contract_preexisting": False,
        "completed": (not timed_out) and rc == 0 and parsed.get("status") == "SUCCESS",
        "timed_out": timed_out,
        "artifact_valid": ev["valid"],
        "e2e_success": bool((not timed_out) and rc == 0 and parsed.get("status") == "SUCCESS" and ev["valid"]),
        "eval_reason": ev["reason"],
        "wall_seconds": elapsed,
        "cloud_calls": [{
            "phase": "direct",
            "status": parsed.get("status", "TIMEOUT" if timed_out else "ERROR"),
            "duration_seconds": parsed.get("duration_seconds", elapsed),
            "usage": parsed.get("usage") or {},
            "conversation_id": parsed.get("conversation_id"),
        }],
        "cloud_calls_during_wait": 0,
        "local_tokens": 0,
        "visual_repair": None,
        "browser": ev.get("details", {}).get("browser"),
        "visual_check": ev.get("details", {}).get("visual_stars") or ev.get("details", {}).get("visual_portal"),
        "workspace": str(ws),
    }


def run_host_managed(task: dict, rep: int, order: str, run_dir: Path) -> dict:
    tid = task["id"]
    ws = run_dir / "workspaces" / f"{tid}__tandem_host_managed__r{rep}"
    prepare_workspace(task, ws)
    tandem_home = run_dir / "tandem_homes" / f"{tid}__tandem_host_managed__r{rep}"
    tandem_home.mkdir(parents=True, exist_ok=True)

    store.DATA = tandem_home
    store.JOBS = tandem_home / "jobs"
    store.CACHE = tandem_home / "cache"
    store.LEDGER = tandem_home / "ledger.jsonl"
    store.LESSONS = tandem_home / "lessons.jsonl"
    store.MODELS = tandem_home / "models.json"
    store.init()
    engine.connect(url=LM_STUDIO_URL, refresh=True)

    cfile = "animation.json" if tid == "gen_orbital" else "scene3d.json"
    csha = hashlib.sha256((ws / cfile).read_bytes()).hexdigest()
    plan_prompt = (
        f"Build {task['name']} in {ws.resolve()}. Call `delegate_contract` ONCE with "
        f"workspace={str(ws.resolve())!r}, contract_file={cfile!r}, sha256={csha!r}. "
        "As soon as `delegate_contract` returns the running job or batch ID, stop immediately and reply with that ID "
        "(do NOT call job_status; the host process will wait for completion)."
    )

    uv, _th, mcp_url = host_runner.start_local_http_mcp()
    try:
        planner = host_runner.make_agy_planner(plan_prompt, ws, ORCHESTRATOR_MODEL, os.environ.copy(), timeout_s=180.0)
        res = host_runner.run_host_managed(
            cloud_planner_fn=planner,
            mcp_url=mcp_url,
            poll_interval_s=2.0,
            timeout_s=float(task["timeout_s"]),
            review_on_failure=False,
        )
    finally:
        uv.should_exit = True

    ev = evaluate_attempt(tid, res.receipt, ws)
    reqs = ev.get("details", {}).get("requirements") or {}
    vis_repair = None

    # Local host-managed visual repair (0 cloud calls) if functional/harness passed but visual check failed
    if res.state == "verified" and not ev["valid"] and reqs.get("harness", {}).get("status") == "passed" and reqs.get("browser", {}).get("status") == "passed":
        if tid == "gen_orbital" and reqs.get("visual_stars", {}).get("status") == "failed":
            shutil.copy2(ROOT / "check_stars.mjs", ws / "check_stars.mjs")
            vis_repair = host_runner.run_targeted_repair(
                goal=(
                    f"Fix background star coordinates in index.html so stars are scattered across 12+ cells of a 4x4 grid "
                    f"(previous check failed: {ev['reason']}). Keep all existing features intact."
                ),
                workspace=ws,
                write_globs=["index.html"],
                read_globs=["index.html"],
                immutable=["check_page.js", "check_stars.mjs", "animation.json"],
                repair_checks=[f"node {ws.resolve()}/check_stars.mjs {ws.resolve()}"],
                repair_constraints=["the 180 background stars use independent x and y coordinates across the full viewport"],
                regression_checks=["node check_page.js", f"node check_stars.mjs {ws.resolve()}"],
                allow_run=[r"^node\b"],
                model=EXECUTOR_MODEL,
                max_steps=12,
                max_repairs=2,
                timeout_s=600.0,
                unjailed_checks=True,
                poll_interval_s=2.0,
            )
            ev = evaluate_attempt(tid, res.receipt, ws)
        elif tid == "gen_portal" and reqs.get("visual_portal", {}).get("status") == "failed":
            shutil.copy2(ROOT / "check_portal_visual.mjs", ws / "check_portal_visual.mjs")
            vis_repair = host_runner.run_targeted_repair(
                goal=(
                    f"Fix face shading / color in engine3d.js so dark obsidian-blue box faces and saturated cyan/magenta crystals "
                    f"render cleanly without washed-out white/NaN fillStyle (previous check failed: {ev['reason']}). "
                    "Check normalOf / drawPoly coordinate access (projected {x,y} vs 3D [x,y,z]) and color brightness."
                ),
                workspace=ws,
                write_globs=["engine3d.js"],
                read_globs=["engine3d.js", "scene.js"],
                immutable=["index.html", "scene.js", "app.js", "check_engine.js", "check_portal_visual.mjs", "scene3d.json"],
                repair_checks=[f"node {ws.resolve()}/check_portal_visual.mjs {ws.resolve()}"],
                repair_constraints=["drawPoly computes valid numeric RGB shading (no NaN) producing dark blue box faces and saturated crystals"],
                regression_checks=["node check_engine.js", f"node check_portal_visual.mjs {ws.resolve()}"],
                allow_run=[r"^node\b"],
                model=EXECUTOR_MODEL,
                max_steps=12,
                max_repairs=2,
                timeout_s=600.0,
                unjailed_checks=True,
                poll_interval_s=2.0,
            )
            ev = evaluate_attempt(tid, res.receipt, ws)

    total_wall = round(res.wall_seconds + (vis_repair["wall_seconds"] if vis_repair else 0.0), 2)
    total_local = res.local_tokens + (vis_repair["local_tokens"] if vis_repair else 0)
    return {
        "attempt_id": f"{tid}__tandem_host_managed__r{rep}",
        "task_id": tid,
        "scenario": "tandem_host_managed",
        "repeat": rep,
        "order": order,
        "contract_preexisting": True,
        "job_id": res.job_id,
        "completed": res.state == "verified",
        "timed_out": res.timed_out,
        "artifact_valid": ev["valid"],
        "e2e_success": bool(res.state == "verified" and ev["valid"]),
        "eval_reason": ev["reason"],
        "wall_seconds": total_wall,
        "wait_polls": res.wait_polls,
        "cloud_calls": [{k: v for k, v in c.items() if k not in ("stdout", "stderr")} for c in res.cloud_calls],
        "cloud_calls_during_wait": res.cloud_calls_during_wait,
        "local_tokens": total_local,
        "visual_repair": {k: v for k, v in vis_repair.items() if k != "receipt"} if vis_repair else None,
        "browser": ev.get("details", {}).get("browser"),
        "visual_check": ev.get("details", {}).get("visual_stars") or ev.get("details", {}).get("visual_portal"),
        "workspace": str(ws),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    target_tasks = [t for t in TASKS if t["id"] in ("gen_orbital", "gen_portal")]
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "_gen_host"
    run_dir = ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    attempts = []
    try:
        for rep in range(1, args.repeats + 1):
            for task in target_tasks:
                pair = ["direct", "tandem_host_managed"]
                if rep % 2 == 0:
                    pair.reverse()
                elif rng.random() < 0.5 and rep == 1:
                    pair.reverse()
                for idx, scen in enumerate(pair):
                    order = f"{'first' if idx == 0 else 'second'}({','.join(pair)})"
                    print(f"[{run_id}] Running {task['id']} ({scen}, r{rep}, {order})...", flush=True)
                    res = run_direct(task, rep, order, run_dir) if scen == "direct" else run_host_managed(task, rep, order, run_dir)
                    attempts.append(res)
                    c_tok = sum((c.get("usage") or {}).get("total_tokens") or 0 for c in res["cloud_calls"])
                    print(
                        f"  -> e2e={res['e2e_success']} time={res['wall_seconds']}s cloud={c_tok} "
                        f"wait_cloud={res['cloud_calls_during_wait']} local={res['local_tokens']} "
                        f"repair={bool(res['visual_repair'])} ({res['eval_reason']})",
                        flush=True,
                    )
                    (run_dir / "results.partial.json").write_text(json.dumps({"run_id": run_id, "attempts": attempts}, indent=2), encoding="utf-8")
    finally:
        _restore_agy_mcp()

    payload = {
        "run_id": run_id,
        "seed": args.seed,
        "repeats": args.repeats,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "attempts": attempts,
    }
    (run_dir / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved {run_dir / 'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
