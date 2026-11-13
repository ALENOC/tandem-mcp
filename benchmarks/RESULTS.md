# Tandem MCP: Live Benchmark Results

**Trade-off first.** Tandem can save cloud tokens, and it is slower: the work runs on the local model, whose speed depends on your hardware (here about 11 tokens per second). Reading and test-driven fixes save 59 to 99% of the cloud tokens for seconds to minutes of waiting. Generating new code from a contract keeps the quality but saves much less, because the design has to be written into the contract, and it takes tens of minutes instead of one cloud turn.

Sections 1 and 2 are measured by [`benchmarks/run_benchmark.py`](run_benchmark.py) (cache disabled, isolated temporary `TANDEM_HOME`, sequential execution, raw numbers in [`latest.json`](latest.json)). Sections 3 to 5 compare code written directly by the cloud model with code written by the local model under a contract (raw numbers in [`generation.json`](generation.json), contracts in [`contracts/`](contracts/)).

## Environment

- **Date**: 2026-11-13
- **Tandem MCP**: 3.1.0, strict contract on
- **Platform**: Linux x86_64 / Python 3.13.17
- **Hardware**: Intel Core i9-9900K @ 3.60GHz (16 threads), 22 GiB RAM, AMD Radeon Navi 21 (RX 6800/6900 XT, 16 GiB VRAM)
- **Orchestrator (cloud)**: `Fable 5.2`
- **Executor (local)**: `qwen3.8-27b@iq3_s` on LM Studio (`http://127.0.0.1:1234/v1`), context `65536`, probed speed `11.2` tokens/s, native tool calls, forced JSON schema, reasoning stripped
- **Sandbox**: `bubblewrap` (machine read only, workspace writable, credentials and host sockets hidden, env secrets stripped, no network)
- **Token estimate**: `1 cloud token = 3.6 characters` (`store.CHARS_PER_TOKEN`)

### LM Studio configuration of the executor

| Load setting | Value | | Inference setting | Value |
| --- | --- | --- | --- | --- |
| Model file | `unsloth/Qwen3.8-27B-GGUF/Qwen3.8-27B-UD-IQ3_S.gguf` (12.04 GB, 27B, IQ3_S) | | Temperature | 0.15 (Tandem sets its own per call: 0.1, and 0.7 for extra `ask` samples) |
| Runtime | LM Studio 0.4.28, `llama.cpp` Vulkan (`linux-x86_64-vulkan-avx2` 2.73.0) | | Top K / Top P / Min P | 20 / 0.95 / 0.05 |
| Context length | 65536 (model supports 262144) | | Repeat penalty | 1 |
| GPU offload | 65 layers (all) | | Presence penalty | off |
| CPU thread pool | 8 | | Thinking | enabled, reasoning budget 1024 tokens |
| Evaluation / physical batch | 1024 / 512 | | Context overflow | rolling window |
| Max concurrent predictions | 1 | | Limit response length | off |
| Unified KV cache | on | | Structured output | off (Tandem sends a schema per call) |
| KV cache on GPU | on, K cache `Q8_0`, V cache `Q4_0` | | Seed | random |
| Flash attention | on | | | |
| Context checkpoints | 32 | | | |
| Keep model in memory / mmap | on / on | | | |
| On-demand tensor loading | auto | | | |
| Speculative decoding | MTP, max draft tokens 4, min 0, draft probability 0.75 | | | |
| RoPE frequency base / scale | auto / auto | | | |

Speed and memory use follow from these settings: a different quantization, context length, GPU offload or runtime changes every wall time below.

---

## 1. Reading and evidence (`digest_file`, `digest_many`, `digest_command`, `extract_from_file`)

The cloud model asks a question and receives a short answer with quotes that the server has looked up in the source, instead of reading the material.

| Scenario | Tool | Source read | Returned to cloud | Cloud tokens (without → with) | Est. cloud tokens saved | Local tokens | Wall time | Evidence check |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Full-file doc QA (`README.md`) | `digest_file` | 27,943 B | 405 B | 7,762 → 112 | **7,649 (98.6%)** | 10,298 | 66.15 s | 0 ok / 2 dropped (`unsupported`) |
| Targeted grep QA (`agent.py`) | `digest_file (grep)` | 85,889 B | 692 B | 23,858 → 192 | **23,666 (99.2%)** | 643 | 14.11 s | 3 ok / 0 dropped (`quote_only`) |
| Multi-file package survey (`tandem_mcp/*.py`) | `digest_many (8 files)` | 209,756 B | 1,509 B | 58,266 → 419 | **57,846 (99.3%)** | 108,207 | 800.32 s | 8 ok / 0 dropped (`checked`) |
| Recent git history (`git log -n 30 --stat`) | `digest_command` | 18,052 B | 1,441 B | 5,014 → 400 | **4,614 (92.0%)** | 18,528 | 109.87 s | 8 ok / 0 dropped |
| Project manifest (`pyproject.toml`) | `extract_from_file` | 786 B | 113 B | 218 → 31 | **187 (85.6%)** | 633 | 9.82 s | schema validated, 0 values not in the source |

