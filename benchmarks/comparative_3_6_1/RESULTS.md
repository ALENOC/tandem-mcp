# Comparative Benchmark Results — Tandem MCP v3.6.1 (`010cbb6`)

Rigorous three-way comparison of **Gemini 4 Hydrogen** (`gemini-4-hydrogen-medium`), **Gemini 4 Hydrogen + Direct LM Studio** (`qwen3.8-27b@iq3_s` via minimal tool harness), and **Gemini 4 Hydrogen + Tandem MCP v3.6.1** (`010cbb6` + `qwen3.8-27b@iq3_s`).

Raw data: [`runs/20261117-075357/results.json`](runs/20261117-075357/results.json) · Suite runner: [`run_comparison.py`](run_comparison.py) · Evaluator: [`evaluate.py`](evaluate.py) · Metrics: [`metrics.py`](metrics.py)

---

## 1. Environment & Identity Verification

- **Date**: 2026-11-17
- **Run ID**: `20261117-075357`
- **Tandem MCP**: `3.6.1`, commit `010cbb6` (verified against `/home/ale/tools/tandem-mcp`)
- **Orchestrator**: `gemini-4-hydrogen-medium` (`orchestrator_identity_verified: true`, executed via `agy --model gemini-4-hydrogen-medium --output-format json`)
- **Cloud token collection**: `measured` via `agy --output-format json` (`input_tokens`, `output_tokens`, `thinking_tokens`, `cache_read_tokens`, `total_tokens`, `num_turns`)
- **Local executor**: `qwen3.8-27b@iq3_s` on LM Studio (`http://127.0.0.1:1234/v1`), context `65536`
- **Hardware**: Intel Core i9-9900K @ 3.60GHz (16 threads), 22 GiB RAM, AMD Radeon Navi 21 (RX 6800/6900 XT, 16 GiB VRAM), Linux x86_64
- **Frozen fixtures**: 24 files from tag `v3.6.1` (`010cbb6`), SHA-256 verified before every run ([`fixtures/manifest.json`](fixtures/manifest.json))
- **Cache policy**: Isolated temporary `TANDEM_HOME` and fresh workspace per run; scenario order rotated across repetitions (`A,B,C`, `B,C,A`, `C,A,B`).

---

## 2. Comparative Results (Measured Cloud Tokens, Local Tokens, Time & Quality)

> **Important:** Negative `Cloud Savings vs Direct` means Tandem (or Direct LM Studio) consumed **more** total cloud tokens than `Gemini Direct` for that task. Values are never clamped to zero.

| Task | Scenario | n | Success | Median Time (s) | Cloud Tokens (mean, measured) | Cloud Savings vs Direct | Local Tokens (mean, measured) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `reading_readme` | `gemini_direct` | 3 | 33.3% | 11.06 | 15,920.0 | baseline | 0 |
| `reading_readme` | `gemini_lmstudio` | 3 | 0.0% | 83.46 | N/A | N/A | N/A |
| `reading_readme` | `gemini_tandem` | 3 | 33.3% | 85.25 | 20,787.0 | **-30.6%** | 5,313.0 |
| `reading_grep_agent` | `gemini_direct` | 3 | 100.0% | 15.58 | 19,627.3 | baseline | 0 |
| `reading_grep_agent` | `gemini_lmstudio` | 3 | 100.0% | 145.09 | 24,371.0 | **-24.2%** | 18,124.3 |
| `reading_grep_agent` | `gemini_tandem` | 3 | 100.0% | 69.77 | 25,704.7 | **-31.0%** | 1,262.7 |
| `reading_package_survey` | `gemini_direct` | 1 | 100.0% | 26.75 | 27,564.0 | baseline | 0 |
| `reading_package_survey` | `gemini_lmstudio` | 1 | 100.0% | 474.46 | 29,014.0 | **-5.3%** | 45,520.0 |
| `reading_package_survey` | `gemini_tandem` | 1 | 100.0% | 220.57 | 40,437.0 | **-46.7%** | 1,113.0 |
| `reading_git_history` | `gemini_direct` | 1 | 100.0% | 17.90 | 22,127.0 | baseline | 0 |
| `reading_git_history` | `gemini_lmstudio` | 1 | 100.0% | 181.77 | 18,374.0 | **+17.0%** | 18,591.0 |
| `reading_git_history` | `gemini_tandem` | 1 | 0.0% | 318.98 | 43,707.0 | **-97.5%** | 17,202.0 |
| `extraction_manifest` | `gemini_direct` | 3 | 100.0% | 8.11 | 14,463.3 | baseline | 0 |
| `extraction_manifest` | `gemini_lmstudio` | 3 | 33.3% | 32.94 | 20,532.0 | **-42.0%** | 2,019.0 |
| `extraction_manifest` | `gemini_tandem` | 3 | 100.0% | 38.54 | 17,853.7 | **-23.4%** | 1,065.0 |
| `bugfix_micro` | `gemini_direct` | 3 | 100.0% | 16.22 | 19,155.3 | baseline | 0 |
| `bugfix_micro` | `gemini_lmstudio` | 3 | 100.0% | 54.99 | 28,489.3 | **-48.7%** | 5,202.0 |
| `bugfix_micro` | `gemini_tandem` | 3 | 100.0% | 60.46 | 21,540.7 | **-12.5%** | 6,391.0 |
| `bugfix_multifile` | `gemini_direct` | 3 | 100.0% | 17.40 | 23,470.7 | baseline | 0 |
| `bugfix_multifile` | `gemini_lmstudio` | 3 | 100.0% | 90.90 | 22,166.3 | **+5.6%** | 12,599.0 |
| `bugfix_multifile` | `gemini_tandem` | 3 | 100.0% | 85.10 | 21,055.3 | **+10.3%** | 9,010.7 |
| `gen_orbital` | `gemini_direct` | 1 | 100.0% | 56.75 | 35,975.0 | baseline | 0 |
| `gen_orbital` | `gemini_lmstudio` | 1 | 100.0% | 816.11 | 40,847.0 | **-13.5%** | 37,149.0 |
| `gen_orbital` | `gemini_tandem` | 1 | 100.0% | 2,400.12 (timeout) | `unavailable` | `N/A` | 125,923.0 |

