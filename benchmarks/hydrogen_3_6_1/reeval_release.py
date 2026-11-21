#!/usr/bin/env python3
"""Re-evaluate the release benchmark runs with the current behavioral evaluators.

Every workspace is evaluated REPEATS times; an attempt counts as a success only when every
repetition passes and the attempt finished inside its time budget. Writes a JSON report with
the evaluator SHA-256 so the verdicts can be reproduced.

Usage: python reeval_release.py <out.json> <run_dir> [<run_dir> ...]
"""
from __future__ import annotations

import hashlib
import json
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPEATS = 3
EVALUATORS = {
    "gen_orbital": ROOT / "check_orbital_behavioral.mjs",
    "gen_portal": ROOT / "check_portal_behavioral.mjs",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate_once(task: str, ws: Path) -> dict:
    proc = subprocess.run(["node", str(EVALUATORS[task]), str(ws)], capture_output=True, text=True, timeout=120)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"passed": False, "failed": ["evaluator_error"], "error": (proc.stderr or proc.stdout)[-300:]}
    if task == "gen_orbital":
        failed = [k for k, v in data.get("requirements", {}).items() if v.get("status") != "Pass"]
        return {"passed": bool(data.get("passed")), "failed": failed}
    failed = [k for k in ("startup", "canvasMotion", "interactions") if (data.get(k) or {}).get("status") != "passed"]
    if not data.get("visual_passed"):
        failed.append("visual")
    passed = bool(data.get("functional_passed")) and bool(data.get("visual_passed"))
    return {"passed": passed, "failed": failed, "interactions": (data.get("interactions") or {}).get("evidence", "")[-200:]}


def cloud_tokens(result: dict) -> int | None:
    calls = result.get("cloud_calls") or []
    if not calls or any((c.get("usage") or {}).get("total_tokens") is None for c in calls):
        return None
    return sum(c["usage"]["total_tokens"] for c in calls)


def usage_parts(result: dict) -> dict:
    """Input, output and cache-read tokens of an attempt: output usually costs several times more than input."""
    parts = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0}
    for c in result.get("cloud_calls") or []:
        for k in parts:
            parts[k] += int((c.get("usage") or {}).get(k) or 0)
    return parts


def main() -> int:
    out = Path(sys.argv[1])
    attempts = []
    for run_dir in map(Path, sys.argv[2:]):
        payload = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
        for r in payload["results"]:
            task = r["task_id"]
            ws = Path(r["workspace"])
            verdicts = [evaluate_once(task, ws) for _ in range(REPEATS)]
            all_pass = all(v["passed"] for v in verdicts)
            agree = len({v["passed"] for v in verdicts}) == 1
            attempts.append({
                "run": run_dir.name,
                "task": task,
                "mode": r["mode"],
                "timed_out": bool(r.get("timed_out")),
                "success": all_pass and not r.get("timed_out"),
                "verdicts_agree": agree,
                "failed_checks": sorted({f for v in verdicts for f in v["failed"]}),
                "wall_seconds": r.get("wall_seconds"),
                "cloud_tokens": cloud_tokens(r),
                "local_tokens": r.get("local_tokens") or 0,
                "cloud_parts": usage_parts(r),
                "fallback_used": bool(r.get("fallback_used")),
                "stored_e2e": r.get("e2e_success"),
            })
            a = attempts[-1]
            print(f"{a['run'][:15]} {task:11} {a['mode']:20} success={a['success']} agree={agree} "
                  f"cloud={a['cloud_tokens']} wall={a['wall_seconds']} failed={a['failed_checks']}", flush=True)

    summary = {}
    for key in sorted({(a["task"], a["mode"]) for a in attempts}):
        rows = [a for a in attempts if (a["task"], a["mode"]) == key]
        ok = [a for a in rows if a["success"]]
        cloud = [a["cloud_tokens"] for a in rows]
        cloud_total = None if any(c is None for c in cloud) else sum(cloud)
        summary[f"{key[0]}/{key[1]}"] = {
            "attempts": len(rows),
            "successes": len(ok),
            "cloud_tokens_total": cloud_total,
            "cloud_tokens_per_success": round(cloud_total / len(ok)) if ok and cloud_total is not None else None,
            "local_tokens_total": sum(a["local_tokens"] for a in rows),
            "cloud_parts_total": {k: sum(a["cloud_parts"][k] for a in rows)
                                  for k in ("input_tokens", "output_tokens", "cache_read_tokens")},
            "fallbacks": sum(a["fallback_used"] for a in rows),
            "median_wall_seconds": round(statistics.median(a["wall_seconds"] for a in rows), 2),
            "wall_seconds_per_success": round(sum(a["wall_seconds"] for a in rows) / len(ok), 2) if ok else None,
        }

    report = {
        "reevaluated_at": datetime.now(timezone.utc).isoformat(),
        "repeats": REPEATS,
        "rule": "success = every repetition passes and the attempt did not time out",
        "evaluator_sha256": {p.name: sha256(p) for p in EVALUATORS.values()},
        "summary": summary,
        "attempts": attempts,
    }
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
