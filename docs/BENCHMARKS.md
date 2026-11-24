# Benchmarks

Tandem **4.1.0**, November 2026. Cloud orchestrator: **Opus 5.5** in Claude Code. Local executor: `qwen3.8-27b@iq3_s` on LM Studio. Earlier campaigns with other orchestrators were removed from the repository and stay in the git history.

## Method

Each task is run as a counterbalanced pair in fresh workspaces:

- **Direct:** Opus does the work itself. No MCP server is loaded.
- **With Tandem:** the same request with the fixed suffix "Usa Tandem.", and the Tandem MCP server in the autonomous profile (`TANDEM_PROFILE=autonomous`, fresh `TANDEM_HOME` per attempt). Opus writes a contract and calls `delegate` once. The call blocks while the local model writes, runs the checks and repairs, with no cloud call. Opus gets back a one-line `ACCEPTED`, or only what still fails.

Both arms run `claude -p` with the same isolated setup: `--setting-sources ""` (no user settings, plugins or `CLAUDE.md`), `--disable-slash-commands`, `--strict-mcp-config`, permissions bypassed. The arm that runs first alternates from pair to pair. The Tandem code of each run is copied before the first attempt and its SHA-256 is recorded.

**Cloud cost** is `total_cost_usd` from the `result` event of `claude -p --output-format json` (list prices, every model used in the attempt). Input, cache writes, cache reads and output tokens are recorded too. **Main metric:** cloud cost per successful result, with failed attempts counted in the cost:

    cost per success = cost of all attempts / successful attempts

An attempt **succeeds** when an independent evaluator, which neither arm sees, passes it three times in a row and the attempt ended inside its time budget. All 4.1.0 runs use the exact same evaluators as 4.0.0 (identical SHA-256 hashes recorded in `REEVAL_4_1.json` and `REEVAL_V3.json`). The local model also costs time and power; those are reported next to the cloud figures.

Runner: [`run_pair.py`](../benchmarks/opus/run_pair.py) · Tasks and evaluators: [`tasks.py`](../benchmarks/opus/tasks.py) · Re-evaluation: [`reeval.py`](../benchmarks/opus/reeval.py) · 4.1.0 combined report: [`REEVAL_4_1.json`](../benchmarks/opus/REEVAL_4_1.json) · 4.0.0 baseline report: [`REEVAL_V3.json`](../benchmarks/opus/REEVAL_V3.json)

