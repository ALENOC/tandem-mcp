# Benchmarks

Tandem 4.0.0, November 2026. Cloud orchestrator: **Opus 5.5** in Claude Code. Local executor: `qwen3.8-27b@iq3_s` on LM Studio. Earlier campaigns with other orchestrators were removed from the repository and stay in the git history.

## Method

Each task is run as a counterbalanced pair, three pairs per task, in fresh workspaces:

- **Direct:** Opus does the work itself. No MCP server is loaded.
- **With Tandem:** the same request with the fixed suffix "Usa Tandem.", and the Tandem MCP server in the autonomous profile (`TANDEM_PROFILE=autonomous`, fresh `TANDEM_HOME` per attempt). Opus writes a contract and calls `delegate` once. The call blocks while the local model writes, runs the checks and repairs, with no cloud call. Opus gets back a one-line `ACCEPTED`, or only what still fails.

Both arms run `claude -p` with the same isolated setup: `--setting-sources ""` (no user settings, plugins or `CLAUDE.md`), `--disable-slash-commands`, `--strict-mcp-config`, permissions bypassed. The arm that runs first alternates from pair to pair. The Tandem code of each run is copied before the first attempt and its SHA-256 is recorded.

**Cloud cost** is `total_cost_usd` from the `result` event of `claude -p --output-format json` (list prices, every model used in the attempt). Input, cache writes, cache reads and output tokens are recorded too. **Main metric:** cloud cost per successful result, with failed attempts counted in the cost:

    cost per success = cost of all attempts / successful attempts

An attempt **succeeds** when an independent evaluator, which neither arm sees, passes it three times in a row and the attempt ended inside its time budget. The local model also costs time and power; those are reported next to the cloud figures.

Runner: [`run_pair.py`](../benchmarks/opus/run_pair.py) · Tasks and evaluators: [`tasks.py`](../benchmarks/opus/tasks.py) · Re-evaluation: [`reeval.py`](../benchmarks/opus/reeval.py) · Report: [`REEVAL_V3.json`](../benchmarks/opus/REEVAL_V3.json) · Run: [`runs/20261121-215741_v3`](../benchmarks/opus/runs/20261121-215741_v3)

## Results

| Task | Budget | Direct: cost per success | Tandem: cost per success | Change |
| --- | ---: | --- | --- | ---: |
| Fix a bug in `discount.py` (5 lines) | 15 min | $0.0457 · 3/3 · 12 s | $0.0504 · 3/3 · 1.9 min | **+10%** |
| Cron parser module with tests | 40 min | $0.2434 · 3/3 · 66 s | $0.1769 · 2/3 · 25 min | **-27%** |
| Boids web simulation | 40 min | $0.2418 · 3/3 · 65 s | $0.1573 · 2/3 · 10 min | **-35%** |
| Orbital web simulation | 40 min | $0.4588 · 2/3 · 79 s | $0.1990 · 2/3 · 26 min | **-57%** |
| 3D neon portal (4 files) | 70 min | no success · 0/3 · 3 min | no success · 0/3 · 52 min | |
| **All 15 attempts per arm** | | **$4.12 total · 11/15 · $0.375 per success** | **$1.62 total · 9/15 · $0.180 per success** | **-61% total, -52% per success** |

Each cell gives the cost per success, the successes and the median time per attempt.

| Cloud tokens, all 15 attempts | Direct | With Tandem |
| --- | ---: | ---: |
| Output | 122,534 | 34,074 (-72%) |
| Cache writes | 172,279 | 101,347 |
| Cache reads | 1,453,182 | 646,441 |

Output tokens are the most expensive part of the cost, and Tandem moves almost all of them to the local model.

## What the numbers mean

- **Small edits do not pay.** On the 5-line fix the contract costs Opus about as much as the edit, plus one turn to load the tool schema. The guide tells Opus to do edits under about 30 lines itself; in these runs the request said "Usa Tandem", so it delegated anyway.
- **Medium and large work saves 27-57% per success**, and 75% per attempt on the portal ($0.135 against $0.537).
- **Correctness is the same, punctuality is not.** Ignoring the time budget, both arms deliver 11 correct results of 15: Tandem at $0.147 each, direct at $0.375 (-61%). Inside the budget Tandem has 9 against 11. Two Tandem results were correct but late, both after one `job_continue`:
  - Cron pair 2 at 42 minutes, against a 40-minute budget.
  - Orbital pair 1 at 55 minutes.
