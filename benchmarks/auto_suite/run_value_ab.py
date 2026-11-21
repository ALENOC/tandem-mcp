#!/usr/bin/env python3
"""Targeted 3-pair counterbalanced A/B benchmark: Direct Cloud (A) vs 'usa Tandem, privilegia il risparmio di token cloud' (B)."""
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

BOIDS_CHECKER = SUITE_ROOT / "check_boids_behavioral.mjs"

VALUE_CASES = [
    {
        "id": "py_cron_sched",
        "family": "python",
        "budget_s": 900.0,
        "prompt": (
            "Crea da zero cron_sched.py con parser e iteratore di espressioni cron a 5 campi "
            "(minuto, ora, giorno_mese, mese, giorno_settimana) supportando *, numeri, intervalli a-b, "
            "liste a,b,c, step */n e a-b/n, più la funzione next_runs(expr, start_dt, count=5) che restituisce "
            "i prossimi count datetime UTC successivi a start_dt, sollevando ValueError su espressioni non valide; "
            "aggiungi test_cron_sched.py con almeno 12 test unittest e verifica che python3 -m unittest -v test_cron_sched.py passi."
        ),
    },
    {
        "id": "web_boids_paused",
        "family": "web",
        "budget_s": 1200.0,
        "prompt": (
            "Crea da zero index.html con una simulazione HTML5 Canvas a tutto schermo (#070b14) di stormo Boids "
            "(separazione, allineamento, coesione) che parte in pausa con almeno 40 boids visibili, HUD glassmorphism "
            "(FPS, numero boids, velocità), pulsanti Play/Pause (parte mostrando Play), Step, Reset, "
            "slider velocità (0.5..3.0), e click sul canvas per aggiungere un nuovo boid. Zero dipendenze esterne e zero errori JavaScript."
        ),
    },
]


