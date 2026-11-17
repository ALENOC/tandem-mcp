# Tandem MCP v3.6.1: Live Benchmark Results (Gemini 4 Hydrogen + Qwen 27B)

This report reproduces the **Historical Benchmark Suite (Tandem MCP v3.1.0)** on **Tandem MCP v3.6.1** (commit `010cbb6`, tag `v3.6.1`) using **Gemini 4 Hydrogen** as the cloud orchestrator and **`qwen3.8-27b@iq3_s`** on LM Studio as the local executor.

Sections 1 and 2 are measured by [`benchmarks/gemini_3_6_1/run_benchmark.py`](run_benchmark.py) (cache disabled, isolated temporary `TANDEM_HOME`, sequential execution, raw numbers in [`results.json`](results.json)). Sections 3 to 5 compare code written directly by `Gemini 4 Hydrogen` with code written by `qwen3.8-27b@iq3_s` under the exact historical strict contracts in [`../contracts/`](../contracts/) (raw numbers in [`generation.json`](generation.json)).

---

## 1. Environment

- **Date**: 2026-11-17
- **Tandem MCP**: `3.6.1` (tag `v3.6.1`, commit `010cbb6`), strict contract on
- **Local installation**: `/home/ale/tools/tandem-mcp` (verified `3.6.1`)
- **Platform**: Linux x86_64 (`7.0.0-43-generic`) / Python `3.13.17` (`.venv`, system Python `3.14.4`), Node `v22.23.4`
- **Hardware**: Intel Core i9-9900K @ 3.60GHz (16 threads), 22 GiB RAM, AMD Radeon Navi 21 (RX 6800/6900 XT, 16 GiB VRAM)
- **Orchestrator (cloud)**: `Gemini 4 Hydrogen`
- **Executor (local)**: `qwen3.8-27b@iq3_s` on LM Studio (`http://127.0.0.1:1234/v1`), context `65536`, probed speed `23.6` tokens/s (`tools=true`, `schema=true`, `thinking=true`)
- **Sandbox**: `bubblewrap` (`allowlist system dirs, home hidden, workspace writable, env secrets stripped, no network`)
- **Cache policy**: disabled (isolated temporary `TANDEM_HOME` per run)
- **Token estimate**: `1 cloud token = 3.6 characters` (`store.CHARS_PER_TOKEN`)

## 2. LM Studio configuration of the executor

- **Endpoint**: `http://127.0.0.1:1234/v1`
- **Loaded model**: `qwen3.8-27b@iq3_s` (`context: 65536`)
- **Capabilities probed by Tandem (`engine.probe`)**: `tools: true`, `schema: true`, `thinking: true`, `tps: 23.6`
- **Notes**: Same hardware, quantization (`iq3_s`), and context window (`65536`) as the historical 3.1.0 campaign. Probed throughput increased from `11.2` tok/s (3.1.0) to `23.6` tok/s (3.6.1), reflecting runtime/system differences since the original run.

---

## 3. Reading, command digest & extraction (`digest_file`, `digest_many`, `digest_command`, `extract_from_file`)

All 5 workloads were executed sequentially against the `v3.6.1` (`010cbb6`) repository state (before any benchmark documentation updates to `README.md`).

| Scenario | Tool | Source read | Returned to cloud | Cloud tokens (without -> with) | Est. cloud tokens saved | Local tokens | Wall time | Evidence check |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Full-file doc QA (`README.md`) | `digest_file` | 8,468 B | 811 B | 2,352 -> 225 | **2,127 (90.4%)** | 3,602 | 36.16 s | 1 ok / 2 dropped (`contested`) |
| Targeted grep QA (`agent.py`) | `digest_file (grep)` | 99,739 B | 480 B | 27,705 -> 133 | **27,572 (99.5%)** | 837 | 22.22 s | 2 ok / 0 dropped (`quote_only`) |
| Multi-file package survey (`tandem_mcp/*.py`) | `digest_many (8 files)` | 250,640 B | 1,512 B | 69,622 -> 420 | **69,202 (99.4%)** | 107,172 | 863.99 s | 11 ok / 0 dropped (`checked`) |
| Recent git history (`git log -n 30 --stat`) | `digest_command` | 13,221 B | 425 B | 3,672 -> 118 | **3,554 (96.8%)** | 53,712 | 420.63 s | `quotes_ok: null` (not logged by `digest_command` in 3.6.1) |
| Project manifest (`pyproject.toml`) | `extract_from_file` | 786 B | 113 B | 218 -> 31 | **187 (85.6%)** | 633 | 11.94 s | schema validated, 0 values not in source |

**Observations:**
- On `README.md`, 1 quote was verified and 2 quotes were dropped, so Tandem flagged the answer as `contested` (negative/partial evidence is preserved and surfaced to the orchestrator).
- `README.md` in v3.6.1 is `8,468 B` (vs `27,943 B` in v3.1.0), `agent.py` grew to `99,739 B` (vs `85,889 B`), `tandem_mcp/*.py` grew to `250,640 B` (vs `209,756 B`), and `git log -n 30 --stat` at `010cbb6` is `13,221 B` (vs `18,052 B`).

