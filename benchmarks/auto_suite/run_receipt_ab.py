#!/usr/bin/env python3
"""3-pair counterbalanced comparison: B_cur (compact receipt OFF) vs B_mod (compact receipt ON) + A_direct reference."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import statistics
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
from suite import EXECUTOR_MODEL, ORCHESTRATOR_MODEL  # noqa: E402
from tandem_mcp import host_runner  # noqa: E402

PENDULUM_CHECKER = SUITE_ROOT / "check_pendulum_behavioral.mjs"
BUDGET_S = 1200.0
PROMPT = (
    "Crea da zero index.html con una simulazione HTML5 Canvas a tutto schermo (#090d16) di doppio pendolo caotico "
    "con scie sfumate che parte in pausa, HUD glassmorphism (FPS, energia o tempo, velocità), "
    "pulsanti Play/Pause (parte mostrando Play), Step, Reset, slider velocità (0.5..3.0), "
    "e click sul canvas per impostare un nuovo angolo iniziale. Zero dipendenze esterne e zero errori JavaScript."
)


def parse_transcript_metrics(conv_id: str | None) -> dict:
    if not conv_id:
        return {"in": None, "out": None, "cache": None, "turns": None, "rereads_post_watcher": 0, "tools": []}
    tpath = Path.home() / f".gemini/antigravity-cli/brain/{conv_id}/.system_generated/logs/transcript.jsonl"
    if not tpath.is_file():
        return {"in": None, "out": None, "cache": None, "turns": None, "rereads_post_watcher": 0, "tools": []}
    tin = tout = tcache = turns = rereads = 0
    seen_watcher = False
    tools = []
    for line in tpath.read_text().splitlines():
        rec = json.loads(line)
        c = rec.get("content") or ""
        if "HOST_MANAGED_RESULT" in c:
            seen_watcher = True
        if rec.get("source") == "MODEL" and rec.get("type") == "PLANNER_RESPONSE":
            tin += int(rec.get("input_tokens") or 0)
            tout += int(rec.get("output_tokens") or 0)
            tcache += int(rec.get("cache_read_tokens") or 0)
            turns += 1
            for tc in (rec.get("tool_calls") or []):
                name = tc.get("name") or tc.get("function", {}).get("name")
                tools.append(name)
                if seen_watcher and name == "read_file":
                    rereads += 1
    return {"in": tin, "out": tout, "cache": tcache, "turns": turns, "rereads_post_watcher": rereads, "tools": tools}


def run_one(pair_idx: int, mode: str, run_dir: Path) -> dict:
    tag = f"web_pendulum__p{pair_idx}__{mode}"
    ws = run_dir / "workspaces" / tag
    thome = run_dir / "tandem_homes" / tag
    shutil.rmtree(ws, ignore_errors=True)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "README.txt").write_text("Double pendulum canvas simulation.\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=ws, check=True)

    os.environ["TANDEM_AUTO_POLICY"] = "first_turn"
    os.environ["TANDEM_HOST_MANAGED"] = "1"
    os.environ["TANDEM_COMPACT_WRITES"] = "1"
    os.environ["TANDEM_COMPACT_RECEIPT"] = "0" if mode == "B_cur" else "1"

    t0 = time.monotonic()
    uv = None
    timed_out = False
    timeout_source = "none"
    cloud_tokens = None
    conv_id = None
    job_id = None
    job_state = None
    executed_route = "direct"

    try:
        if mode == "A_direct":
            subprocess.run(["agy", "mcp", "disable", "tandem-mcp"], check=False, capture_output=True)
            prompt = PROMPT
        else:
            v2._init_tandem_home(thome)
            uv, _thr, mcp_url = host_runner.start_local_http_mcp()
            subprocess.run(["agy", "mcp", "add", "--type", "http", "tandem-mcp", mcp_url], check=True, capture_output=True)
            subprocess.run(["agy", "mcp", "enable", "tandem-mcp"], check=True, capture_output=True)
            prompt = f"usa Tandem, privilegia il risparmio di token cloud, posso aspettare: {PROMPT}"

        plan_res = v2._run_agy_single(prompt, ws, BUDGET_S)
        conv_id = plan_res.get("conversation_id")
        if plan_res["usage"] and "total_tokens" in plan_res["usage"]:
            cloud_tokens = int(plan_res["usage"]["total_tokens"])
        timed_out = plan_res["timed_out"]
        if timed_out:
            timeout_source = "planner"

        tm = parse_transcript_metrics(conv_id)
        if mode != "A_direct":
            jobs_dir = thome / "jobs"
            started = sorted([p.name for p in jobs_dir.iterdir() if p.is_dir()]) if jobs_dir.is_dir() else []
            if started:
                job_id = started[-1]
                job_state = json.loads((jobs_dir / job_id / "job.json").read_text()).get("state")
                executed_route = "local_delegate" if not timed_out else "timeout"
            else:
                executed_route = "timeout" if timed_out else "direct_fallback"

        wall = round(time.monotonic() - t0, 2)
        delivered_in_budget = (not timed_out) and (wall <= BUDGET_S)
        p_ev = subprocess.run(["node", str(PENDULUM_CHECKER), str(ws)], capture_output=True, text=True, timeout=60)
        try:
            ev = json.loads(p_ev.stdout)
        except Exception:
            ev = {"correct": False, "reason": f"checker error rc={p_ev.returncode}"}

        local_inferences = 0
        local_tokens = 0
        repairs = 0
        if mode != "A_direct" and (thome / "ledger.jsonl").is_file():
            for line in (thome / "ledger.jsonl").read_text().splitlines():
                rec = json.loads(line)
                if rec.get("kind") == "llm" and rec.get("tool") != "probe":
                    local_inferences += 1
                    local_tokens += int(rec.get("prompt_tokens", 0)) + int(rec.get("completion_tokens", 0))
            if job_id:
                repairs = int(json.loads((thome / "jobs" / job_id / "job.json").read_text()).get("repairs", 0))

        return {
            "pair": pair_idx,
            "mode": mode,
            "budget_s": BUDGET_S,
            "artifact_correct": bool(ev.get("correct")),
            "delivered_in_budget": delivered_in_budget,
            "success_in_budget": bool(ev.get("correct")) and delivered_in_budget,
            "wall_seconds": wall,
            "timed_out": timed_out,
            "timeout_source": timeout_source,
            "cloud_tokens": cloud_tokens,
            "cloud_in": tm["in"],
            "cloud_out": tm["out"],
            "cloud_cache": tm["cache"],
            "cloud_turns": tm["turns"],
            "rereads_post_watcher": tm["rereads_post_watcher"],
            "local_inferences": local_inferences,
            "local_tokens": local_tokens,
            "repairs": repairs,
            "executed_route": executed_route,
            "tools": tm["tools"],
            "job_id": job_id,
            "job_state": job_state,
            "conversation_id": conv_id,
            "reason": ev.get("reason", ""),
            "workspace": str(ws),
        }
    finally:
        if uv is not None:
            uv.should_exit = True
        v2._restore_agy_mcp()


def main() -> int:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S_receipt_ab")
    run_dir = SUITE_ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    frozen = {
        "run_receipt_ab.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "check_pendulum_behavioral.mjs": hashlib.sha256(PENDULUM_CHECKER.read_bytes()).hexdigest(),
    }
    orders = [
        ("B_cur", "B_mod", "A_direct"),
        ("B_mod", "B_cur", "A_direct"),
        ("B_cur", "B_mod", "A_direct"),
    ]
    records = []
    for pair_idx, order in enumerate(orders, 1):
        for mode in order:
            print(f"[RUN] p{pair_idx} {mode}", flush=True)
            rec = run_one(pair_idx, mode, run_dir)
            records.append(rec)
            print(
                f"[DONE] p{pair_idx} {mode}: art={rec['artifact_correct']} in_b={rec['delivered_in_budget']} "
                f"wall={rec['wall_seconds']}s cloud={rec['cloud_tokens']} (in={rec['cloud_in']}, out={rec['cloud_out']}) "
                f"rereads={rec['rereads_post_watcher']} local={rec['local_tokens']}",
                flush=True,
            )
            (run_dir / "results.json").write_text(
                json.dumps({
                    "run_id": run_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "models": {"cloud": ORCHESTRATOR_MODEL, "local": EXECUTOR_MODEL},
                    "frozen_sha256": frozen,
                    "records": records,
                }, indent=2) + "\n",
                encoding="utf-8",
            )
    print(f"Saved: {run_dir / 'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