On the `README.md` question the local model paraphrased its quotes instead of copying them, so the verifier dropped both and marked the answer `unsupported`. The answer reaches the cloud model flagged as unverified, which is the intended behaviour.

---

## 2. Delegated fixes with an existing test (`delegate`)

The baseline is the cloud model reading the workspace files plus about 600 characters of failing test output. With Tandem it writes a contract (goal, `write_globs`, the test as `verify_commands`) and reads a receipt.

| Scenario | Workspace + test output | Receipt returned | Cloud tokens (without → with) | Est. cloud tokens saved | Local tokens | Wall time | Outcome |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Micro bugfix (1 tiny file, 6 lines) | 1,047 B | 432 B | 291 → 120 | **171 (58.7%)** | 6,297 | 25.32 s | `VERIFIED` (4 steps, 0 repairs) |
| Multi-file bugfix (`config_loader.py` + 3 other files) | 6,094 B | 476 B | 1,693 → 132 | **1,561 (92.2%)** | 8,066 | 32.79 s | `VERIFIED` (4 steps, 0 repairs) |

---

## 3. Generation from a contract: method

The question is whether the local model can write new code of the same quality as the cloud model, and what that costs. The rules of this benchmark mirror real use, where the orchestrator does not have a finished solution to compare with:

1. **Direct variant**: `Fable 5.2` writes the file itself. Cost: the output tokens of the file.
2. **Tandem variant**: `Fable 5.2` writes a contract once, before any output exists, and `qwen3.8-27b@iq3_s` writes the code. Cost: the output tokens of the contract and of the check harness, plus the input tokens of the receipt and of the inspection.
3. **Strict contract**: named `write_globs`, `verify_commands` that run the code, and every design decision as an atomic constraint (one requirement, at most 160 characters). The server refuses a contract without them.
4. **Evidence**: at `finish` the executor cites, for every constraint, a line of a file. The server looks the quote up and sends the work back when a constraint has none.
5. **Inspection**: the orchestrator reads `job_evidence` (the cited lines) and renders the page in headless Chrome. It judges the result against the contract only.
6. **No fix after generation**: no `job_continue`, no manual edit. What the executor delivered is what is published here.

A first attempt at the animation used the user prompt as the goal with three loose constraints. It was `VERIFIED` and worked, and it looked plainer than the direct version (flat planets, no orbit lines), because the design decisions had been left to the local model. Nothing in the contract said otherwise, so an orchestrator without a reference would not have noticed. That run led to the strict contract and is not counted below.

---

## 4. Orbital particle simulation (single file)

