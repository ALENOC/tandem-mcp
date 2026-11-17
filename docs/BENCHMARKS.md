# Benchmarks

> **Trade-off first.** Tandem can save cloud tokens on multi-file test-driven fixes (`+10.3%` measured vs. Gemini Direct), at the cost of local execution time (which depends on your hardware). On small single-file tasks where a cloud orchestrator already has fast grep/read tools, MCP round-trips and tool schemas often consume **more** total cloud tokens (`-12.5%` to `-46.7%`), even though raw context compression (`Context Reduction (Est.)`) appears high.

This document separates three distinct campaigns (do not conflate datasets across versions or methodologies):
1. **Comparative — Gemini Direct vs. LM Studio vs. Tandem 3.6.1 (`010cbb6`)** (new measured methodology)
2. **Historical — Gemini / Tandem 3.6.1 (`010cbb6`)** (reproduction of the v3.1.0 suite)
3. **Historical — Fable / Tandem 3.1.0** (original baseline campaign, unmodified)

---

## Comparative — Gemini Direct vs. Direct LM Studio vs. Tandem 3.6.1

Suite: [`benchmarks/comparative_3_6_1/run_comparison.py`](../benchmarks/comparative_3_6_1/run_comparison.py) · Full report: [`benchmarks/comparative_3_6_1/RESULTS.md`](../benchmarks/comparative_3_6_1/RESULTS.md) · Raw JSON: [`results.json`](../benchmarks/comparative_3_6_1/runs/20261117-075357/results.json)

Measured with `gemini-4-hydrogen-medium` (`agy --output-format json`, `orchestrator_identity_verified: true`) and `qwen3.8-27b@iq3_s` on LM Studio (`http://127.0.0.1:1234/v1`) over 24 SHA-256 frozen `v3.6.1` (`010cbb6`) fixtures.

| Task | Scenario | n | Success | Median Time | Cloud Tokens (mean) | Cloud Savings vs Direct | Local Tokens (mean) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `reading_grep_agent` | `gemini_direct` | 3 | 100.0% | 15.6 s | 19,627.3 | baseline | 0 |
| `reading_grep_agent` | `gemini_lmstudio` | 3 | 100.0% | 145.1 s | 24,371.0 | -24.2% | 18,124.3 |
| `reading_grep_agent` | `gemini_tandem` | 3 | 100.0% | 69.8 s | 25,704.7 | -31.0% | 1,262.7 |
| `extraction_manifest` | `gemini_direct` | 3 | 100.0% | 8.1 s | 14,463.3 | baseline | 0 |
| `extraction_manifest` | `gemini_lmstudio` | 3 | 33.3% | 32.9 s | 20,532.0 | -42.0% | 2,019.0 |
| `extraction_manifest` | `gemini_tandem` | 3 | 100.0% | 38.5 s | 17,853.7 | -23.4% | 1,065.0 |
| `bugfix_micro` | `gemini_direct` | 3 | 100.0% | 16.2 s | 19,155.3 | baseline | 0 |
| `bugfix_micro` | `gemini_lmstudio` | 3 | 100.0% | 55.0 s | 28,489.3 | -48.7% | 5,202.0 |
| `bugfix_micro` | `gemini_tandem` | 3 | 100.0% | 60.5 s | 21,540.7 | -12.5% | 6,391.0 |
| `bugfix_multifile` | `gemini_direct` | 3 | 100.0% | 17.4 s | 23,470.7 | baseline | 0 |
| `bugfix_multifile` | `gemini_lmstudio` | 3 | 100.0% | 90.9 s | 22,166.3 | +5.6% | 12,599.0 |
| `bugfix_multifile` | `gemini_tandem` | 3 | 100.0% | 85.1 s | 21,055.3 | **+10.3%** | 9,010.7 |
| `reading_package_survey` | `gemini_direct` | 1 | 100.0% | 26.8 s | 27,564.0 | baseline | 0 |
| `reading_package_survey` | `gemini_tandem` | 1 | 100.0% | 220.6 s | 40,437.0 | -46.7% | 1,113.0 |
| `reading_git_history` | `gemini_direct` | 1 | 100.0% | 17.9 s | 22,127.0 | baseline | 0 |
| `reading_git_history` | `gemini_tandem` | 1 | 0.0% | 319.0 s | 43,707.0 | -97.5% | 17,202.0 |
| `gen_orbital` | `gemini_direct` | 1 | 100.0% | 56.8 s | 35,975.0 | baseline | 0 |
| `gen_orbital` | `gemini_lmstudio` | 1 | 100.0% | 816.1 s | 40,847.0 | -13.5% | 37,149.0 |
| `gen_orbital` | `gemini_tandem` | 1 | 100.0% | 2,400.1 s (timeout) | `unavailable` | `N/A` | 125,923.0 |

