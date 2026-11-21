#!/usr/bin/env python3
"""Run counterbalanced direct vs Tandem pairs with Opus 5.5 as the orchestrator (Claude Code, `claude -p`).

Both arms run the same user request in a fresh workspace with the same isolated Claude Code setup:
no user or project settings, no slash commands, no user plugins or CLAUDE.md (`--setting-sources ""`),
permissions bypassed, and only the MCP servers given here (`--strict-mcp-config`).

- direct: no MCP server. Opus does the work itself.
- tandem: the Tandem MCP server in the autonomous profile, with a fresh TANDEM_HOME. The request gets the
  fixed suffix TANDEM_SUFFIX. `delegate` blocks while the local model works, so the wait costs no cloud tokens.

Cloud cost is read from the `result` event of `claude -p --output-format json`: `total_cost_usd` (list
prices, every model used in the run) and the token split (input, cache writes, cache reads, output).

Usage: python run_pair.py --tasks gen_orbital,py_discount --pairs 3 --tag name
"""
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

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))

from tasks import TASKS  # noqa: E402

MODEL = os.environ.get("BENCH_MODEL", "claude-opus-5-5")
EXECUTOR = os.environ.get("BENCH_EXECUTOR", "qwen3.8-27b@iq3_s")
LM_URL = os.environ.get("BENCH_LM_URL", "http://127.0.0.1:1234/v1")
PYTHON = str(REPO / ".venv" / "bin" / "python")
TANDEM_SUFFIX = "\n\nUsa Tandem."
LOCAL_RESERVE_S = 300          # the local job ends this much before the attempt budget, to leave time to answer


def git_sha() -> str:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "tandem_mcp"], cwd=REPO, capture_output=True, text=True).stdout
    return sha + ("+dirty" if dirty.strip() else "")


def snapshot_code(run_dir: Path) -> Path:
    """Freeze the Tandem code used by this run, so later edits to the repository do not change it."""
    dst = run_dir / "_tandem_code"
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(REPO / "tandem_mcp", dst / "tandem_mcp", ignore=shutil.ignore_patterns("__pycache__"))
    digest = hashlib.sha256()
    for p in sorted((dst / "tandem_mcp").rglob("*")):
        if p.is_file():
            digest.update(p.name.encode() + p.read_bytes())
    (dst / "SHA256").write_text(digest.hexdigest(), encoding="utf-8")
    return dst


def parse_stream(stdout: str) -> tuple[dict, list]:
    try:
        events = json.loads(stdout)
    except json.JSONDecodeError:
        events = []
        for line in stdout.splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    if isinstance(events, dict):
        events = [events]
    result = next((e for e in events if e.get("type") == "result"), {})
    return result, events


def tool_uses(events: list) -> list[str]:
    return [c.get("name") for e in events if e.get("type") == "assistant"
            for c in (e.get("message") or {}).get("content", []) if c.get("type") == "tool_use"]


def local_metrics(thome: Path) -> dict:
    jobs = []
    for jf in sorted((thome / "jobs").glob("*/job.json")) if (thome / "jobs").exists() else []:
        d = json.loads(jf.read_text(encoding="utf-8"))
        jobs.append({"id": d.get("id"), "state": d.get("state"), "tokens": d.get("tokens"), "repairs": d.get("repairs"),
                     "steps": d.get("steps"), "seconds": d.get("seconds"), "accepted": d.get("accepted"),
                     "verify": [str(v)[:400] for v in d.get("verify") or []],
                     "constraints": d.get("constraints"), "goal": d.get("goal")})
    return {"jobs": jobs, "local_tokens": sum(int(j.get("tokens") or 0) for j in jobs)}