Prompt (identical for both variants): a self-contained `index.html` with a full-viewport canvas, a glowing star, at least 5 planets with moons and fading trails, 150 or more twinkling stars, a glassmorphism HUD (Play/Pause, Trails, Reset, speed slider, FPS, time, burst count) and click-to-spawn particle bursts. Full text in the [README](../README.md#benchmarks).

| | Without Tandem | With Tandem MCP |
| --- | --- | --- |
| Who writes the code | `Fable 5.2` | `qwen3.8-27b@iq3_s` under a contract by `Fable 5.2` |
| Output | [`animation_without_tandem/index.html`](animation_without_tandem/index.html), 11,956 B, 272 lines | [`animation_with_tandem/index.html`](animation_with_tandem/index.html), 12,499 B, 459 lines |
| Cloud output tokens | ~3,321 | ~2,343: contract 4,450 chars ([`contracts/animation.json`](contracts/animation.json)) + harness 3,986 chars ([`check_page.js`](animation_with_tandem/check_page.js)) |
| Cloud output tokens saved | n/a | **~978 (29.4%)** |
| Cloud input tokens | 0 | ~4,199: receipt 8,457 chars + `job_evidence` 6,661 chars |
| Local tokens | 0 | 104,087 |
| Wall time | one cloud turn | 1120.6 s |
| Executor result | n/a | `VERIFIED`, 9 steps, 0 repairs, 46 of 46 constraints with checked evidence |
| Check | n/a | `node check_page.js`: runs the inline script on a stub DOM, 30 frames, click burst, fade-out, slider, pause, reset (failed before the job) |
| Constraints met on inspection | n/a | 46 of 46 |
| Headless Chrome | 60 FPS, no console error | 60 FPS, no console error |
| Fixes after generation | none | none |

Side by side: **[live comparison](https://alenoc.github.io/tandem-mcp/benchmarks/animation_comparison.html)** ([source](animation_comparison.html)).

---

## 5. 3D neon portal (software 3D engine, four modules)

Both variants implement the same scene: a two-tier platform, twin pillars, lintel and crown cap (36 box faces), six orbiting octahedral crystals (48 triangles), a portal core with two counter-rotating rings, a cyber grid floor, 180 stars, 110 rising particles, an orbiting camera and a HUD. The direct variant is one file. The Tandem variant is one `delegate_many` batch of four tasks, each with its own contract.

| Task | File | Constraints | Check | Result | Local tokens | Wall time |
| --- | --- | ---: | --- | --- | ---: | ---: |
| `html_css` | `index.html` (3,529 B, 153 lines) | 12 | element ids and script order present | `VERIFIED`, 4 steps, 0 repairs | 17,009 | 184.6 s |
| `scene_data` | `scene.js` (3,157 B, 88 lines) | 18 | node script counts 36 faces, 6 crystals, 180 stars, 110 particles | `VERIFIED`, 3 steps, 0 repairs | 19,521 | 265.2 s |
| `engine3d` | `engine3d.js` (10,342 B, 335 lines) | 32 | `node check_engine.js`: renders 3 frames on a stub canvas, expects 84 polygons and 110 particles | `VERIFIED`, 11 steps, 0 repairs | 133,153 | 1254.6 s |
| `app_loop` | `app.js` (1,215 B, 40 lines) | 7 | `node --check` and calls present | `VERIFIED`, 4 steps, 0 repairs | 29,499 | 184.2 s |

| | Without Tandem | With Tandem MCP |
| --- | --- | --- |
| Who writes the code | `Fable 5.2` | `qwen3.8-27b@iq3_s` under four contracts by `Fable 5.2` |
| Output | [`scene3d_without_tandem/index.html`](scene3d_without_tandem/index.html), 15,122 B, 327 lines | [`scene3d_with_tandem/`](scene3d_with_tandem/), 18,243 B, 616 lines in 4 files |
| Cloud output tokens | ~4,201 | ~2,396: contracts 6,874 chars ([`contracts/scene3d.json`](contracts/scene3d.json)) + harness 1,753 chars ([`check_engine.js`](scene3d_with_tandem/check_engine.js)) |
| Cloud output tokens saved | n/a | **~1,805 (43.0%)** |
| Cloud input tokens | 0 | ~7,814: receipts 17,360 chars + `job_evidence` 10,772 chars |
| Local tokens | 0 | 199,182 |
| Wall time | one cloud turn | 1889.8 s |
| Executor result | n/a | 4 of 4 tasks `VERIFIED`, 0 repairs, 69 of 69 constraints with checked evidence |
| Constraints met on inspection | n/a | 67 of 69 |
| Headless Chrome | 60 FPS, 84 polygons, no console error | 60 FPS, 84 polygons, 110 particles, no console error |
| Fixes after generation | none | none |

**The two constraints that are not met.** `engine3d.js` sorts polygons by their distance from the scene origin, and gives the portal a constant depth, instead of using the depth from the camera that the contract asks for ("sorted by mean depth", "the portal is drawn inside that same depth order"). The cited lines made this visible during the `job_evidence` inspection (`items.push({ type: 'portal', d: 0.55 * 0.55 })`). The check harness counts polygons and does not test the drawing order, so the job was `VERIFIED`. From the default camera the picture is close to the direct version; from other angles some faces can overlap in the wrong order. The result is published as delivered.

Side by side: **[live comparison](https://alenoc.github.io/tandem-mcp/benchmarks/scene3d_comparison.html)** ([source](scene3d_comparison.html)).

GIFs (`540x345`, 72 frames at 12 fps, headless Chrome, no synthetic input): `animation_without_tandem.gif`, `animation_with_tandem.gif`, `scene3d_without_tandem.gif`, `scene3d_with_tandem.gif`.

---

## 6. Takeaways: where Tandem pays and where it does not

1. **Reading pays almost always.** A targeted `grep` question on an 86 KB source file cost about 190 cloud tokens instead of 23,900, in 14 seconds. A survey of 8 modules saved about 57,800 cloud tokens and took more than 13 minutes on one local GPU.
2. **Fixes with an existing test pay when there is something to read.** The four-file fix saved 92% in 33 seconds. The six-line fix saved 171 tokens in 25 seconds: not worth a delegation.
3. **Generation keeps the quality only when the design is in the contract, and then it saves less.** With every design decision written as a constraint the local model delivered both demos at the first attempt, with no repair. The contract and its check cost 57 to 71% of the tokens of writing the code directly, so the saving on cloud output tokens was 29.4% and 43.0%.
4. **Count the input tokens too.** Receipts and the `job_evidence` view add about 4,199 and 7,814 cloud input tokens. Input tokens are usually billed at a fraction of output tokens, so whether the total is a saving depends on the price list. In token count alone, generation through Tandem used more cloud tokens than writing the code directly.
5. **It is slower.** 19 and 31 minutes of local generation against one cloud turn. The local model produced about 11 tokens per second on this hardware.
6. **A check and a cited line are not a proof.** Both jobs were `VERIFIED`. The inspection of the cited lines still found two constraints of the 3D engine that were not met as written, and anything the contract forgets to state stays unchecked.
7. **Unverified answers are flagged, not hidden.** In the `README.md` reading run the paraphrased quotes were dropped and the answer was marked `unsupported`.

## Reproduce

```sh
.venv/bin/python benchmarks/run_benchmark.py     # sections 1 and 2, writes benchmarks/latest.json
```

For sections 4 and 5, empty the `*_with_tandem` folders except the check harness (`check_page.js`, `check_engine.js`) and pass the files in [`contracts/`](contracts/) to `delegate` and `delegate_many`, with `workspace` set to the absolute path of the folder.
