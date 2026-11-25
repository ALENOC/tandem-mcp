#!/usr/bin/env python3
"""Build the GitHub Pages site with the benchmark comparison.

Copies site/ to the output directory, writes data.json from the re-evaluation report (plus the unpaired
supplementary attempts, listed apart from the totals) and copies the
comparison GIFs and the live demo pages next to it. The workflow in .github/workflows/pages.yml runs this on every push to main.

Usage: python scripts/build_site.py [out_dir]   (default: _site)
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BENCH = REPO / "benchmarks" / "opus"
DEFAULT_REPORT = BENCH / "REEVAL_4_2.json"
# unpaired extra attempts: listed on the site, never added to the summary or the totals
SUPPLEMENTARY = [BENCH / "REEVAL_4_2_PORTAL_DIRECT.json"]
RUNS = BENCH / "runs"
# the pages shown live on the site, the same attempts as the GIFs
DEFAULT_DEMOS = {
    "orbital/direct": "20261124-174810_v4_2/workspaces/gen_orbital__p3__direct",
    "orbital/tandem": "20261124-174810_v4_2/workspaces/gen_orbital__p3__tandem",
    "portal/direct": "20261124-174810_v4_2/workspaces/gen_portal__p2__direct",
    "portal/tandem": "20261124-174810_v4_2/workspaces/gen_portal__p2__tandem",
}
BUDGETS = {"py_discount": 900, "py_cron": 2400, "web_boids": 2400, "gen_orbital": 2400, "gen_portal": 4200}


def attempt_row(a: dict) -> dict:
    return {
        "run": a["run"], "task": a["task"], "arm": a["arm"], "pair": a["pair"], "success": a["success"],
        "timed_out": a["timed_out"], "cost_usd": a["cost_usd"], "wall_seconds": a["wall_seconds"],
        "output_tokens": a["usage"].get("output_tokens"), "local_tokens": a["local_tokens"],
        "failed_checks": a["failed_checks"], "local_jobs": a.get("local_jobs", []), "hints": a.get("hints", 0),
        "visual_strikes": a.get("visual_strikes", 0), "visual_review": a.get("visual_review", []),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the GitHub Pages benchmark comparison site.")
    ap.add_argument("out_dir", nargs="?", default=str(REPO / "_site"))
    ap.add_argument("--report", default=str(DEFAULT_REPORT), help="Path to reeval JSON report")
    ap.add_argument("--demos", default="", help="Optional JSON mapping demo slot -> run workspace path under benchmarks/opus/runs/")
    args = ap.parse_args()
    out = Path(args.out_dir)
    report_path = Path(args.report)
    demos = json.loads(args.demos) if args.demos else DEFAULT_DEMOS
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(REPO / "site", out)
    shutil.copytree(BENCH / "gifs", out / "gifs")
    shutil.copy(REPO / "assets" / "logo.svg", out / "logo.svg")
    for dst, ws in demos.items():
        shutil.copytree(RUNS / ws, out / "demos" / dst, ignore=shutil.ignore_patterns(".*", "__pycache__"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    supplementary = []
    for path in SUPPLEMENTARY:
        extra = json.loads(path.read_text(encoding="utf-8"))
        if extra["evaluator_sha256"] != report["evaluator_sha256"]:
            raise SystemExit(f"{path.name}: evaluators differ from {report_path.name}")
        supplementary += [dict(attempt_row(a), supplementary=True) for a in extra["attempts"]]
    data = {"reevaluated_at": report["reevaluated_at"], "repeats": report["repeats"], "rule": report["rule"],
            "budgets": BUDGETS, "summary": report["summary"], "attempts": [attempt_row(a) for a in report["attempts"]],
            "supplementary": supplementary}
    (out / "data.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print(f"site built in {out} from {report_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
