# Methodological Correction Report — Comparative Benchmark Suite (`v3.6.1`)

This document records the methodological defects identified in the initial comparative run (`20261117-075357`) and the corrections applied in `20261117-075357_corrected` and the benchmark framework (`metrics.py`, `evaluate.py`, `run_comparison.py`).

The original raw dataset [`runs/20261117-075357/results.json`](runs/20261117-075357/results.json) is preserved unmodified. The corrected re-analysis is published separately in [`runs/20261117-075357_corrected/RESULTS.md`](runs/20261117-075357_corrected/RESULTS.md).

---

## 1. Timeout Counted as End-to-End Success (P0 — Critical)

- **Original issue**: `gen_orbital` under `gemini_tandem` timed out at `2,400.12 s` (`status: "TIMEOUT"`, cloud usage `unavailable`) after generating a valid `index.html` (`13,019 B`, passing `check_page.js` and headless Chromium). `aggregate_runs()` computed `success_rate` solely from `quality.passed`, reporting `100.0%` success.
- **Root cause**: Execution completion and artifact quality were conflated into a single boolean.
- **Corrected calculation**:
  - `execution_completed = (execution_status == "COMPLETED")`
  - `artifact_valid = (quality.evaluated and quality.passed)`
  - `end_to_end_success = execution_completed and artifact_valid`
- **Before vs. After (`gen_orbital`, `gemini_tandem`)**:
  - Before: `success_rate = 100.0%`
  - After: `completed_executions = 0`, `end_to_end_success_rate = 0.0%`, `artifact_pass_rate = 100.0%`, `timeouts = 1`, `usage_coverage_pct = 0.0%`, `cloud_tokens_per_success = N/A`.

---

## 2. Cloud Token Accounting & Coverage (P1 — High)

- **Original issue**: `aggregate_runs()` averaged `cloud_total_tokens` only over `successes`, silently excluding failed attempts and omitting usage coverage.
- **Root cause**: Filtering `cloud_ok` on `quality.passed` dropped resource consumption of failed runs.
- **Corrected calculation**:
  - **Cloud Tokens Per Attempt**: Mean and total across **all** attempts with measured usage (both successful and failed). Missing usage (e.g. timeouts) remains `null`, never `0`.
  - **Cloud Tokens Per Successful Result**: `total_measured_cloud_tokens / end_to_end_successes` (returns `N/A` when `end_to_end_successes == 0`, and marks `incomplete` when `usage_coverage_pct < 100%`).
  - **No Double-Counting**: Verified against `agy --output-format json` (`total_tokens == input_tokens + output_tokens`, where `thinking_tokens <= output_tokens`), so `thinking_tokens` is never added on top of `total_tokens`. `cache_read_tokens` is tracked separately.

---

## 3. Context Reduction vs. Assistant Response Proxy (P1 — High)

- **Original issue**: `run_comparison.py` passed `len(answer_text)` (final assistant response) into `compute_context_reduction()`, conflating assistant reply length with tool context transferred to the cloud.
- **Corrected calculation**:
  - `extract_tool_interactions_from_transcript()` parses `transcript_full.jsonl` (`PLANNER_RESPONSE.tool_calls` + `GENERIC` tool responses) across all three scenarios to record actual `tool_call_count`, `total_request_bytes`, `total_response_bytes`, and `truncated_calls`.
  - `mcp_proxy.py` provides an additional transparent stdio JSON-RPC proxy for direct MCP wire-level measurement without modifying Tandem `v3.6.1`.

---

## 4. Model Identity & Environment Integrity (P1)

- **Original issue**: `run_comparison.py` hardcoded `identity_verified: true` at the report level based only on `--model gemini-4-hydrogen-medium`.
- **Corrected calculation**:
  - `verify_agy_model_identity()` inspects each run's `transcript.jsonl` `PLANNER_RESPONSE.model` field. In `20261117-075357_corrected`, `53/54` runs are independently verified as `gemini-4-hydrogen-medium`; the timed-out `gen_orbital` run has `identity_verified: false` (no `conversation_id`).
  - `verify_tandem_environment()` checks commit `010cbb6`, clean git working tree, `tandem_mcp.__version__ == "3.6.1"`, imported package path, and SHA-256 hashes of all `tandem_mcp/*.py` files.

---

## 5. Independent Evaluator Ground Truth & Truncated Preview Bug (P1)

- **Original issue**:
  1. `run_comparison.py` evaluated `answer_text` live, but subsequent re-evaluations using `answer_preview[:400]` truncated long preambles in `gemini_lmstudio` `extraction_manifest` (`33.3%` -> actually `100.0%` when reading full response from `transcript_full.jsonl`).
  2. `eval_reading_readme` required the word `"network"` even when the model accurately answered `TANDEM_SANDBOX` for sandbox mode (`33.3%` -> `100.0%` when checked against `README_v3_6_1.md` ground truth).
  3. `eval_reading_git_history`, `eval_reading_package_survey`, `eval_gen_orbital`, and `eval_gen_portal` were strengthened with `git log --stat` frequency parsing, AST module/responsibility checks, and multi-frame headless Chromium DOM/control/pixel-change checks.

---

## 6. Remaining Limitations

- Single-repeat (`n=1`) long-running tasks (`reading_package_survey`, `reading_git_history`, `gen_orbital`, `gen_portal`) are not statistically representative and do not report variance intervals.
- Antigravity CLI (`agy`) adds ~12–15K base system/tool-declaration input tokens per session; this overhead is included in all three scenarios as measured by `agy` without subtracting an assumed constant.
