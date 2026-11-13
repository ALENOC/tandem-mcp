# Tandem MCP — Live Benchmark Results

Measured live with [`benchmarks/run_benchmark.py`](run_benchmark.py) (cache disabled, isolated temporary `TANDEM_HOME`, sequential execution).

## Environment

- **Date**: 2026-11-13
- **Platform**: Linux x86_64 / Python 3.13.17
- **Local server**: LM Studio (`http://127.0.0.1:1234/v1`)
- **Local model**: `qwen3.8-27b@iq3_s` (context `65536`, probed speed `11.1` tokens/s, native tool calls + reasoning stripped)
- **Sandbox**: `bubblewrap` (machine read-only, workspace writable, credentials hidden, env secrets stripped, no network)
- **Token estimate convention**: `1 orchestrator token ≈ 3.6 chars` (`store.CHARS_PER_TOKEN`), comparing raw material bytes vs. the compact output/receipt returned to the cloud orchestrator.

---

## 1. Reading & Evidence Benchmarks (`digest_file`, `digest_many`)

| Scenario | Tool | Source read | Returned to cloud | Cloud tokens (without → with) | Est. cloud tokens saved | Local tokens | Wall time | Evidence check |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Full-file doc QA (`README.md`) | `digest_file` | 23,036 B (360/360 lines) | 491 B | 6,399 → 136 | **6,262 (97.9%)** | 9,141 | 66.24 s | `0` ok / `3` dropped (`unsupported`)* |
| Targeted grep QA (`agent.py`) | `digest_file (grep)` | 75,402 B (7/1,500 lines) | 692 B | 20,945 → 192 | **20,753 (99.1%)** | 643 | 14.01 s | `3` ok / `0` dropped (`quote_only`) |
| Multi-file survey (`tandem_mcp/*.py`) | `digest_many` (8 files) | 172,846 B (8 files) | 1,631 B | 48,013 → 453 | **47,560 (99.1%)** | 77,047 | 532.05 s | `12` ok / `0` dropped (`checked`) |

*\*Note on `README.md`: the local model paraphrased its quotes instead of copying them verbatim, so Tandem's lexical evidence verifier dropped all 3 quotes and flagged `claim_supported = unsupported`. This is an intentional safety feature rather than a silent pass.*

---

## 2. Delegated Coding Benchmarks (`delegate`)

Baseline assumes the cloud orchestrator reads the workspace files plus a ~600 B failing test output.

| Scenario | Workspace size (+test out) | Receipt returned | Cloud tokens (without → with) | Est. cloud tokens saved | Local tokens | Wall time | Outcome |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Micro bugfix (1 tiny file, 6 lines) | 1,047 B | 438 B | 291 → 122 | **169 (58.2%)** | 5,581 | 24.28 s | `VERIFIED` (4 steps, 0 repairs) |
| Multi-file bugfix (`config_loader.py` + 3 files) | 6,094 B | 469 B | 1,693 → 130 | **1,562 (92.3%)** | 7,432 | 34.66 s | `VERIFIED` (4 steps, 0 repairs) |

---

## 3. Additional Live MCP Tool Benchmarks (`digest_command`, `extract_from_file`)

Measured live via MCP calls against `qwen3.8-27b@iq3_s` on LM Studio:

| Scenario | Tool | Input size | Returned to cloud | Est. cloud tokens saved | Wall time | Verification |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Recent git history (`git log -n 30 --stat`) | `digest_command` | 14,149 B (336 lines) | 1,422 B | **3,535 (90.0%)** | 147 s | 10/10 quotes verified |
| Project manifest (`pyproject.toml`) | `extract_from_file` | 686 B (23 lines) | 143 B | **151 (79.2%)** | 12 s | JSON Schema validated |

---

## 4. Animation Generation A/B Comparison (Without vs. With Tandem MCP)

Identical prompt: generate a self-contained single-file HTML5 `<canvas>` orbital particle simulation (`index.html`) with `requestAnimationFrame`, `devicePixelRatio` scaling, radial-gradient star with corona pulse, 5+ planets with moons and fading trails, 150+ twinkling stars, glassmorphism HUD (Play/Pause, Trails toggle, Reset, Speed `0.2x`–`3.0x`, live FPS/time/bursts), and click-to-spawn radial particle bursts.

