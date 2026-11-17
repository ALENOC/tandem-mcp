# Comparative Benchmark Results — Tandem MCP v3.6.1 (`010cbb6`)

Rigorous three-way comparison of **Gemini 4 Hydrogen** (`gemini-4-hydrogen-medium`), **Gemini 4 Hydrogen + Direct LM Studio** (`qwen3.8-27b@iq3_s` via minimal tool harness), and **Gemini 4 Hydrogen + Tandem MCP v3.6.1** (`010cbb6` + `qwen3.8-27b@iq3_s`).

- **Corrected re-analysis (Tasks 1–8)**: [`runs/20261117-075357_corrected/RESULTS.md`](runs/20261117-075357_corrected/RESULTS.md) · [`results.json`](runs/20261117-075357_corrected/results.json) (derived from immutable [`runs/20261117-075357/results.json`](runs/20261117-075357/results.json))
- **3D Portal 3-way run (Task 9)**: [`runs/20261117-101952/RESULTS.md`](runs/20261117-101952/RESULTS.md) · [`results.json`](runs/20261117-101952/results.json)
- **Methodological Corrections**: [`METHODOLOGY_CORRECTION.md`](METHODOLOGY_CORRECTION.md)

---

## 1. Environment & Integrity Verification

- **Tandem MCP**: `3.6.1`, commit `010cbb6` (clean working tree, imported path `/home/ale/tools/tandem-mcp/tandem_mcp`, SHA-256 verified)
- **Requested Orchestrator**: `gemini-4-hydrogen-medium`
- **Model Identity Verification**: `53/54` runs in `20261117-075357_corrected` and `2/3` runs in `20261117-101952` independently verified as `gemini-4-hydrogen-medium` via `transcript.jsonl`; timed-out runs have `identity_verified: false` (no `conversation_id`).
- **Cloud Token Accounting**: `agy_cli_json_usage` (`total_tokens == input_tokens + output_tokens`; `thinking_tokens` is already included in `output_tokens` and is not double-counted; `cache_read_tokens` is tracked separately).
- **Local Executor**: `qwen3.8-27b@iq3_s` on LM Studio (`http://127.0.0.1:1234/v1`, `65536` context).
- **Frozen Fixtures**: 24 files from tag `v3.6.1` (`010cbb6`), SHA-256 verified ([`fixtures/manifest.json`](fixtures/manifest.json)).

---

## 2. Three-Way Comparative Results (All 9 Workloads)

> **Definitions:**
> - `end_to_end_success = execution_completed AND artifact_valid`. A `TIMEOUT` run that produced a valid artifact reports `Artifact Valid = 100.0%`, `Completed = 0`, `E2E Success = 0.0%`.
> - `Cloud Tokens / Attempt` averages **all** measured attempts (both successful and failed).
> - `Cloud Savings vs Direct` is never clamped to zero; negative percentages indicate higher cloud token consumption than `gemini_direct`.