---

## Historical — Gemini / Tandem 3.6.1 (`010cbb6`)

Reproducible suite: [benchmarks/gemini_3_6_1/run_benchmark.py](../benchmarks/gemini_3_6_1/run_benchmark.py) · Full report: [benchmarks/gemini_3_6_1/RESULTS.md](../benchmarks/gemini_3_6_1/RESULTS.md) · Raw JSON: [results.json](../benchmarks/gemini_3_6_1/results.json) · [generation.json](../benchmarks/gemini_3_6_1/generation.json)

Orchestrator `Gemini 4 Hydrogen` (cloud) and executor `qwen3.8-27b@iq3_s` (LM Studio, `http://127.0.0.1:1234/v1`, `65536` ctx, `23.6 tok/s` probed), Tandem `3.6.1` (commit `010cbb6`) with strict contract, cache disabled, `1 cloud tok = 3.6 chars` (**Estimated Context Reduction**), on **Intel Core i9-9900K @ 3.60GHz (16 threads)**, **22 GiB RAM**, **AMD Radeon Navi 21 (RX 6800/6900 XT, 16 GiB VRAM)**, Linux x86_64.

### Reading, Command Digest & Extraction (3.6.1)

| Task | Source -> Cloud | Cloud saved (est.) | Local tokens | Time | Evidence |
| --- | --- | ---: | ---: | ---: | --- |
| Full-file doc QA (`README.md`) | 8.5 KB -> 811 B | **~2,127 tok (90.4%)** | 3,602 | 36.2 s | 1 ok / 2 dropped (`contested`) |
| Targeted grep QA (`agent.py`) | 99.7 KB -> 480 B | **~27,572 tok (99.5%)** | 837 | 22.2 s | 2 ok / 0 dropped (`quote_only`) |
| Multi-file package survey (`tandem_mcp/*.py`) | 250.6 KB -> 1.5 KB | **~69,202 tok (99.4%)** | 107,172 | 864.0 s | 11 ok / 0 dropped (`checked`) |
| Recent git history (`git log -n 30 --stat`) | 13.2 KB -> 425 B | **~3,554 tok (96.8%)** | 53,712 | 420.6 s | `quotes_ok: null` |
| Project manifest (`pyproject.toml`) | 786 B -> 113 B | **~187 tok (85.6%)** | 633 | 11.9 s | schema validated, 0 loose values |

### Delegated Fixes with an Existing Test (3.6.1)

| Task | Baseline -> Receipt | Cloud saved (est.) | Local tokens | Time | Result |
| --- | --- | ---: | ---: | ---: | --- |
| Micro bugfix (1 tiny file, 6 lines) | 1.0 KB -> 432 B | **~171 tok (58.7%)** | 6,498 | 27.7 s | `VERIFIED` (4 steps, 0 repairs) |
| Multi-file bugfix (`config_loader.py` + 3 files) | 6.1 KB -> 476 B | **~1,561 tok (92.2%)** | 8,278 | 37.1 s | `VERIFIED` (4 steps, 0 repairs) |

### Generation From a Contract (3.6.1)

| Metric | Orbital (Direct) | Orbital (Tandem) | 3D Portal (Direct) | 3D Portal (Tandem) |
| --- | ---: | ---: | ---: | ---: |
| Output | 14,726 B, 466 lines | 13,295 B, 509 lines | 17,593 B, 518 lines | 21,211 B, 730 lines (4 files) |
| Cloud output tokens saved (est.) | n/a | **42.7%** (~1,748 tok) | n/a | **51.0%** (~2,491 tok) |
| Cloud input tokens to inspect (est.) | 0 | ~5,529 | 0 | ~9,708 |
| Local tokens | 0 | 63,324 | 0 | 237,029 |
| Wall time | 1 cloud turn | **984.2 s** (16.4 min) | 1 cloud turn | **2,464.4 s** (41.1 min) |
| Constraints met on inspection | n/a | **46 of 46** | n/a | **69 of 69** |

