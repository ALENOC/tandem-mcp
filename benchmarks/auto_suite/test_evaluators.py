"""Unit tests & negative controls for benchmarks/auto_suite evaluators."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmarks/auto_suite"))

import suite_def  # noqa: E402

checks = 0


def ok(cond, msg):
    global checks
    assert cond, msg
    checks += 1


with tempfile.TemporaryDirectory() as tmp:
    troot = Path(tmp)
    # 1. Verify split sizes (6 dev, 6 eval, all 6 families covered in both)
    devs = [c for c in suite_def.CASES if c["split"] == "dev"]
    evals = [c for c in suite_def.CASES if c["split"] == "eval"]
    evals2 = [c for c in suite_def.CASES if c["split"] == "eval_v2"]
    ok(len(devs) == 6 and len(evals) == 6 and len(evals2) == 6, f"expected 6/6/6, got {len(devs)}/{len(evals)}/{len(evals2)}")
    ok({c["family"] for c in devs} == {c["family"] for c in evals} == {c["family"] for c in evals2}, "families mismatch")

    # 2. Extract evaluator positive + negative (wrong type/value)
    c_ext = next(c for c in devs if c["id"] == "dev_extract_toml")
    ws_ext = troot / "ext"
    c_ext["builder"](ws_ext)
    bh = suite_def.snapshot_before(ws_ext)
    ok(suite_def.evaluate_case(c_ext, ws_ext, '{"version": "1.8.3", "dep_count": 3, "batches_sum": 100}', bh)["correct"], "extract pos")
    ok(not suite_def.evaluate_case(c_ext, ws_ext, '{"version": "1.8.3", "dep_count": "3", "batches_sum": 100}', bh)["correct"], "extract neg wrong type")

    # 2b. Tied max vs unique max derived from fixture
    c_tie = next(c for c in evals if c["id"] == "eval_extract_log_counts")
    ws_tie = troot / "tie"
    c_tie["builder"](ws_tie)
    bh_tie = suite_def.snapshot_before(ws_tie)
    ok(suite_def.evaluate_case(c_tie, ws_tie, '{"error_count": 40, "top_error_service": "auth", "last_critical_ts": "2026-11-19T10:05:50Z"}', bh_tie)["correct"], "tie accepts auth")
    ok(suite_def.evaluate_case(c_tie, ws_tie, '{"error_count": 40, "top_error_service": "worker", "last_critical_ts": "2026-11-19T10:05:50Z"}', bh_tie)["correct"], "tie accepts worker")
    ok(not suite_def.evaluate_case(c_tie, ws_tie, '{"error_count": 40, "top_error_service": "billing", "last_critical_ts": "2026-11-19T10:05:50Z"}', bh_tie)["correct"], "tie rejects billing")

    c_uniq = next(c for c in evals2 if c["id"] == "eval2_extract_csv_sum")
    ws_uniq = troot / "uniq"
    c_uniq["builder"](ws_uniq)
    bh_uniq = suite_def.snapshot_before(ws_uniq)
    exp_u = suite_def._expected_from_csv(ws_uniq / "sales.csv")
    ok(len(exp_u["top_product"]) == 1 and exp_u["top_product"][0] == "edge", f"expected unique max edge, got {exp_u}")
    ok(suite_def.evaluate_case(c_uniq, ws_uniq, f'{{"eu_count": {exp_u["eu_count"]}, "eu_amount_sum": {exp_u["eu_amount_sum"]}, "top_product": "edge"}}', bh_uniq)["correct"], "unique max pass")
    ok(not suite_def.evaluate_case(c_uniq, ws_uniq, f'{{"eu_count": {exp_u["eu_count"]}, "eu_amount_sum": {exp_u["eu_amount_sum"]}, "top_product": "core"}}', bh_uniq)["correct"], "unique max wrong fails")

    # 3. Read-only violation negative
    c_exp = next(c for c in devs if c["id"] == "dev_explain_small")
    ws_exp = troot / "exp"
    c_exp["builder"](ws_exp)
    bh_exp = suite_def.snapshot_before(ws_exp)
    ok(suite_def.evaluate_case(c_exp, ws_exp, "_evict_oldest is called by put when cap is full using pop(0)", bh_exp)["correct"], "explain pos")
    (ws_exp / "cache.py").write_text("# modified\n", encoding="utf-8")
    ok(not suite_def.evaluate_case(c_exp, ws_exp, "_evict_oldest put pop(0)", bh_exp)["correct"], "read_only violation must fail")

    # 4. Python test negative (unchanged bug fails independent check)
    c_ed = next(c for c in devs if c["id"] == "dev_edit_func")
    ws_ed = troot / "ed"
    c_ed["builder"](ws_ed)
    bh_ed = suite_def.snapshot_before(ws_ed)
    ok(not suite_def.evaluate_case(c_ed, ws_ed, "", bh_ed)["correct"], "unmodified retry.py must fail independent check")

print(f"{checks} checks, 0 failures")