def eval_case(case_id: str, ws: Path) -> dict:
    if case_id == "py_cron_sched":
        try:
            p1 = subprocess.run("python3 -m unittest -v test_cron_sched.py", shell=True, cwd=ws, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return {"correct": False, "reason": "unittest timed out after 30s"}
        if p1.returncode != 0:
            return {"correct": False, "reason": f"unittest failed: {(p1.stderr or p1.stdout)[-250:]}"}
        extra = (
            "from datetime import datetime, timezone\n"
            "import pathlib, re\n"
            "from cron_sched import next_runs\n"
            "src = pathlib.Path('test_cron_sched.py').read_text(encoding='utf-8')\n"
            "assert len(re.findall(r'def\\s+test_', src)) >= 12, 'need >=12 unittest methods'\n"
            "r1 = next_runs('*/15 9-17 * * 1-5', datetime(2026, 11, 20, 8, 50, tzinfo=timezone.utc), 3)\n"
            "assert r1 == [datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc), datetime(2026, 11, 20, 9, 15, tzinfo=timezone.utc), datetime(2026, 11, 20, 9, 30, tzinfo=timezone.utc)], r1\n"
            "r2 = next_runs('0 10 * * 1-5', datetime(2026, 11, 20, 11, 0, tzinfo=timezone.utc), 1)\n"
            "assert r2 == [datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)], r2\n"
            "for bad in ('61 * * * *', '* * *', '0 25 * * *'):\n"
            "    try:\n"
            "        next_runs(bad, datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc), 1)\n"
            "        raise AssertionError(f'expected ValueError for {bad}')\n"
            "    except ValueError:\n"
            "        pass\n"
        )
        try:
            p2 = subprocess.run([sys.executable, "-c", extra], cwd=ws, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return {"correct": False, "reason": "independent check timed out after 30s"}
        if p2.returncode != 0:
            return {"correct": False, "reason": f"independent check failed: {(p2.stderr or p2.stdout)[-250:]}"}
        return {"correct": True, "reason": "all unit and independent checks passed"}

    try:
        p = subprocess.run(["node", str(BOIDS_CHECKER), str(ws)], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return {"correct": False, "reason": "boids checker timed out after 60s"}
    try:
        data = json.loads(p.stdout)
        return {"correct": bool(data.get("correct")), "reason": data.get("reason", ""), "checks": data.get("checks", {})}
    except Exception:
        return {"correct": False, "reason": f"boids checker error (rc={p.returncode}): {(p.stderr or p.stdout)[-300:]}"}


def run_one(case: dict, pair_idx: int, mode: str, run_dir: Path) -> dict:
    tag = f"{case['id']}__p{pair_idx}__{mode}"
    ws = run_dir / "workspaces" / tag
    thome = run_dir / "tandem_homes" / tag
    shutil.rmtree(ws, ignore_errors=True)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "README.txt").write_text(f"{case['id']} workspace\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=ws, check=True)

    budget_s = float(case["budget_s"])
    os.environ["TANDEM_AUTO_POLICY"] = "first_turn"
    os.environ["TANDEM_HOST_MANAGED"] = "1"
    os.environ["TANDEM_COMPACT_WRITES"] = "1"

    t0 = time.monotonic()
    timed_out = False
    timeout_source = "none"
    cloud_tokens = None
    num_turns = None
    conv_id = None
    first_action = None
    tool_calls = []
    job_id = None
    job_state = None
    executed_route = "direct"

    uv = None
    try:
        if mode == "A_direct":
            subprocess.run(["agy", "mcp", "disable", "tandem-mcp"], check=False, capture_output=True)
            prompt = case["prompt"]
        else:
            v2._init_tandem_home(thome)
            uv, _thr, mcp_url = host_runner.start_local_http_mcp()
            subprocess.run(["agy", "mcp", "add", "--type", "http", "tandem-mcp", mcp_url], check=True, capture_output=True)
            subprocess.run(["agy", "mcp", "enable", "tandem-mcp"], check=True, capture_output=True)
            prompt = f"usa Tandem, privilegia il risparmio di token cloud, posso aspettare: {case['prompt']}"

        plan_res = v2._run_agy_single(prompt, ws, budget_s)
        conv_id = plan_res.get("conversation_id")
        num_turns = plan_res.get("num_turns")
        if plan_res["usage"] and "total_tokens" in plan_res["usage"]:
            cloud_tokens = int(plan_res["usage"]["total_tokens"])
        timed_out = plan_res["timed_out"]
        if timed_out:
            timeout_source = "planner"

        if conv_id:
            tpath = Path.home() / f".gemini/antigravity-cli/brain/{conv_id}/.system_generated/logs/transcript.jsonl"
            if tpath.is_file():
                for line in tpath.read_text().splitlines():
                    for tc in (json.loads(line).get("tool_calls") or []):
                        tool_calls.append(tc.get("name") or tc.get("function", {}).get("name"))
            if tool_calls:
                first_action = tool_calls[0]

        if mode == "B_auto_save":
            jobs_dir = thome / "jobs"
            started_jobs = sorted([p.name for p in jobs_dir.iterdir() if p.is_dir()]) if jobs_dir.is_dir() else []
            if started_jobs:
                job_id = started_jobs[-1]
                jdata = json.loads((jobs_dir / job_id / "job.json").read_text())
                job_state = jdata.get("state")
                executed_route = "local_delegate" if not timed_out else "timeout"
            elif timed_out:
                executed_route = "timeout"
            else:
                executed_route = "direct_fallback_or_choice"

        wall = round(time.monotonic() - t0, 2)
        delivered_in_budget = (not timed_out) and (wall <= budget_s)
        ev = eval_case(case["id"], ws)

        local_inferences = 0
        local_tokens = 0
        repairs = 0
        if mode == "B_auto_save" and (thome / "ledger.jsonl").is_file():
            for line in (thome / "ledger.jsonl").read_text().splitlines():
                rec = json.loads(line)
                if rec.get("kind") == "llm" and rec.get("tool") != "probe":
                    local_inferences += 1
                    local_tokens += int(rec.get("prompt_tokens", 0)) + int(rec.get("completion_tokens", 0))
            if job_id:
                jdata = json.loads((thome / "jobs" / job_id / "job.json").read_text())
                repairs = int(jdata.get("repairs", 0))

        return {
            "case_id": case["id"],
            "family": case["family"],
            "pair": pair_idx,
            "mode": mode,
            "budget_s": budget_s,
            "artifact_correct": bool(ev["correct"]),
            "delivered_in_budget": delivered_in_budget,
            "success_in_budget": bool(ev["correct"]) and delivered_in_budget,
            "wall_seconds": wall,
            "timed_out": timed_out,
            "timeout_source": timeout_source,
            "cloud_tokens": cloud_tokens,
            "cloud_turns": num_turns,
            "local_inferences": local_inferences,
            "local_tokens": local_tokens,
            "repairs": repairs,
            "executed_route": executed_route,
            "first_action": first_action,
            "tool_calls": tool_calls,
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
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", type=str, default="")
    args = ap.parse_args()

    if args.resume:
        run_dir = Path(args.resume).resolve()
        existing = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
        run_id = existing["run_id"]
        records: list[dict] = list(existing["records"])
        frozen = existing["frozen_sha256"]
        done_keys = {(r["case_id"], r["pair"], r["mode"]) for r in records}
    else:
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S_value_ab")
        run_dir = SUITE_ROOT / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        frozen = {
            "run_value_ab.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "check_boids_behavioral.mjs": hashlib.sha256(BOIDS_CHECKER.read_bytes()).hexdigest(),
        }
        records = []
        done_keys = set()

    pair_orders = [("A_direct", "B_auto_save"), ("B_auto_save", "A_direct"), ("A_direct", "B_auto_save")]

    for case in VALUE_CASES:
        for pair_idx, order in enumerate(pair_orders, 1):
            for mode in order:
                if (case["id"], pair_idx, mode) in done_keys:
                    print(f"[SKIP] {case['id']} pair={pair_idx} mode={mode} already done", flush=True)
                    continue
                print(f"[RUN] {case['id']} pair={pair_idx} mode={mode}", flush=True)
                rec = run_one(case, pair_idx, mode, run_dir)
                records.append(rec)
                print(
                    f"[DONE] {case['id']} p{pair_idx} {mode}: art={rec['artifact_correct']} in_b={rec['delivered_in_budget']} "
                    f"wall={rec['wall_seconds']}s cloud={rec['cloud_tokens']} local={rec['local_tokens']} route={rec['executed_route']}",
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
