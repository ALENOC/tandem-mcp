# Comparative Benchmark Suite — Tandem MCP v3.6.1

Rigorous three-way comparative evaluation of **Gemini 4 Hydrogen** (`gemini-4-hydrogen-medium`) and **`qwen3.8-27b@iq3_s`** (LM Studio) on **Tandem MCP v3.6.1** (`010cbb6`).

## Scenarios

1. **Scenario A (`gemini_direct`)**: Gemini 4 Hydrogen solves the task directly using its native file reading, search (`grep`/`rg`), editing, and shell execution tools.
2. **Scenario B (`gemini_lmstudio`)**: Gemini 4 Hydrogen delegates to `qwen3.8-27b@iq3_s` through a minimal LM Studio tool harness (`lm_studio_harness.py`) without Tandem contracts, journals, rollback, or lexical quote verification.
3. **Scenario C (`gemini_tandem`)**: Gemini 4 Hydrogen orchestrates `qwen3.8-27b@iq3_s` through **Tandem MCP v3.6.1** (`digest_file`, `digest_many`, `digest_command`, `extract_from_file`, `delegate`, `delegate_many`, `job_evidence`, `job_diff`).

## Methodology & Metrics

- **Context Reduction (`derived` / `estimated`)**: Measures source bytes avoided in cloud context. Kept strictly separate from actual cloud token savings.
- **Actual Cloud Token Savings (`measured` / `unavailable`)**: Measured directly from `agy --output-format json` (`input_tokens`, `output_tokens`, `thinking_tokens`, `cache_read_tokens`, `total_tokens`, `num_turns`). Negative savings are never clamped to zero.
- **Local Compute Cost (`measured`)**: Local prompt/completion tokens, inference time, throughput (tok/s), requests, retries, and repairs from LM Studio / Tandem ledger.
- **Frozen Fixtures**: All 24 input files are frozen from tag `v3.6.1` (`010cbb6`) and verified by SHA-256 (`fixtures/manifest.json`) before every run.
- **Independent Quality Evaluation**: `evaluate.py` scores every scenario independently (never trusting `VERIFIED` alone), including headless Chromium checks for generated web apps.

## Usage

```sh
# Dry run (verifies commit 010cbb6 and all 24 SHA-256 fixture hashes)
python3 benchmarks/comparative_3_6_1/run_comparison.py --dry-run

# Run specific tasks or categories
python3 benchmarks/comparative_3_6_1/run_comparison.py --task reading_grep_agent,extraction_manifest --repeats 3
python3 benchmarks/comparative_3_6_1/run_comparison.py --category bugfix --repeats 3

# Resume an interrupted run
python3 benchmarks/comparative_3_6_1/run_comparison.py --resume <run_id>
```