---

## 4. Delegated fixes with existing tests (`delegate`)

| Scenario | Workspace + test output | Receipt returned | Cloud tokens (without -> with) | Est. cloud tokens saved | Local tokens | Wall time | Outcome |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Micro bugfix (1 tiny file, 6 lines) | 1,047 B | 432 B | 291 -> 120 | **171 (58.7%)** | 6,498 | 27.74 s | `VERIFIED` (4 steps, 0 repairs) |
| Multi-file bugfix (`config_loader.py` + 3 other files) | 6,094 B | 476 B | 1,693 -> 132 | **1,561 (92.2%)** | 8,278 | 37.07 s | `VERIFIED` (4 steps, 0 repairs) |

---

## 5. Orbital animation (single file)

Identical functional specification and strict 46-constraint contract ([`../contracts/animation.json`](../contracts/animation.json)) as the historical benchmark, with 0 post-generation fixes.

| | Variant A: Gemini Direct | Variant B: Gemini + Tandem MCP v3.6.1 |
| --- | --- | --- |
| Who writes the code | `Gemini 4 Hydrogen` | `qwen3.8-27b@iq3_s` under contract (`job 20261117-011201-9212f9`) |
| Output | [`animation_direct/index.html`](animation_direct/index.html), 14,726 B, 466 lines | [`animation_tandem/index.html`](animation_tandem/index.html), 13,295 B, 509 lines |
| Cloud output tokens (est.) | ~4,091 | ~2,343: contract 4,450 chars + harness 3,986 chars (`check_page.js`) |
| Cloud output tokens saved (est.) | n/a | **~1,748 (42.7%)** |
| Cloud input tokens (est.) | 0 | ~5,529: receipt 8,445 chars + `job_evidence` 11,459 chars |
| Local tokens | 0 | 63,324 |
| Wall time | 1 cloud turn | **984.2 s** (~16.4 min) |
| Executor result | n/a | `VERIFIED`, 6 steps, 0 repairs, 46/46 constraints cited |
| Independent verification | `node check_page.js` PASS | `node check_page.js` PASS |
| Constraints met on inspection | n/a | **46 of 46** |
| Fixes after generation | none | none |

