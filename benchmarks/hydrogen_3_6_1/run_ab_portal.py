#!/usr/bin/env python3
"""Run controlled A/B comparison: Tandem baseline vs Tandem modified on gen_portal from-prompt, plus Orbital regression."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
BASELINE_PKG = Path("/tmp/tandem_baseline_pkg")
OUT_DIR = ROOT / "runs" / "20261119_ab_portal_opt"


def _run_one(task: str, variant: str, tag: str, skip_direct: bool = True) -> dict:
    env = os.environ.copy()
    if variant == "baseline":
        env["PYTHONPATH"] = f"{BASELINE_PKG}:{REPO_ROOT}"
    else:
        env["PYTHONPATH"] = str(REPO_ROOT)

    cmd = [
        str(REPO_ROOT / ".venv/bin/python"),
        str(ROOT / "run_from_prompt_pair.py"),
        "--task", task,
        "--tag", tag,
    ]
    if skip_direct:
        cmd.append("--skip-direct")

    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, capture_output=True, text=True)
    # Locate the saved run directory from stdout ("Saved .../results.json")
    run_json = None
    for line in reversed((proc.stdout or "").splitlines()):
        if line.startswith("Saved ") and line.endswith("results.json"):
            run_json = Path(line.split("Saved ", 1)[1].strip())
            break
    if not run_json or not run_json.is_file():
        return {"variant": variant, "tag": tag, "task": task, "error": (proc.stderr or proc.stdout)[-400:], "rc": proc.returncode}
    payload = json.loads(run_json.read_text())
    return {
        "variant": variant,
        "tag": tag,
        "task": task,
        "run_dir": str(run_json.parent),
        "results": payload["results"],
    }


def _save(records: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "summary.json").write_text(
        json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(), "records": records}, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["pilot", "rest"], required=True)
    args = parser.parse_args()

    summary_path = OUT_DIR / "summary.json"
    records = json.loads(summary_path.read_text()).get("records", []) if summary_path.is_file() else []

    if args.phase == "pilot":
        # Pair 1: direct + modified_r1, then baseline_r1
        records.append(_run_one("gen_portal", "modified", "ab_modified_r1", skip_direct=False))
        _save(records)
        records.append(_run_one("gen_portal", "baseline", "ab_baseline_r1", skip_direct=True))
        _save(records)
    else:
        # Pair 2 (baseline_r2 -> modified_r2) and Pair 3 (modified_r3 -> baseline_r3) + Orbital regression
        for variant, tag in [
            ("baseline", "ab_baseline_r2"),
            ("modified", "ab_modified_r2"),
            ("modified", "ab_modified_r3"),
            ("baseline", "ab_baseline_r3"),
        ]:
            records.append(_run_one("gen_portal", variant, tag, skip_direct=True))
            _save(records)
        records.append(_run_one("gen_orbital", "modified", "ab_orbital_reg", skip_direct=True))
        _save(records)

    print("Saved", summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