Interactive version, also on mobile: [alenoc.github.io/tandem-mcp](https://alenoc.github.io/tandem-mcp/) (built from [`site/`](../site) by `scripts/build_site.py`).

## Test machine and local model

All local work ran on one desktop PC; the local model ran entirely on the GPU.

| Part | Value |
| --- | --- |
| CPU | Intel Core i9-9900K, 8 cores, 16 threads, 3.6 GHz |
| GPU | AMD Radeon RX 6800 series (Navi 21), 16 GB VRAM |
| RAM | 22 GiB available to the system |
| OS | Ubuntu 26.04.1 LTS, Linux 7.0 |
| Model server | LM Studio 0.4.28, llama.cpp Vulkan runtime 2.73.0 |

| Local model setting | Value |
| --- | --- |
| Model | Qwen3.8 27B, unsloth GGUF `Qwen3.8-27B-UD-IQ3_S.gguf` (LM Studio id `qwen3.8-27b@iq3_s`) |
| Quantization | IQ3_S (about 3 bits per weight), 12.0 GB on disk |
| Context length | 65,536 tokens (the model supports 262,144) |
| GPU offload | all layers |
| KV cache | K in `q8_0`, V in `q4_0` |
| Parallel sessions | 1 |
| CPU threads | 8 |
| Evaluation batch | 1,024 |
| Reasoning | on, budget 1,024 tokens (LM Studio model defaults) |
| Sampling sent by Tandem | temperature 0.1 (0.7 for 2 replies after 3 identical repeated calls), up to 12,000 tokens per executor step (`TANDEM_REPLY_TOKENS`; was 4,000 in 4.0.0), native tool calls, prefix-stable prompt cache |
| Other LM Studio sampling defaults | top-k 20, repeat penalty 1.0 |
| Tandem limits and gates per job | `TANDEM_JOB_SECONDS` = task budget minus 5 minutes, `TANDEM_MAX_REPAIRS` 20, `TANDEM_MAX_STEPS` 160, `TANDEM_WEB_MIN_FPS` 40, `TANDEM_SLOW_CHECK_S` 30 |

The cloud side was Opus 5.5 (`claude-opus-5-5`) in Claude Code 2.1.330.

## Results (4.1.0 series)

Four medium and large tasks across three progressive 4.1.0 runs (`20261124-030230_adversarial_pilot1`, 1 pair; `20261124-052842_adversarial_confirm`, 2 pairs; `20261124-103103_adversarial_final`, 1 pair): 4 pairs per task, 16 attempts per arm. Small 5-line edits (`py_discount`) were already measured in the 4.0.0 baseline below (+10% cost) and are routed direct by the guide.

| Task | Budget | Direct: cost per success | Tandem: cost per success | Change |
| --- | ---: | --- | --- | ---: |
| Cron parser module with tests | 40 min | $0.4405 · 3/4 · 97 s | $0.1729 · 3/4 · 19 min | **-61%** |
| Boids web simulation | 40 min | $0.2323 · 4/4 · 67 s | $0.1172 · 4/4 · 7 min | **-50%** |
| Orbital web simulation | 40 min | $1.1947 · 1/4 · 81 s | $0.4703 · 2/4 · 39 min | **-61%** |
| 3D neon portal (4 files) | 70 min | $1.0556 · 2/4 · 2.4 min | $0.2318 · 2/4 · 23 min | **-78%** |
| **All 16 attempts per arm** | | **$5.56 total · 10/16 · $0.556 per success** | **$2.39 total · 11/16 · $0.217 per success** | **-57% total, -61% per success** |
| **Without 2 infra incidents (15)** | | **$5.21 total · 10/15 · $0.521 per success** | **$2.05 total · 10/15 · $0.205 per success** | **-61% total, -61% per success** |

Each cell gives the cost per success, the successes inside the budget and the median time per attempt.

| Cloud tokens, all 16 attempts | Direct | With Tandem | Change |
| --- | ---: | ---: | ---: |
| Output | 165,432 | 54,755 | **-67%** (-72% excl. incidents) |
| Cache writes | 241,310 | 137,266 | -43% |
| Cache reads | 1,583,886 | 988,380 | -38% |
| Local model tokens (free) | 0 | 4,800,809 | |

Output tokens are the most expensive part of the cost, and Tandem moves most of them to the local model.

### Infrastructure incidents in the final run

The final run (`20261124-103103_adversarial_final`) hit one infrastructure incident per arm:

- **Tandem Orbital (pair 1):** a GPU reset (`vk::Queue::submit: ErrorDeviceLost`) crashed `llama-server` on the first model call. LM Studio returned `400`, so Opus wrote the page itself (`$0.346`, `123 s`, `0` local tokens). It counts as a success under the strict rule, but it was not local work; 4.1.0 now reports the server error in the receipt and advises re-delegating instead of calling `job_continue`.
- **Direct Cron (pair 1):** a 74-minute API stall between two tool calls pushed the attempt past its 40-minute budget (`4,506 s`). The artifact passes the evaluator.

Excluding those two attempts gives **10/15** successes on both arms (`$0.205` with Tandem against `$0.521` direct, **-61%**).

## What changed from 4.0.0 to 4.1.0

Comparing the same 4 tasks (`py_cron`, `web_boids`, `gen_orbital`, `gen_portal`) between the 4.0.0 baseline (`v3`, 12 attempts per arm) and the 4.1.0 series (16 attempts per arm):

| Metric (4 shared tasks) | Tandem 4.0.0 (`v3`) | Tandem 4.1.0 series | Direct (`v3` / 4.1.0 runs) |
| --- | --- | --- | --- |
| Successes in budget | 6/12 (50%) | 11/16 (69%; 10/15 clean) | 8/12 (67%) / 10/16 (63%; 10/15 clean) |
| Cloud cost per success | $0.245 | $0.217 ($0.205 clean) | $0.498 / $0.556 ($0.521 clean) |
| Median wall time per task | 25 min (1,508 s) | 19 min (1,137 s) | 75 s / 86 s |
| Mean time per local LLM call | 128.7 s | 70–80 s (-40 to -45%) | n/a |
| Replies truncated by token budget | 36 (across v3 and v4) | 0 | n/a |
| 3D portal frame rate (1280x800) | 4, 8 and 20 FPS | 55–60 FPS (pilot/confirm), 38–39 FPS (final) | 60 FPS (v3/confirm), 40 FPS (final) |

Key drivers of the improvement:

- **Prefix-stable conversation:** the state of the work is appended to the end of each request and never stored, writes are compacted lazily, and context trimming cuts once down to 70% of budget. Measured on a 23,700-token conversation: 156 s cold, 148 s when editing the task message (4.0.0), **1.1 s** with the prefix unchanged (4.1.0).
- **12,000-token reply budget (`TANDEM_REPLY_TOKENS`):** eliminated the 36 cut-off replies seen in v3/v4.
- **40 FPS web-check gate (`TANDEM_WEB_MIN_FPS`):** caught both slow 3D portals in `confirm` (3 and 4 FPS on first finish) and guided the local model to reach 60 FPS before acceptance.
- **Failure visibility and early stops:** long check outputs keep failing lines (`BAD`, `FAIL`, `ERROR`, tracebacks); repeated identical failures stop as `stuck` at the third finish; slow passing checks (`TANDEM_SLOW_CHECK_S=30`) go back once with the line after the longest silence.

## What the numbers mean

- **Small edits do not pay:** in `v3`, the 5-line fix in `discount.py` cost `+10%` (`$0.0504` against `$0.0457`). The guide tells Opus to do edits under about 30 lines itself.
- **Medium and large work saves 50–78% per success** across all four tasks, and 61% overall (`$0.217` vs `$0.556`, or `$0.205` vs `$0.521` without infrastructure incidents).
- **Sample-size caveat:** the 4.1.0 series combines three progressive rounds (`pilot1`: round 1; `confirm`: rounds 1+2; `final`: round 3) with 4 pairs per task total. Before the final pair Tandem stood at 7/12 against 9/12 direct; with 12–16 attempts per arm a 1- or 2-success difference is not statistically decisive.
- **Remaining Tandem failures in the 4.1.0 series:**
  - **Orbital (`pilot1` p1 and `confirm` p1):** both artifacts pass the independent evaluator, but timed out because of an orchestrator check that raced the running animation or could not be satisfied (the failing-line preservation and early `stuck` stop were added specifically to address this).
  - **Cron (`confirm` p1):** unit tests passed in 141 s on an unsatisfiable expression searched minute by minute; the evaluator timed out at 60 s (`TANDEM_SLOW_CHECK_S=30` was added after this run).
  - **3D portal (`confirm` p1 and p2):** p1's contract asked for a scrolling grid that pushed the orbit check just past its threshold (0.317 vs 0.30); p2 failed `interactions` on 1 of the 3 repeated evaluations (intermittent evaluator checks also caused failures on Direct Orbital).
- **Time:** a Tandem result takes roughly 7 to 39 minutes median (about 13x slower than direct in wall time), the inherent trade-off of a local 27B model at ~27 tokens/s.

## Quality

The evaluator verdicts above are the functional comparison. Visually, on 1280x800 captures and measured FPS:

- **Boids and Cron:** functionally equivalent (60 FPS on Boids in both arms; on 19 cron edge cases, Tandem matched Direct on 18–19 cases, with the single difference decided by the contract). Direct writes slightly more detailed error messages and UI hints.
- **Orbital:** both arms run at 60 FPS and are clean; Direct adds extra polish not requested in the prompt (glow halos, tapered trails, usage hint line).
- **3D portal:** in `confirm` both Tandem portals were raised from 3–4 FPS to 60 FPS by the FPS gate; in `final`, Tandem's portal runs at 38–39 FPS (vs 40 FPS direct on a heavier scene) and passes all 3 evaluations with dark-blue solid blocks, glowing rings and floating crystals, while Direct renders neon wireframe edges and a full cross-grid but fails `interactions`. Visual defects such as inverted quad winding or half-grids remain invisible to automated functional checks.

The local model does only what the contract says. The guide therefore asks Opus to keep requested labels verbatim, write the contract in the user's language, and state palette, layout and finish for UI work.

### 3D neon portal

<table>
  <tr><th width="50%">Direct (final, pair 1)</th><th width="50%">With Tandem (final, pair 1)</th></tr>
  <tr>
    <td><img src="../benchmarks/opus/gifs/portal_direct.gif" width="100%" alt="3D portal written directly by Opus"></td>
    <td><img src="../benchmarks/opus/gifs/portal_tandem.gif" width="100%" alt="3D portal written by the local model through Tandem"></td>
  </tr>
</table>

### Orbital simulation

<table>
  <tr><th width="50%">Direct (pilot, pair 1)</th><th width="50%">With Tandem (confirm, pair 2)</th></tr>
  <tr>
    <td><img src="../benchmarks/opus/gifs/orbital_direct.gif" width="100%" alt="Orbital simulation written directly by Opus"></td>
    <td><img src="../benchmarks/opus/gifs/orbital_tandem.gif" width="100%" alt="Orbital simulation written by the local model through Tandem"></td>
  </tr>
</table>

## Earlier baseline and how the version was reached

The repository keeps all earlier iterations in `benchmarks/opus/runs/`.

- **4.0.0 baseline (`v3`, `20261121-215741_v3`, [`REEVAL_V3.json`](../benchmarks/opus/REEVAL_V3.json)):** 5 tasks x 3 pairs (15 attempts per arm), including the 5-line `discount.py` fix (`$0.0457` direct vs `$0.0504` Tandem, `+10%`). Overall: Direct `$4.12` total, `11/15` ok (`$0.375`/success); Tandem `$1.62` total, `9/15` ok (`$0.180`/success, `-52%` per success, `-61%` total, `-72%` output tokens; ignoring budget both delivered `11/15`). Revealed slow 3D portals (4–20 FPS) and long local loop times.
- **`v4` (`20261122-110735_v4`):** expanded run with read and sorting tasks; exposed prompt-cache invalidation (~50% of local wall time across v3/v4), 36 cut-off replies under the 4,000-token limit, and translated UI labels when an English prompt carried the Italian suffix "Usa Tandem".
- **4.1.0 adversarial rounds (`20261124-030230_adversarial_pilot1`, `20261124-052842_adversarial_confirm`, `20261124-103103_adversarial_final`):**
  - **Round 1 (`pilot1`):** prefix-stable conversation, lazy write compaction, 12,000-token reply budget, temperature bump on repeated calls, 40 FPS web-check gate, verbatim label rule.
  - **Round 2 (`confirm`):** failing lines preserved when trimming long check outputs, early `stuck` stop on repeated identical failures.
  - **Round 3 (`final`):** slow passing check gate (`TANDEM_SLOW_CHECK_S=30`), `stuck` threshold at 3 repeated failures, repeated-failure receipt guidance, and explicit error receipts when the model server fails before saving a conversation.
- **v1 & v2 (`20261121-151815_full`, `20261121-183640_orbital_p1_tandem`, `20261121-191242_orbital_p2p3`, `20261121-211511_v2`):** early autonomous profile iterations that led to the 50 ms `tandem:ui_test` post-action wait, 30 s MCP progress notifications, and the language/finish contract rule.

## Reproduce

    cd benchmarks/opus
    python run_pair.py --tasks py_cron,web_boids,gen_orbital,gen_portal --pairs 3 --tag my_run
    python reeval.py out.json runs/<run_dir>
    node render_gifs.mjs <workspace_dir> <out.gif>

The GIFs play in real time: each frame keeps the time it covered on the page, so a page that renders slowly shows fewer frames, not faster motion.

`run_pair.py` needs the `claude` CLI logged in, LM Studio with the executor model at `http://127.0.0.1:1234/v1`, Node and a Chromium build. A full run takes several hours, mostly spent waiting for the local model.
