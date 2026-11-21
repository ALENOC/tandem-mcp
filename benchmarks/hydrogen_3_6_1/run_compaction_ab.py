#!/usr/bin/env python3
"""Controlled A/B comparison on full Portal jobs: TANDEM_COMPACT_WRITES=0 vs TANDEM_COMPACT_WRITES=1."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
OUT_DIR = ROOT / "runs" / "20261119_ab_compaction"


def _count_reads(run_dir: Path) -> int:
    th = run_dir / "tandem_homes" / "gen_portal__tandem_from_prompt" / "jobs"
    if not th.is_dir():
        return 0
    jdirs = list(th.iterdir())
    if not jdirs:
        return 0
    log_p = jdirs[0] / "log.json"
    if not log_p.is_file():
        return 0
    logs = json.loads(log_p.read_text())
    return sum(1 for row in logs if row.get("tool") == "read_file")


def _run_one(compact_flag: str, tag: str) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["TANDEM_COMPACT_WRITES"] = compact_flag
    cmd = [
        str(REPO_ROOT / ".venv/bin/python"),
        str(ROOT / "run_from_prompt_pair.py"),
        "--task", "gen_portal",
        "--skip-direct",
        "--tag", tag,
    ]
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, capture_output=True, text=True)
    run_json = None
    for line in reversed((proc.stdout or "").splitlines()):
        if line.startswith("Saved ") and line.endswith("results.json"):
            run_json = Path(line.split("Saved ", 1)[1].strip())
            break
    if not run_json or not run_json.is_file():
        return {"compact": compact_flag, "tag": tag, "error": (proc.stderr or proc.stdout)[-400:], "rc": proc.returncode}
    payload = json.loads(run_json.read_text())
    r = payload["results"][0]
    r["read_file_calls"] = _count_reads(run_json.parent)
    r["compact_writes"] = compact_flag
    return {"compact": compact_flag, "tag": tag, "run_dir": str(run_json.parent), "result": r}


def _save(records: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "summary.json").write_text(
        json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(), "records": records}, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["pair1", "pairs23"], required=True)
    args = parser.parse_args()

    summary_p = OUT_DIR / "summary.json"
    records = json.loads(summary_p.read_text()).get("records", []) if summary_p.is_file() else []

    if args.phase == "pair1":
        for flag, tag in [("0", "nocompact_r1"), ("1", "compact_r1")]:
            records.append(_run_one(flag, tag))
            _save(records)
    else:
        for flag, tag in [("1", "compact_r2"), ("0", "nocompact_r2"), ("0", "nocompact_r3"), ("1", "compact_r3")]:
            records.append(_run_one(flag, tag))
            _save(records)
    print("Saved", summary_p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