*(Scope note: `gen_portal` was not re-run in the 3-way comparative suite due to ~40+ min per local generation run; historical single-run data for `gen_portal` is preserved separately in [`../gemini_3_6_1/RESULTS.md`](../gemini_3_6_1/RESULTS.md). Single-run tasks `n=1` are not statistically representative.)*

---

## 3. Targeted Grep Dual-Baseline Analysis (`reading_grep_agent`)

In the historical suite, `digest_file (grep)` compared its 480 B response against the full 99,739 B `agent.py` file, reporting `99.5%` savings. Under the corrected methodology:

1. **Full-file Context Reduction (Estimated)**: `99.5%` (99,739 B source vs ~480 B digest output; measures text compression relative to reading the entire file).
2. **Efficient-search Baseline (`gemini_direct` with `grep`/line-range reads)**: Gemini Direct found the answer in `15.58 s` (median) using `19,627.3` actual cloud tokens (mean). Tandem took `69.77 s` (median) and `25,704.7` actual cloud tokens (`-31.0%`), because MCP tool-call round-trips and system/tool schema overhead outweigh reading a few targeted lines when the orchestrator already has fast local search tools.

---

## 4. Key Findings: When Tandem Pays and When It Does Not

1. **Multi-file bugfix with existing tests (`bugfix_multifile`) is where Tandem won on both cloud tokens and reliability:**
   - Tandem achieved **+10.3% actual cloud token savings** vs Gemini Direct (`21,055.3` vs `23,470.7` cloud tokens) with **100% success** (`n=3`), and used fewer local tokens (`9,010.7`) than Direct LM Studio (`12,599.0`).
2. **Tandem vs Direct LM Studio (`gemini_lmstudio`) on quality & local efficiency:**
   - On `extraction_manifest`, `gemini_tandem` achieved **100% schema-valid extraction** (`n=3`, `1,065` local tokens) whereas `gemini_lmstudio` succeeded only **33.3%** (`1/3`).
   - On `reading_grep_agent` and `reading_package_survey`, `gemini_tandem` used **14x–40x fewer local tokens** (`1,262.7` vs `18,124.3`; `1,113` vs `45,520`) because `digest_file (grep)` and `digest_many` bound what the local model reads.
3. **Small single-file tasks (`extraction_manifest`, `bugfix_micro`, `reading_grep_agent`) do NOT save actual cloud tokens vs Gemini Direct:**
   - Each `agy` session carries ~12–15K base system/tool-definition input tokens per turn. Adding MCP tool calls adds turns and tool schemas, resulting in `-12.5%` to `-46.7%` actual cloud token overhead on small tasks where Gemini Direct can read/grep directly in 1–2 turns.
4. **Code generation (`gen_orbital`)**:
   - All three scenarios passed `node check_page.js` and headless Chromium rendering with 0 console errors.
   - `gemini_direct` completed in `56.75 s` (`35,975` cloud tokens).
   - `gemini_lmstudio` completed in `816.11 s` (`40,847` cloud tokens, `-13.5%` total, though cloud output tokens dropped from `10,200` to `3,282`).
   - `gemini_tandem` produced a passing `13,019 B` `index.html` (`125,923` local tokens) but hit the `2,400 s` CLI timeout, leaving cloud token usage `unavailable`.

---

## 5. Phase 10 Analysis: High Local Token Usage in `digest_command` (`git log -n 30 --stat`)

In the historical 3.6.1 campaign (`53,712` local tokens, `420.63 s`) and the comparative run (`17,202` local tokens, `318.98 s`), `digest_command` consumed disproportionately many local tokens for a `13,221 B` (~3,700 token) input. Inspection of `tandem_mcp/digest.py` and `tandem_mcp/engine.py` identifies the root cause (not a code regression, but an interaction with thinking models):

- `digest.answer()` sets `max_tokens = max(600, max_words * 6)` (`720` tokens for `max_words=120`).
- `qwen3.8-27b@iq3_s` has **thinking enabled**; on an aggregation prompt ("Which files were changed most often..."), reasoning consumes the 720-token budget before emitting JSON (`finish_reason == 'length'`, empty `content`).
- `engine.chat()` triples the budget (`2,160`) and re-sends the full ~3,700-token prompt; if JSON is still incomplete/invalid, `engine.chat_json()` retries up to 3 attempts (up to 6 total LLM calls), multiplying prompt and reasoning tokens.
- **Proposed future optimization (not applied to `v3.6.1`)**: Increase `digest.answer()`'s `max_tokens` floor when `caps(model)['thinking']` is `True` (e.g. `max(2048, max_words * 6)`), and log `retry_attempts` / `quotes_ok` for `digest_command` in `ledger.jsonl`.
