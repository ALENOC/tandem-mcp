#!/usr/bin/env python3
"""Build the GitHub Pages site with the benchmark comparison.

Copies site/ to the output directory, writes data.json from the re-evaluation report and copies the
comparison GIFs and the live demo pages next to it. The workflow in .github/workflows/pages.yml runs this on every push to main.

Usage: python scripts/build_site.py [out_dir]   (default: _site)
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BENCH = REPO / "benchmarks" / "opus"
REPORT = BENCH / "REEVAL_4_1.json"
RUNS = BENCH / "runs"
# the pages shown live on the site, the same attempts as the GIFs
DEMOS = {
    "orbital/direct": "20261124-030230_adversarial_pilot1/workspaces/gen_orbital__p1__direct",
    "orbital/tandem": "20261124-052842_adversarial_confirm/workspaces/gen_orbital__p2__tandem",
    "portal/direct": "20261124-103103_adversarial_final/workspaces/gen_portal__p1__direct",
    "portal/tandem": "20261124-103103_adversarial_final/workspaces/gen_portal__p1__tandem",
}
BUDGETS = {"py_discount": 900, "py_cron": 2400, "web_boids": 2400, "gen_orbital": 2400, "gen_portal": 4200}


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else REPO / "_site")
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(REPO / "site", out)
    shutil.copytree(BENCH / "gifs", out / "gifs")
    shutil.copy(REPO / "assets" / "logo.svg", out / "logo.svg")
    for dst, ws in DEMOS.items():
        shutil.copytree(RUNS / ws, out / "demos" / dst, ignore=shutil.ignore_patterns(".*", "__pycache__"))
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    attempts = [{
        "run": a["run"], "task": a["task"], "arm": a["arm"], "pair": a["pair"], "success": a["success"],
        "timed_out": a["timed_out"], "cost_usd": a["cost_usd"], "wall_seconds": a["wall_seconds"],
        "output_tokens": a["usage"].get("output_tokens"), "local_tokens": a["local_tokens"],
        "failed_checks": a["failed_checks"],
    } for a in report["attempts"]]
    data = {"reevaluated_at": report["reevaluated_at"], "repeats": report["repeats"], "rule": report["rule"],
            "budgets": BUDGETS, "summary": report["summary"], "attempts": attempts}
    (out / "data.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print(f"site built in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