def run_arm(task_id: str, arm: str, pair: int, run_dir: Path, code_dir: Path) -> dict:
    task = TASKS[task_id]
    tag = f"{task_id}__p{pair}__{arm}"
    ws = run_dir / "workspaces" / tag
    thome = run_dir / "tandem_homes" / tag
    shutil.rmtree(ws, ignore_errors=True)
    ws.mkdir(parents=True)
    if task.get("setup"):
        task["setup"](ws)
    budget = int(task["budget_s"])
    env = os.environ.copy()
    for k in list(env):
        if k.startswith("TANDEM_"):
            env.pop(k)
    prompt = task["prompt"]
    if arm == "tandem":
        thome.mkdir(parents=True, exist_ok=True)
        cfg = {"mcpServers": {"tandem": {
            "command": PYTHON, "args": ["-m", "tandem_mcp.server"], "timeout": (budget + 600) * 1000,
            "env": {"PYTHONPATH": str(code_dir), "TANDEM_HOME": str(thome), "TANDEM_PROFILE": "autonomous",
                    "TANDEM_BASE_URL": LM_URL, "TANDEM_MODEL": EXECUTOR,
                    "TANDEM_JOB_SECONDS": str(max(120, budget - LOCAL_RESERVE_S))},
        }}}
        env["MCP_TOOL_TIMEOUT"] = str((budget + 600) * 1000)
        prompt = prompt + TANDEM_SUFFIX
    else:
        cfg = {"mcpServers": {}}
    cfg_path = run_dir / f"mcp_{tag}.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    cmd = ["claude", "-p", prompt, "--model", MODEL, "--output-format", "json", "--strict-mcp-config",
           "--mcp-config", str(cfg_path), "--setting-sources", "", "--disable-slash-commands",
           "--dangerously-skip-permissions", "--max-budget-usd", "20"]
    t0 = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(cmd, cwd=ws, env=env, capture_output=True, text=True, timeout=budget + 900,
                              stdin=subprocess.DEVNULL)
        stdout, stderr = proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    wall = round(time.monotonic() - t0, 2)
    (run_dir / "transcripts").mkdir(exist_ok=True)
    (run_dir / "transcripts" / f"{tag}.json").write_text(stdout, encoding="utf-8")
    if stderr.strip():
        (run_dir / "transcripts" / f"{tag}.stderr.txt").write_text(stderr[-20000:], encoding="utf-8")
    result, events = parse_stream(stdout)
    ev = task["evaluate"](ws)
    usage = result.get("usage") or {}
    rec = {
        "task": task_id, "arm": arm, "pair": pair, "workspace": str(ws), "wall_seconds": wall,
        "budget_s": budget, "timed_out": timed_out or wall > budget, "is_error": result.get("is_error"),
        "num_turns": result.get("num_turns"), "total_cost_usd": result.get("total_cost_usd"),
        "usage": {k: usage.get(k) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
                                             "output_tokens")},
        "model_usage": result.get("modelUsage"), "tool_uses": tool_uses(events),
        "result_text": str(result.get("result") or "")[:1500],
        "evaluation": ev, "success": bool(ev.get("passed")) and not (timed_out or wall > budget),
    }
    if arm == "tandem":
        rec["local"] = local_metrics(thome)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=",".join(TASKS))
    ap.add_argument("--pairs", type=int, default=3)
    ap.add_argument("--first-pair", type=int, default=1)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + (f"_{args.tag}" if args.tag else "")
    run_dir = ROOT / "runs" / run_id
    run_dir.mkdir(parents=True)
    code_dir = snapshot_code(run_dir)
    meta = {"run_id": run_id, "started": datetime.now(timezone.utc).isoformat(), "model": MODEL, "executor": EXECUTOR,
            "git": git_sha(), "tandem_code_sha256": (code_dir / "SHA256").read_text(),
            "claude_version": subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip(),
            "tandem_suffix": TANDEM_SUFFIX, "records": []}
    out = run_dir / "results.json"
    for task_id in args.tasks.split(","):
        for pair in range(args.first_pair, args.first_pair + args.pairs):
            arms = ("direct", "tandem") if pair % 2 else ("tandem", "direct")
            for arm in arms:
                print(f"[{run_id}] {task_id} pair {pair} {arm} ...", flush=True)
                rec = run_arm(task_id, arm, pair, run_dir, code_dir)
                meta["records"].append(rec)
                out.write_text(json.dumps(meta, indent=2), encoding="utf-8")
                loc = rec.get("local", {})
                print(f"  -> {arm} success={rec['success']} cost=${rec['total_cost_usd']} turns={rec['num_turns']} "
                      f"wall={rec['wall_seconds']}s out={rec['usage'].get('output_tokens')} "
                      f"local={loc.get('local_tokens', 0)} jobs={[j['state'] for j in loc.get('jobs', [])]} "
                      f"tools={rec['tool_uses'][:12]} failed={rec['evaluation'].get('failed')}", flush=True)
    print(f"Saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