Live interactive comparison: **[animation_comparison.html](https://alenoc.github.io/tandem-mcp/benchmarks/gemini_3_6_1/animation_comparison.html)** ([source](animation_comparison.html)).

---

## 6. 3D neon portal (software 3D engine, four modules)

Identical scene specification and 4-task `delegate_many` batch contract ([`../contracts/scene3d.json`](../contracts/scene3d.json)) as the historical benchmark, with 0 post-generation fixes.

| Task | File | Constraints | Check | Result | Local tokens | Wall time |
| --- | --- | ---: | --- | --- | ---: | ---: |
| `html_css` | `index.html` (3,703 B, 162 lines) | 12 | element IDs, script order, backdrop-filter | `VERIFIED`, 4 steps, 0 repairs | 15,908 | 247.6 s |
| `scene_data` | `scene.js` (3,972 B, 129 lines) | 18 | node check + counts (36, 6, 180, 110) | `VERIFIED`, 5 steps, 0 repairs | 35,776 | 427.3 s |
| `engine3d` | `engine3d.js` (12,222 B, 398 lines) | 32 | `node --check` + `node check_engine.js` | `VERIFIED`, 10 steps, 1 repair | 152,696 | 1558.0 s |
| `app_loop` | `app.js` (1,314 B, 41 lines) | 7 | `node --check` + `Engine3D.init` / `getStats` | `VERIFIED`, 4 steps, 0 repairs | 32,649 | 231.2 s |

| | Variant A: Gemini Direct | Variant B: Gemini + Tandem MCP v3.6.1 |
| --- | --- | --- |
| Who writes the code | `Gemini 4 Hydrogen` (1 file) | `qwen3.8-27b@iq3_s` (`batch 20261117-012957-1c188f`, 4 modules) |
| Output | [`portal_direct/index.html`](portal_direct/index.html), 17,593 B, 518 lines | [`portal_tandem/`](portal_tandem/), 21,211 B, 730 lines across 4 files |
| Cloud output tokens (est.) | ~4,887 | ~2,396: contracts 6,874 chars + harness 1,753 chars (`check_engine.js`) |
| Cloud output tokens saved (est.) | n/a | **~2,491 (51.0%)** |
| Cloud input tokens (est.) | 0 | ~9,708: receipts 16,720 chars + `job_evidence` 18,228 chars |
| Local tokens | 0 | 237,029 |
| Wall time | 1 cloud turn | **2464.4 s** (~41.1 min) |
| Executor result | n/a | 4 of 4 tasks `VERIFIED`, 1 repair (`engine3d`), 69/69 constraints cited |
| Independent verification | Node DOM/canvas loop PASS (30 frames) | `node check_engine.js` PASS + Node 4-module wiring PASS (30 frames, 84 polys, 110 parts) |
| Constraints met on inspection | n/a | **69 of 69** (including camera-depth sorting & portal depth order) |
| Fixes after generation | none | none |

Live interactive comparison: **[scene3d_comparison.html](https://alenoc.github.io/tandem-mcp/benchmarks/gemini_3_6_1/scene3d_comparison.html)** ([source](scene3d_comparison.html)).

---

## 7. Comparison and conclusions: Historical Fable 5.2 (v3.1.0) vs. Gemini 4 Hydrogen (v3.6.1)

> **Important methodological note:** The two campaigns differ in **both** the cloud orchestrator (`Fable 5.2` vs `Gemini 4 Hydrogen`) **and** the Tandem MCP version (`3.1.0` vs `3.6.1`), as well as repository file sizes (`README.md`, `agent.py`, `tandem_mcp/*.py`, `git log` at `010cbb6`) and probed local throughput (`11.2` vs `23.6` tok/s). Differences below reflect the **complete configuration** and should not be attributed solely to the orchestrator or solely to Tandem.

| Workload | Fable 5.2 + Tandem 3.1.0 | Gemini 4 Hydrogen + Tandem 3.6.1 |
| --- | --- | --- |
| `digest_file` (`README.md`) | 27,943 B -> 405 B, 98.6% saved, 10,298 local tok, 66.15 s, 0/2 quotes (`unsupported`) | 8,468 B -> 811 B, 90.4% saved, 3,602 local tok, 36.16 s, 1/3 quotes (`contested`) |
| `digest_file` grep (`agent.py`) | 85,889 B -> 692 B, 99.2% saved, 643 local tok, 14.11 s, 3/3 quotes | 99,739 B -> 480 B, 99.5% saved, 837 local tok, 22.22 s, 2/2 quotes |
| `digest_many` (`tandem_mcp/*.py`) | 209,756 B -> 1,509 B, 99.3% saved, 108,207 local tok, 800.32 s, 8/8 quotes | 250,640 B -> 1,512 B, 99.4% saved, 107,172 local tok, 863.99 s, 11/11 quotes |
| `digest_command` (`git log -n 30 --stat`) | 18,052 B -> 1,441 B, 92.0% saved, 18,528 local tok, 109.87 s, 8/8 quotes | 13,221 B -> 425 B, 96.8% saved, 53,712 local tok, 420.63 s |
| `extract_from_file` (`pyproject.toml`) | 786 B -> 113 B, 85.6% saved, 633 local tok, 9.82 s, 0 loose values | 786 B -> 113 B, 85.6% saved, 633 local tok, 11.94 s, 0 loose values |
| `delegate` micro bugfix | 1,047 B -> 432 B, 58.7% saved, 6,297 local tok, 25.32 s, `VERIFIED` (4 steps, 0 repairs) | 1,047 B -> 432 B, 58.7% saved, 6,498 local tok, 27.74 s, `VERIFIED` (4 steps, 0 repairs) |
| `delegate` multi-file bugfix | 6,094 B -> 476 B, 92.2% saved, 8,066 local tok, 32.79 s, `VERIFIED` (4 steps, 0 repairs) | 6,094 B -> 476 B, 92.2% saved, 8,278 local tok, 37.07 s, `VERIFIED` (4 steps, 0 repairs) |
| Orbital animation (Tandem) | 12,499 B, 29.4% output tok saved, ~4,199 input tok, 104,087 local tok, 1,120.6 s, 46/46 met | 13,295 B, 42.7% output tok saved, ~5,529 input tok, 63,324 local tok, 984.2 s, 46/46 met |
| 3D neon portal (Tandem) | 18,243 B, 43.0% output tok saved, ~7,814 input tok, 199,182 local tok, 1,889.8 s, **67/69 met** | 21,211 B, 51.0% output tok saved, ~9,708 input tok, 237,029 local tok, 2,464.4 s (1 repair), **69/69 met** |

### Key Takeaways

1. **Reading & bugfix savings remain highly consistent:** Targeted grep (`99.5%`), multi-file survey (`99.4%`), structured extraction (`85.6%`), and test-driven bugfixes (`58.7%` / `92.2%`) reproduce the historical savings profile closely.
2. **Evidence flagging continues to surface partial/unsupported quotes:** On `README.md`, 2 of 3 quotes were dropped and the answer was marked `contested` rather than silently accepted.
3. **3D Portal achieved 69/69 constraints on inspection:** Unlike the 3.1.0 run (where `engine3d.js` sorted by origin distance and used a constant portal depth, meeting 67/69), the 3.6.1 run used 1 repair on `engine3d` and satisfied all 69/69 constraints including camera-depth sorting and portal depth ordering.
4. **Total cloud tokens on generation still exceed direct generation when counting input inspection:** While cloud output tokens saved were `42.7%` (animation) and `51.0%` (3D portal), inspecting receipts and `job_evidence` added `~5,529` and `~9,708` estimated cloud input tokens.
