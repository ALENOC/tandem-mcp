#!/usr/bin/env python3
"""Run ONE paired from-prompt comparison (no pre-built contract, no hidden test files in workspace):
Gemini direct vs Tandem host-managed (Gemini writes contract from scratch -> host waits locally)."""
from __future__ import annotations

import argparse
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
from suite import EXECUTOR_MODEL, LM_STUDIO_URL, ORCHESTRATOR_MODEL
from tandem_mcp import engine, host_runner, store


def evaluate_from_prompt(task_id: str, ws: Path) -> dict:
    """Run prompt-based behavioral & visual evaluator independent of DOM IDs and file split."""
    script = ROOT / ("check_orbital_behavioral.mjs" if task_id == "gen_orbital" else "check_portal_behavioral.mjs")
    proc = subprocess.run(["node", str(script), str(ws)], capture_output=True, text=True, timeout=60)
    raw = (proc.stdout or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "valid": False,
            "visual_passed": False,
            "reason": f"evaluator parse error (rc={proc.returncode}): {(proc.stderr or raw)[-250:]}",
            "details": {"status": "not_evaluated"},
        }
    if task_id == "gen_orbital":
        reqs = data.get("requirements") or {}
        valid = bool(data.get("passed"))
        vis_ok = reqs.get("starDistribution", {}).get("status") == "Pass"
        reason = "all behavioral and star distribution checks passed" if valid else "; ".join(
            f"{k}:{v.get('status')}" for k, v in reqs.items() if v.get("status") != "Pass"
        )
        return {"valid": valid, "visual_passed": vis_ok, "reason": reason, "details": data}

    valid = bool(data.get("functional_passed"))
    vis_ok = bool(data.get("visual_passed"))
    parts = [
        f"startup={data.get('startup', {}).get('status')}",
        f"motion={data.get('canvasMotion', {}).get('status')}",
        f"interactions={data.get('interactions', {}).get('status')}",
        f"visual={data.get('visual', {}).get('status')}",
    ]
    return {"valid": valid, "visual_passed": vis_ok, "reason": ", ".join(parts), "details": data}


def _collect_job_metrics(tandem_home: Path, job_id: str | None) -> dict:
    if not job_id:
        return {"repairs": 0, "rejected_run_commands": 0, "local_calls": 0, "first_runtime_pass_s": "non disponibile"}
    jdir = tandem_home / "jobs" / job_id
    jdata = json.loads((jdir / "job.json").read_text()) if (jdir / "job.json").is_file() else {}
    logs = json.loads((jdir / "log.json").read_text()) if (jdir / "log.json").is_file() else []
    rejected_runs = sum(
        1 for row in logs
        if row.get("tool") == "run" and "not in the allow list" in str(row.get("result", ""))
    )
    first_pass_ev = next(
        (row for row in logs
         if row.get("tool") == "tandem:web_check" and row.get("phase") == "verify" and row.get("exit") == 0),
        None,
    )
    first_pass_s = first_pass_ev.get("elapsed_s") if first_pass_ev else "non disponibile"
    ledger_p = tandem_home / "ledger.jsonl"
    local_calls = 0
    if ledger_p.is_file():
        for line in ledger_p.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("tool") == "delegate" and row.get("kind") == "llm":
                local_calls += 1
    return {
        "repairs": int(jdata.get("repairs") or 0),
        "rejected_run_commands": rejected_runs,
        "local_calls": local_calls,
        "first_runtime_pass_s": first_pass_s,
    }


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