Live demos (all four interactive comparisons):
- **Gemini 4 Hydrogen + Tandem v3.6.1**: [Orbital Animation Comparison](https://alenoc.github.io/tandem-mcp/benchmarks/gemini_3_6_1/animation_comparison.html) · [3D Portal Comparison](https://alenoc.github.io/tandem-mcp/benchmarks/gemini_3_6_1/scene3d_comparison.html)
- **Historical Fable 5.2 + Tandem v3.1.0**: [Orbital Animation Comparison](https://alenoc.github.io/tandem-mcp/benchmarks/animation_comparison.html) · [3D Portal Comparison](https://alenoc.github.io/tandem-mcp/benchmarks/scene3d_comparison.html)

## 1. Live Profiling & Micro-Benchmark (Tandem 3.6.0, Nov 2026)

Measured on **LM Studio** (`http://127.0.0.1:1234/v1`) running **`qwen3.8-27b@iq3_s`**:

| Scenario / Phase | Wall Time | Local Tokens | Outcome / Notes |
| --- | ---: | ---: | --- |
| `digest_file` (`calc.py`) | 16.36 s | - | Quote-checked answer |
| `extract_from_file` (`calc.py`) | 4.96 s | - | Schema-validated JSON |
| `delegate` bugfix (`calc.py` + `unittest`) | 13.46 s | 4,608 | `VERIFIED` (3 steps, 0 repairs) |
| `delegate` refactor + `read_globs` (`fmt.py`) | 26.35 s | 6,494 | `VERIFIED` (4 steps, 0 repairs) |

Phase breakdown for the 13.46 s `delegate` bugfix:
- Local LLM inference (`_turn`): **12.5606 s (93.3%)**
- Baseline + post-edit `bwrap` verification (`run_checks`): **0.8921 s (6.6%)**
- Tandem Python overhead (`protect` 0.0006 s + `take_guard` 0.0003 s + `tool_exec` 0.0014 s + `changes` 0.0018 s + `_save` 0.0026 s): **0.0067 s (<0.1%)**
- Large-workspace scan (`protect` + `take_guard` on 2,500 files): **0.0196 s**

## 2. Live Validation & Micro-Benchmark (Tandem 3.5.1, Nov 2026)

Measured on **LM Studio** (`http://127.0.0.1:1234/v1`) running **`qwen3.8-27b@iq3_s`** (`tools=true`, `schema=true`, `thinking=true`, probed `10.7 tok/s`):

| Test / Scenario | Wall Time | Local Tokens | Outcome |
| --- | ---: | ---: | --- |
| `executor_probe` (schema + tools) | 7.75 s | - | `tools=true, schema=true, 10.7 tok/s` |
| Code understanding (`digest_file` on `stats.py`) | 14.84 s | - | `quote_found=true` |
| Direct LM Studio API bugfix (Scenario B, no sandbox/tests) | 8.46 s | 305 | `has_fix=true` (unverified) |
| Tandem `delegate` bugfix (Scenario C, baseline + `unittest` + journal) | 23.78 s | 5,124 | `VERIFIED` (3 steps, 0 repairs, `fully_backed`, rollback verified) |
| Failed task + guard + rollback (`delegate` with impossible test) | 13.27 s | - | `checks_failed`, `test_calc.py` intact, `calc.py` restored |
| Multi-chunk extraction (`extract_from_file`, `TANDEM_CONTEXT=2500`) | 76.03 s | - | Validated merged JSON matching schema |

*(Note: Scenario B measures only raw inference without contract validation, sandboxed test execution, or rollback; Scenario C includes the full baseline check, tool loop, post-edit verification, and journal/snapshot overhead.)*

## Historical Benchmark (Tandem 3.1.0 — Fable 5.2 + Qwen 27B)

Reproducible suite: [benchmarks/run_benchmark.py](../benchmarks/run_benchmark.py) · Full report: [benchmarks/RESULTS.md](../benchmarks/RESULTS.md)

Orchestrator `Fable 5.2` (cloud) and executor `qwen3.8-27b@iq3_s` (LM Studio, `65536` ctx, `11.2 tok/s` probed), Tandem 3.1.0 with strict contract, cache disabled, `1 cloud tok = 3.6 chars`, on **Intel Core i9-9900K @ 3.60GHz (16 threads)**, **22 GiB RAM**, **AMD Radeon Navi 21 (RX 6800/6900 XT, 16 GiB VRAM)**, Linux x86_64.

<details>
<summary>LM Studio configuration used for the 3.1.0 executor</summary>

| Load setting | Value | Inference setting | Value |
| --- | --- | --- | --- |
| Model file | `unsloth/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-IQ3_S.gguf` (12.04 GB, 27B, IQ3_S) | Temperature | 0.15 (Tandem sets 0.1, 0.7 for extra `ask` samples) |
| Runtime | LM Studio 0.4.28, `llama.cpp` Vulkan (`2.73.0`) | Top K / Top P / Min P | 20 / 0.95 / 0.05 |
| Context length | 65536 | Repeat penalty | 1 |
| GPU offload | 65 layers (all) | Thinking | enabled, budget 1024 tokens |
| Max concurrent predictions | 1 | Speculative decoding | MTP (4 draft tokens, 0.75) |

</details>

### Reading, Command Digest & Extraction

| Task | Source -> Cloud | Cloud saved (est.) | Local tokens | Time | Evidence |
| --- | --- | ---: | ---: | ---: | --- |
| Full-file doc QA (`README.md`) | 27.9 KB -> 405 B | **~7,649 tok (98.6%)** | 10,298 | 66.2 s | 0 ok / 2 dropped (`unsupported`) |
| Targeted grep QA (`agent.py`) | 85.9 KB -> 692 B | **~23,666 tok (99.2%)** | 643 | 14.1 s | 3 ok / 0 dropped (`quote_only`) |
| Multi-file package survey (`tandem_mcp/*.py`) | 209.8 KB -> 1.5 KB | **~57,846 tok (99.3%)** | 108,207 | 800.3 s | 8 ok / 0 dropped (`checked`) |
| Recent git history (`git log -n 30 --stat`) | 18.1 KB -> 1.4 KB | **~4,614 tok (92.0%)** | 18,528 | 109.9 s | 8 ok / 0 dropped |
| Project manifest (`pyproject.toml`) | 786 B -> 113 B | **~187 tok (85.6%)** | 633 | 9.8 s | schema validated, 0 loose values |

### Delegated Fixes with an Existing Test

| Task | Baseline -> Receipt | Cloud saved (est.) | Local tokens | Time | Result |
| --- | --- | ---: | ---: | ---: | --- |
| Micro bugfix (1 tiny file, 6 lines) | 1.0 KB -> 432 B | **~171 tok (58.7%)** | 6,297 | 25.3 s | `VERIFIED` (4 steps, 0 repairs) |
| Multi-file bugfix (`config_loader.py` + 3 files) | 6.1 KB -> 476 B | **~1,561 tok (92.2%)** | 8,066 | 32.8 s | `VERIFIED` (4 steps, 0 repairs) |

### Generation From a Contract

| Metric | Orbital animation (direct) | Orbital animation (Tandem) | 3D portal (direct) | 3D portal (Tandem) |
| --- | ---: | ---: | ---: | ---: |
| Output | 11,956 B, 272 lines | 12,499 B, 459 lines | 15,122 B, 327 lines | 18,243 B, 616 lines (4 files) |
| Cloud output tokens saved | n/a | **29.4%** | n/a | **43.0%** |
| Cloud input tokens to inspect | 0 | ~4,199 | 0 | ~7,814 |
| Local tokens | 0 | 104,087 | 0 | 199,182 |
| Wall time | 1 cloud turn | **1,121 s** (19 min) | 1 cloud turn | **1,890 s** (31 min) |
| Constraints met on inspection | n/a | 46 of 46 | n/a | 67 of 69 |

Live demos: [orbital comparison](https://alenoc.github.io/tandem-mcp/benchmarks/animation_comparison.html) · [3D portal comparison](https://alenoc.github.io/tandem-mcp/benchmarks/scene3d_comparison.html).