- **Tandem failures:**
  - **Boids, pair 2:** the page redraws a translucent trail layer while paused, so its pixels keep changing and the "starts paused" check fails.
  - **3D portal:** none of the three pages passes all three evaluations. The portal evaluator is strict, and the direct path misses it too: one direct page is too bright, and two keep the scene paused after Reset, which this evaluator rejects.
- **Time:** a Tandem result takes from 2 minutes to 2 hours where the direct path takes 12 seconds to 3 minutes.

## Quality

The evaluator verdicts above are the functional comparison. On the look:

- **Boids and Cron:** equivalent. The Tandem cron modules come with more tests (37-39 against 22-26).
- **Orbital:** both are clean. The Tandem orbit trails are fainter.
- **3D portal:** the Tandem page has the neon palette and colored crystals the contract asked for. Its software renderer runs at about 16 FPS where the direct one runs at 60.

The local model does only what the contract says. The guide therefore asks Opus to write the contract in the user's language and to state palette, layout and finish for UI work. Before that rule, a request in Italian produced an English interface.

### 3D neon portal

<table>
  <tr><th width="50%">Direct (pair 3)</th><th width="50%">With Tandem (pair 1)</th></tr>
  <tr>
    <td><img src="../benchmarks/opus/gifs/portal_direct.gif" width="100%" alt="3D portal written directly by Opus"></td>
    <td><img src="../benchmarks/opus/gifs/portal_tandem.gif" width="100%" alt="3D portal written by the local model through Tandem"></td>
  </tr>
</table>

### Orbital simulation

<table>
  <tr><th width="50%">Direct (pair 2)</th><th width="50%">With Tandem (pair 2)</th></tr>
  <tr>
    <td><img src="../benchmarks/opus/gifs/orbital_direct.gif" width="100%" alt="Orbital simulation written directly by Opus"></td>
    <td><img src="../benchmarks/opus/gifs/orbital_tandem.gif" width="100%" alt="Orbital simulation written by the local model through Tandem"></td>
  </tr>
</table>

## How the version was reached

The repository keeps the earlier iterations in `benchmarks/opus/runs/`; only the v3 run counts for the table above.

- **v1** (`20261121-151815_full` and the two Orbital runs after it):
  - Cron saved 47% and Boids 48% per success, both 3/3.
  - Orbital failed 3 of 3. Every job spent its local budget on a last `tandem:ui_test` step ("time near zero right after Reset") that could not pass, because the runner waited 300 ms after each click while the animation kept running.
  - The runner now waits 50 ms. Re-run on the stored page of pair 3, that test passes all 40 steps.
  - In pair 1, Opus then edited the page with `sed` without checking it and removed the click handler. The guide now forbids blind edits after a failure.
- **v2** (`20261121-211511_v2`): stopped after 9 attempts to add the language and finish rule.
- **Harness fixes:**
  - The first Orbital attempt was killed by the runner's own outer timeout after a `job_continue`, so its cost was lost. It is marked `superseded` in `results.json`, and the outer timeout is now wide enough for Opus to finish and report its cost.
  - Claude Code aborts an MCP tool that stays silent for 30 minutes. Tandem now sends a progress notification every 30 seconds; a 2,000-second probe call completed.
- **Evaluator fixes,** each checked against a negative control that must still fail:
  - The Orbital evaluator now reads a `1.0×` speed readout and a `Sim s` time label.
  - The speed check uses 2.5 s windows, so a HUD that shows whole seconds is measured correctly.

## Reproduce

    cd benchmarks/opus
    python run_pair.py --tasks py_discount,py_cron,web_boids,gen_orbital,gen_portal --pairs 3 --tag my_run
    python reeval.py out.json runs/<run_dir>
    node render_gifs.mjs <workspace_dir> <out.gif>

`run_pair.py` needs the `claude` CLI logged in, LM Studio with the executor model at `http://127.0.0.1:1234/v1`, Node and a Chromium build. A full run takes about nine hours, mostly spent waiting for the local model.