def run_direct_from_prompt(task_id: str, prompt_text: str, timeout_s: float, run_dir: Path) -> dict:
    ws = run_dir / "workspaces" / f"{task_id}__direct_from_prompt"
    ws.mkdir(parents=True, exist_ok=True)
    subprocess.run(["agy", "mcp", "disable", "tandem-mcp"], check=True, capture_output=True)

    t0 = time.monotonic()
    timed_out = False
    stdout, stderr, rc = "", "", -1
    try:
        proc = subprocess.run(
            [
                "agy", "-p", prompt_text,
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

    ev = evaluate_from_prompt(task_id, ws)
    return {
        "mode": "direct_from_prompt",
        "task_id": task_id,
        "completed": (not timed_out) and rc == 0 and parsed.get("status") == "SUCCESS",
        "timed_out": timed_out,
        "artifact_valid": ev["valid"],
        "visual_passed": ev["visual_passed"],
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
        "behavioral": ev["details"],
        "workspace": str(ws),
    }


FALLBACK_RESERVE_S = 600.0


def _agy_direct_call(prompt: str, ws: Path, timeout_s: float) -> dict:
    """One direct agy turn with Tandem disabled (used by the direct fallback of the Tandem arm)."""
    subprocess.run(["agy", "mcp", "disable", "tandem-mcp"], capture_output=True)
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            ["agy", "-p", prompt, "--model", ORCHESTRATOR_MODEL, "--output-format", "json", "--mode", "auto",
             "--dangerously-skip-permissions", "--disable-slash-commands"],
            cwd=str(ws), capture_output=True, text=True, timeout=timeout_s,
        )
        stdout = proc.stdout or ""
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
    parsed = {}
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                pass
    return {"status": parsed.get("status", "ERROR"), "duration_seconds": round(time.monotonic() - t0, 2),
            "usage": parsed.get("usage") or {}, "conversation_id": parsed.get("conversation_id")}


def run_tandem_from_prompt(task_id: str, prompt_text: str, timeout_s: float, run_dir: Path,
                           fallback: bool = True) -> dict:
    ws = run_dir / "workspaces" / f"{task_id}__tandem_from_prompt"
    ws.mkdir(parents=True, exist_ok=True)
    tandem_home = run_dir / "tandem_homes" / f"{task_id}__tandem_from_prompt"
    tandem_home.mkdir(parents=True, exist_ok=True)

    store.DATA = tandem_home
    store.JOBS = tandem_home / "jobs"
    store.CACHE = tandem_home / "cache"
    store.LEDGER = tandem_home / "ledger.jsonl"
    store.LESSONS = tandem_home / "lessons.jsonl"
    store.MODELS = tandem_home / "models.json"
    store.init()
    engine.connect(url=LM_STUDIO_URL, refresh=True)

    write_targets = ["index.html"] if task_id == "gen_orbital" else ["index.html", "scene.js", "engine3d.js", "app.js"]
    plan_prompt = (
        f"Work in clean workspace: {ws.resolve()}\n\n"
        f"User request:\n{prompt_text}\n\n"
        "Use Tandem MCP (`delegate` or `delegate_many`) to have the local executor build this from scratch:\n"
        f"- Write only inside `write_globs={write_targets}` (do not write the deliverable files yourself).\n"
        "- Author clear, atomic `constraints` (<=160 chars each) covering the required behavior and visual design, "
        "plus a `tandem:ui_test` acceptance check that clicks every control and asserts its effect "
        "(`expect` moving/static, `text`, `color`), so the local executor repairs behaviour before you see it.\n"
        "- As soon as `delegate` / `delegate_many` returns the running job/batch ID, stop immediately and reply with that ID "
        "(do NOT call `job_status`; the host process will manage the wait locally)."
    )

    def _reviewer(job_id: str, receipt: str) -> dict:
        rev_prompt = (
            f"Tandem job `{job_id}` in `{ws.resolve()}` did not verify cleanly:\n{receipt}\n\n"
            "Call `job_continue(job_id=..., hint=...)` ONCE with a concise targeted fix hint, then stop immediately "
            "and reply with the job ID so the host can wait locally."
        )
        return host_runner.make_agy_planner(rev_prompt, ws, ORCHESTRATOR_MODEL, os.environ.copy(), timeout_s=180.0)("")

    uv, _th, mcp_url = host_runner.start_local_http_mcp()
    try:
        planner = host_runner.make_agy_planner(plan_prompt, ws, ORCHESTRATOR_MODEL, os.environ.copy(), timeout_s=180.0)
        def _fallback(job_id: str, receipt: str) -> dict:
            fb_prompt = (
                f"{prompt_text}\n\nA previous attempt in this folder failed its acceptance checks:\n"
                f"{receipt[-1500:]}\n\nWrite or fix the files yourself so every requirement holds."
            )
            return _agy_direct_call(fb_prompt, ws, FALLBACK_RESERVE_S)

        res = host_runner.run_host_managed(
            cloud_planner_fn=planner,
            mcp_url=mcp_url,
            cloud_reviewer_fn=_reviewer,
            poll_interval_s=2.0,
            timeout_s=timeout_s - (FALLBACK_RESERVE_S if fallback else 0.0),
            review_on_failure=True,
            cloud_fallback_fn=_fallback if fallback else None,
        )
        # If a review/continue happened and re-entered running, wait once more locally
        if res.state == "running" and res.job_id:
            res2 = host_runner.run_host_managed(
                attach_job_id=res.job_id,
                poll_interval_s=2.0,
                timeout_s=timeout_s,
                review_on_failure=False,
            )
            res.state = res2.state
            res.accepted = res2.accepted
            res.receipt = res2.receipt
            res.wait_polls += res2.wait_polls
            res.local_tokens = res2.local_tokens
            res.wall_seconds = round(res.wall_seconds + res2.wall_seconds, 2)
    finally:
        uv.should_exit = True

    # Save generated contract from job.json
    contract_saved = None
    if res.job_id:
        jdata = store.read_job(res.job_id) or {}
        contract_saved = {
            "job_id": res.job_id,
            "kind": jdata.get("kind"),
            "goal": jdata.get("goal"),
            "verify_commands": jdata.get("verify"),
            "constraints": jdata.get("constraints"),
            "tasks": jdata.get("tasks"),
        }
        (run_dir / f"{task_id}__generated_contract.json").write_text(json.dumps(contract_saved, indent=2), encoding="utf-8")

    ev = evaluate_from_prompt(task_id, ws)
    jm = _collect_job_metrics(tandem_home, res.job_id)
    import tandem_mcp
    return {
        "mode": "tandem_from_prompt",
        "task_id": task_id,
        "mcp_installation": str(Path(tandem_mcp.__file__).resolve()),
        "job_id": res.job_id,
        "job_state": res.state,
        "completed": res.state == "verified",
        "timed_out": res.wall_seconds > timeout_s,
        "local_timed_out": res.timed_out,
        "artifact_valid": ev["valid"],
        "visual_passed": ev["visual_passed"],
        "fallback_used": res.fallback_used,
        "e2e_success": bool((res.state == "verified" or res.fallback_used) and ev["valid"]),
        "eval_reason": ev["reason"],
        "wall_seconds": res.wall_seconds,
        "first_runtime_pass_s": jm["first_runtime_pass_s"],
        "repairs": jm["repairs"],
        "rejected_run_commands": jm["rejected_run_commands"],
        "local_calls": jm["local_calls"],
        "wait_polls": res.wait_polls,
        "cloud_calls": [{k: v for k, v in c.items() if k not in ("stdout", "stderr")} for c in res.cloud_calls],
        "cloud_calls_during_wait": res.cloud_calls_during_wait,
        "local_tokens": res.local_tokens,
        "behavioral": ev["details"],
        "generated_contract_path": str(run_dir / f"{task_id}__generated_contract.json") if contract_saved else None,
        "workspace": str(ws),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=["gen_orbital", "gen_portal"], default="gen_orbital")
    parser.add_argument("--skip-direct", action="store_true")
    parser.add_argument("--tag", default="")
    parser.add_argument("--no-fallback", action="store_true", help="measure the local path alone, no direct fallback")
    args = parser.parse_args()

    prompt_file = "orbital_prompt.txt" if args.task == "gen_orbital" else "portal_prompt.txt"
    prompt_text = (ROOT / "fixtures" / "generation" / prompt_file).read_text(encoding="utf-8").strip()
    timeout_s = 2400.0 if args.task == "gen_orbital" else 4200.0

    suffix = f"_{args.tag}" if args.tag else ""
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + f"_{args.task}_from_prompt{suffix}"
    run_dir = ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    results = []
    try:
        if not args.skip_direct:
            print(f"[{run_id}] Running {args.task} (direct_from_prompt)...", flush=True)
            r_dir = run_direct_from_prompt(args.task, prompt_text, 900.0, run_dir)
            results.append(r_dir)
            c_dir = sum((c.get("usage") or {}).get("total_tokens") or 0 for c in r_dir["cloud_calls"])
            print(f"  -> direct e2e={r_dir['e2e_success']} vis={r_dir['visual_passed']} time={r_dir['wall_seconds']}s cloud={c_dir} ({r_dir['eval_reason']})", flush=True)

        print(f"[{run_id}] Running {args.task} (tandem_from_prompt)...", flush=True)
        r_tan = run_tandem_from_prompt(args.task, prompt_text, timeout_s, run_dir, fallback=not args.no_fallback)
        results.append(r_tan)
        c_tan = sum((c.get("usage") or {}).get("total_tokens") or 0 for c in r_tan["cloud_calls"])
        print(f"  -> tandem e2e={r_tan['e2e_success']} vis={r_tan['visual_passed']} state={r_tan['job_state']} time={r_tan['wall_seconds']}s cloud={c_tan} wait_cloud={r_tan['cloud_calls_during_wait']} local={r_tan['local_tokens']} repairs={r_tan['repairs']} rejected_runs={r_tan['rejected_run_commands']} fallback={r_tan['fallback_used']} ({r_tan['eval_reason']})", flush=True)
    finally:
        _restore_agy_mcp()

    payload = {"run_id": run_id, "task": args.task, "timestamp": datetime.now(timezone.utc).isoformat(), "results": results}
    (run_dir / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Saved {run_dir / 'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