| Task | Scenario | n | Completed | E2E Success | Artifact Valid | Timeouts | Cloud Tokens / Attempt | Usage Coverage | Cloud Tokens / Success | Cloud Savings vs Direct | Median Time (s) | Local Tokens (mean) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `reading_readme` | `gemini_direct` | 3 | 3 | 100.0% | 100.0% | 0 | 15,652.7 | 100.0% | 15,652.7 | baseline | 11.06 | 0 |
| `reading_readme` | `gemini_lmstudio` | 3 | 3 | 100.0% | 100.0% | 0 | 20,731.0 | 100.0% | 20,731.0 | **-32.4%** | 83.46 | 6,496.7 |
| `reading_readme` | `gemini_tandem` | 3 | 3 | 100.0% | 100.0% | 0 | 22,336.3 | 100.0% | 22,336.3 | **-42.7%** | 85.25 | 4,469.3 |
| `reading_grep_agent` | `gemini_direct` | 3 | 3 | 100.0% | 100.0% | 0 | 19,627.3 | 100.0% | 19,627.3 | baseline | 15.58 | 0 |
| `reading_grep_agent` | `gemini_lmstudio` | 3 | 3 | 100.0% | 100.0% | 0 | 24,371.0 | 100.0% | 24,371.0 | **-24.2%** | 145.09 | 18,124.3 |
| `reading_grep_agent` | `gemini_tandem` | 3 | 3 | 100.0% | 100.0% | 0 | 25,704.7 | 100.0% | 25,704.7 | **-31.0%** | 69.77 | 1,262.7 |
| `reading_package_survey` | `gemini_direct` | 1 | 1 | 100.0% | 100.0% | 0 | 27,564.0 | 100.0% | 27,564.0 | baseline | 26.75 | 0 |
| `reading_package_survey` | `gemini_lmstudio` | 1 | 1 | 100.0% | 100.0% | 0 | 29,014.0 | 100.0% | 29,014.0 | **-5.3%** | 474.46 | 45,520.0 |
| `reading_package_survey` | `gemini_tandem` | 1 | 1 | 100.0% | 100.0% | 0 | 40,437.0 | 100.0% | 40,437.0 | **-46.7%** | 220.57 | 1,113.0 |
| `reading_git_history` | `gemini_direct` | 1 | 1 | 100.0% | 100.0% | 0 | 22,127.0 | 100.0% | 22,127.0 | baseline | 17.90 | 0 |
| `reading_git_history` | `gemini_lmstudio` | 1 | 1 | 100.0% | 100.0% | 0 | 18,374.0 | 100.0% | 18,374.0 | **+17.0%** | 181.77 | 18,591.0 |
| `reading_git_history` | `gemini_tandem` | 1 | 1 | 100.0% | 100.0% | 0 | 43,707.0 | 100.0% | 43,707.0 | **-97.5%** | 318.98 | 17,202.0 |
| `extraction_manifest` | `gemini_direct` | 3 | 3 | 100.0% | 100.0% | 0 | 14,463.3 | 100.0% | 14,463.3 | baseline | 8.11 | 0 |
| `extraction_manifest` | `gemini_lmstudio` | 3 | 3 | 100.0% | 100.0% | 0 | 20,375.7 | 100.0% | 20,375.7 | **-40.9%** | 32.94 | 2,014.3 |
| `extraction_manifest` | `gemini_tandem` | 3 | 3 | 100.0% | 100.0% | 0 | 17,853.7 | 100.0% | 17,853.7 | **-23.4%** | 38.54 | 1,065.0 |
| `bugfix_micro` | `gemini_direct` | 3 | 3 | 100.0% | 100.0% | 0 | 19,155.3 | 100.0% | 19,155.3 | baseline | 16.22 | 0 |
| `bugfix_micro` | `gemini_lmstudio` | 3 | 3 | 100.0% | 100.0% | 0 | 28,489.3 | 100.0% | 28,489.3 | **-48.7%** | 54.99 | 5,202.0 |
| `bugfix_micro` | `gemini_tandem` | 3 | 3 | 100.0% | 100.0% | 0 | 21,540.7 | 100.0% | 21,540.7 | **-12.5%** | 60.46 | 6,391.0 |
| `bugfix_multifile` | `gemini_direct` | 3 | 3 | 100.0% | 100.0% | 0 | 23,470.7 | 100.0% | 23,470.7 | baseline | 17.40 | 0 |
| `bugfix_multifile` | `gemini_lmstudio` | 3 | 3 | 100.0% | 100.0% | 0 | 22,166.3 | 100.0% | 22,166.3 | **+5.6%** | 90.90 | 12,599.0 |
| `bugfix_multifile` | `gemini_tandem` | 3 | 3 | 100.0% | 100.0% | 0 | 21,055.3 | 100.0% | 21,055.3 | **+10.3%** | 85.10 | 9,010.7 |
| `gen_orbital` | `gemini_direct` | 1 | 1 | 100.0% | 100.0% | 0 | 35,975.0 | 100.0% | 35,975.0 | baseline | 56.75 | 0 |
| `gen_orbital` | `gemini_lmstudio` | 1 | 1 | 100.0% | 100.0% | 0 | 40,847.0 | 100.0% | 40,847.0 | **-13.5%** | 816.11 | 37,149.0 |
| `gen_orbital` | `gemini_tandem` | 1 | 0 | **0.0%** | 100.0% | 1 | N/A | 0.0% | N/A | N/A | 2,400.12 | 125,923.0 |
| `gen_portal` | `gemini_direct` | 1 | 1 | 100.0% | 100.0% | 0 | 58,280.0 | 100.0% | 58,280.0 | baseline | 93.35 | 0 |
| `gen_portal` | `gemini_lmstudio` | 1 | 1 | 100.0% | 100.0% | 0 | 208,731.0 | 100.0% | 208,731.0 | **-258.2%** | 2,152.57 | 17,158.0 |
| `gen_portal` | `gemini_tandem` | 1 | 0 | **0.0%** | 0.0% | 1 | N/A | 0.0% | N/A | N/A | 4,200.13 | 267,995.0 |

*(Note: Single-run tasks `n=1` are not statistically representative.)*

---

## 3. When Tandem Pays vs. When Direct Execution Wins

1. **Multi-file bugfix with existing tests (`bugfix_multifile`, `n=3`)**: Tandem achieved **+10.3% actual cloud token savings** (`21,055.3` vs `23,470.7` cloud tokens), `100.0%` E2E success, and fewer local tokens (`9,010.7`) than Direct LM Studio (`12,599.0`).
2. **Bounded local reading (`reading_grep_agent`, `reading_package_survey`)**: Tandem used **14x–40x fewer local tokens** than Direct LM Studio (`1,262.7` vs `18,124.3`; `1,113.0` vs `45,520.0`) because `digest_file (grep)` and `digest_many` bound what the local model reads.
3. **Small single-file tasks (`reading_readme`, `reading_grep_agent`, `extraction_manifest`, `bugfix_micro`)**: `gemini_direct` is **4x–8x faster** (`8–17 s`) and uses **12%–43% fewer actual cloud tokens** because `agy` carries ~12–15K base system/tool-declaration tokens per session and Gemini's native `grep`/file-read tools solve small tasks in 1–2 turns.
4. **Complex multi-module generation (`gen_orbital`, `gen_portal`)**: On `qwen3.8-27b@iq3_s` (~6–23 tok/s), Tandem's contract + verification + evidence loop exceeded the `2,400 s` (`gen_orbital`) and `4,200 s` (`gen_portal`) CLI timeouts (`0.0%` E2E success), whereas `gemini_direct` completed both in `56.75 s` and `93.35 s` with `100.0%` E2E success.