| Metric | Without Tandem (`Gemini Hydrogen` Cloud Direct) | With Tandem MCP (`Gemini Hydrogen` orchestrator + `qwen3.8-27b@iq3_s` local) |
| --- | --- | --- |
| Output file | **[Live Demo](https://alenoc.github.io/tandem-mcp/benchmarks/animation_without_tandem/)** ([source](animation_without_tandem/index.html)) | **[Live Demo](https://alenoc.github.io/tandem-mcp/benchmarks/animation_with_tandem/)** ([source](animation_with_tandem/index.html)) |
| Size / Lines | 10,343 B / 272 lines | 10,970 B / 364 lines |
| Cloud tokens to write code | ~2,873 output tokens | ~130 receipt tokens (**~2,743 tok / 95.5% cloud output saved**) |
| Local executor tokens | 0 | 17,449 tokens (`2` steps, `0` repairs) |
| Wall time | Immediate (cloud turn) | 322.7 s |
| JS syntax (`node --check`) | PASS | PASS |
| DOM / feature check | PASS (5 planets, 3 moons, 180 stars) | PASS (6 planets, 3 moons, 180 stars) |
| Side-by-side viewer | **[Live Side-by-Side Demo](https://alenoc.github.io/tandem-mcp/benchmarks/animation_comparison.html)** ([source](animation_comparison.html)) | **[Live Side-by-Side Demo](https://alenoc.github.io/tandem-mcp/benchmarks/animation_comparison.html)** ([source](animation_comparison.html)) |

---

## 5. Honest Takeaways: When Tandem Pays Off (and When It Doesn't)

1. **Highest ROI (`digest_file` with `grep`, `digest_many`)**:
   - Targeted `grep` on a 53 KB source file saved **~14,508 cloud input tokens (98.7%)** in **16 s**.
   - Surveying 8 Python modules (150 KB) saved **~41,122 cloud input tokens (98.9%)**, at the cost of **~7m 54s** on a single 11 tok/s local GPU.
2. **Low ROI (`delegate` on trivial 1-file edits)**:
   - Fixing a 6-line file took **19.1 s** and saved only **~174 cloud tokens**. Delegating is only worthwhile when there are multiple files to inspect, larger context, or iterative test-fix-repair cycles.
3. **Single-GPU concurrency limit**:
   - Sending multiple heavy `digest_*` calls in parallel queues requests on a single local GPU and can hit the 3-minute MCP client timeout. Sequential calls or `grep` pre-filtering avoid this.
4. **Verification catches local-model hallucinations**:
   - In the `README.md` run, the local model's non-verbatim quotes were caught and flagged (`0/3` verified) instead of being trusted blindly.

---

## 6. 3D Neon Portal & Floating Monolith (Quality-Preserved Hybrid Delegation)

Re-tested after implementing Tandem's hybrid quality-preservation workflow (tight architectural specification, `delegate_many` module decomposition, orchestrator PNG visual inspection, and targeted `job_continue` polish).

| Variant | Model(s) | Output | Cloud Output Tokens | Cloud Tokens Saved | Local Tokens | Verification |
| :--- | :--- | :--- | ---: | ---: | ---: | :--- |
| **Without Tandem** | `Gemini Hydrogen` (cloud direct) | [`scene3d_without_tandem/index.html`](scene3d_without_tandem/index.html) (403 lines, 15,724 B) | ~4,368 | — | — | `node --check` PASS, `60 FPS`, `84` polys |
| **With Tandem MCP** | `Gemini Hydrogen` (orchestrator) + `qwen3.8-27b@iq3_s` (local) | [`scene3d_with_tandem/`](scene3d_with_tandem/index.html) (`index.html` 166 L / 3,728 B, `engine3d.js` 394 L / 13,482 B, `app.js` 18 L / 557 B — total 578 lines, 17,767 B) | ~650 | **~3,718 (85.1%)** | 314,126 (`6,876` + `282,803` + `24,447`) | All 3 jobs `VERIFIED` (`node --check` PASS), `job_feedback(accepted=True)`, `60 FPS`, `164` polys, visual PNG parity confirmed |

- **2D Orbital Simulation GIFs**: Both `animation_without_tandem.gif` (390,921 B) and `animation_with_tandem.gif` (438,519 B) were re-rendered at `540x345` without synthetic mouse clicks so they faithfully show natural orbital motion.
- **3D Neon Portal GIFs**: Both `scene3d_without_tandem.gif` (2,056,923 B) and `scene3d_with_tandem.gif` (2,049,532 B) were rendered at `540x345` from headless Chrome CDP.
- **Side-by-side interactive comparison**: [`scene3d_comparison.html`](scene3d_comparison.html).
