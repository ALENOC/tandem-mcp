#!/usr/bin/env python3
"""Re-evaluate every artifact of one or more runs REPEATS times and summarize cost per success.

An attempt succeeds only when every repetition passes and it ended inside its budget. The report records
the evaluator SHA-256 so the verdicts can be reproduced.

Usage: python reeval.py <out.json> <run_dir> [<run_dir> ...]
"""
from __future__ import annotations

import hashlib
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from tasks import TASKS  # noqa: E402

REPEATS = 3
TOKEN_KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")


def main() -> int:
    out = Path(sys.argv[1])
    attempts = []
    for run_dir in map(Path, sys.argv[2:]):
        payload = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
        for r in payload["records"]:
            ws = Path(r["workspace"])
            verdicts = [TASKS[r["task"]]["evaluate"](ws) for _ in range(REPEATS)]
            passed = all(v.get("passed") for v in verdicts)
            a = {
                "run": run_dir.name, "task": r["task"], "arm": r["arm"], "pair": r["pair"],
                "success": passed and not r.get("timed_out"), "verdicts_agree": len({bool(v.get("passed")) for v in verdicts}) == 1,
                "failed_checks": sorted({f for v in verdicts for f in v.get("failed") or []}),
                "timed_out": bool(r.get("timed_out")), "wall_seconds": r["wall_seconds"],
                "cost_usd": r.get("total_cost_usd"), "usage": r.get("usage") or {}, "num_turns": r.get("num_turns"),
                "tool_uses": r.get("tool_uses"), "local_tokens": (r.get("local") or {}).get("local_tokens", 0),
                "local_jobs": [j.get("state") for j in (r.get("local") or {}).get("jobs", [])],
            }
            attempts.append(a)
            print(f"{a['task']:12} p{a['pair']} {a['arm']:7} success={a['success']} agree={a['verdicts_agree']} "
                  f"cost={a['cost_usd']} wall={a['wall_seconds']} failed={a['failed_checks']}", flush=True)

    summary = {}
    for task in sorted({a["task"] for a in attempts}):
        row = {}
        for arm in ("direct", "tandem"):
            rows = [a for a in attempts if a["task"] == task and a["arm"] == arm]
            if not rows:
                continue
            ok = sum(a["success"] for a in rows)
            costs = [a["cost_usd"] for a in rows]
            total = None if any(c is None for c in costs) else round(sum(costs), 4)
            row[arm] = {
                "attempts": len(rows), "successes": ok, "cost_usd_total": total,
                "cost_usd_per_success": round(total / ok, 4) if ok and total is not None else None,
                "tokens_total": {k: sum(int(a["usage"].get(k) or 0) for a in rows) for k in TOKEN_KEYS},
                "median_wall_seconds": round(statistics.median(a["wall_seconds"] for a in rows), 1),
                "local_tokens_total": sum(a["local_tokens"] for a in rows),
            }
        d, t = row.get("direct"), row.get("tandem")
        if d and t and d["cost_usd_per_success"] and t["cost_usd_per_success"]:
            row["tandem_vs_direct_per_success"] = round(t["cost_usd_per_success"] / d["cost_usd_per_success"] - 1, 4)
        summary[task] = row

    report = {
        "reevaluated_at": datetime.now(timezone.utc).isoformat(), "repeats": REPEATS,
        "rule": "success = every repetition passes and the attempt ended inside its budget",
        "evaluator_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ROOT.glob("check_*.mjs"))},
        "summary": summary, "attempts": attempts,
    }
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
