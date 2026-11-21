# Benchmarks

This page reports only the latest runs (Tandem 3.7.0, November 2026). Older campaigns stay in the git history.

## Setup

| | |
| --- | --- |
| Cloud orchestrator | Gemini 4 Hydrogen (medium), through the `agy` CLI |
| Local executor | `qwen3.8-27b@iq3_s` on LM Studio |
| Cloud tokens | `usage.total_tokens` reported by `agy --output-format json`, summed over every cloud call of an attempt |
| Local tokens | Tandem `ledger.jsonl` |

**Main metric:** cloud tokens per successful result, with failed attempts counted in the cost:

    cloud tokens per success = cloud tokens of all attempts / successful attempts

An attempt succeeds only if the behavioral evaluator passes it three times in a row and it finished inside its time budget. The local model also costs time, power and hardware: those are reported next to the cloud figures, not folded into them.

## Generation from a prompt

Each pair runs the same prompt twice:

- **Direct:** the orchestrator writes the demo itself, with Tandem disabled.
- **With Tandem:** the orchestrator writes a contract and calls `delegate` once. A local host process (`tandem_mcp/host_runner.py`) waits for the job with no cloud polling. The cloud is not called again unless a review is needed.

Runner: [`benchmarks/hydrogen_3_6_1/run_from_prompt_pair.py`](../benchmarks/hydrogen_3_6_1/run_from_prompt_pair.py) · Re-evaluation: [`reeval_release.py`](../benchmarks/hydrogen_3_6_1/reeval_release.py) · Report: [`REEVAL_RELEASE_3_7_0.json`](../benchmarks/hydrogen_3_6_1/REEVAL_RELEASE_3_7_0.json)

### Orbital simulation (single `index.html`, 3 pairs, budget 40 min)

| | Direct | With Tandem |
| --- | ---: | ---: |
| Successful attempts | 3/3 | 3/3 |
| Cloud tokens per success | 35,488 | 20,410 |
| Cloud change vs direct | | **-42.5%** |
| Median time per attempt | 50 s | 14 min |
| Local tokens per attempt | 0 | 61,428 |

Evaluator: [`check_orbital_behavioral.mjs`](../benchmarks/hydrogen_3_6_1/check_orbital_behavioral.mjs). It checks canvas size, time, pause and resume, the speed slider, the trails toggle, click bursts, reset, the FPS readout, JavaScript errors and the star distribution.

### 3D neon portal (4 files, software renderer, 3 pairs, budget 70 min)

| | Direct | With Tandem |
| --- | ---: | ---: |
| Successful attempts | 2/3 | 1/3 |
| Cloud tokens per success | 74,372 | 75,769 |
| Cloud change vs direct | | **+1.9%** |
| Median time per attempt | 82 s | 40 min |
| Local tokens per attempt | 0 | 218,516 |

Evaluator: [`check_portal_behavioral.mjs`](../benchmarks/hydrogen_3_6_1/check_portal_behavioral.mjs). It checks startup errors, canvas motion, the HUD metrics, pause, orbit, speed, the visual palette, and Reset. Reset must restart the animation even after a pause.

Failed attempts:

- **Direct, run 2:** the base plate is lit almost white, over the limit for overexposed pixels.
- **Tandem, run 1:** the platform is rendered white instead of dark neon faces.
- **Tandem, run 3:** Reset pressed during a pause leaves the scene frozen.

The one delegated run that passed (run 2) clears every check, but its solid floor and particle trails look busier than the direct output.

## Everyday chat requests

In these runs the request is typed into an ordinary `agy` chat. With Tandem, the delegation, the wait and the review all happen inside that chat. Source: [decision report (Italian)](DECISION_REPORT_20261120.md).

| Task | Runs | Direct | With Tandem | Cloud change |
| --- | ---: | --- | --- | ---: |
| Python discount fix | 1 | 26,953 · 1/1 · 24 s | 33,479 · 1/1 · 105 s | +24.2% |
| Boids animation | 3 | 33,532 · 3/3 · 54 s | 33,214 · 3/3 · 9.5 min | -0.95% |
| Cron scheduler module | 3 | 36,890 · 3/3 · 62 s | at least 52,913 · 1/3 · 15 min | at least +43% |
| Pendulum animation | 3 | 36,356 · 3/3 · 62 s | at least 75,591 · 1/3 · 18 min | at least +108% |

Each cell gives cloud tokens per success, then successes, then the median time per attempt. "At least" means some failed attempts did not report cloud usage, so the true cost is higher.

In a chat, the schemas, the wait and the re-reads of the receipt cost about as much cloud context as writing the code directly. Tandem therefore acts directly on the first turn by default (`TANDEM_AUTO_POLICY=first_turn`).

## Executor efficiency: compacted writes

3D Portal, 3 pairs, with `TANDEM_COMPACT_WRITES` off and on:

| | Off | On (default) |
| --- | ---: | ---: |
| Local tokens (3 runs) | 846,805 | 693,349 (-18.1%) |
| Wall time (3 runs) | 8,129 s | 6,377 s (-21.6%) |
| Jobs verified by their own checks | 3/3 | 3/3 |

Both arms failed the strict Reset check of the portal evaluator in most runs. The A/B measures the cost of the executor, not the quality of the result. Source: [`runs/20261119_ab_compaction/summary.json`](../benchmarks/hydrogen_3_6_1/runs/20261119_ab_compaction/summary.json).

## Evaluator corrections in this release

The Orbital evaluator rejected correct pages in three ways. Every stored verdict was re-computed with the fixed evaluator:

- a speed label such as `Time Speed 1.0x` was read as the simulation time;
- a HUD that puts the number before its label (`60 FPS`, `1.2 Sec`) was not parsed;
- the trails check ran for 1.1 s, which under CPU load sat right at its threshold. It now runs for 2 s.

The Portal Orbit check measured camera motion only in the floor band. When the camera sits low, the floor is seen edge-on and that band does not change even while the camera orbits. The check now also compares whole frames: with Orbit off, the frame difference must fall to at most half. A correct page measured 0.40 and a page whose Orbit button does not stop the camera measured 0.96.

Negative controls still fail after the fixes. Pages with a frozen time, frozen FPS or frozen particle counter are rejected on exactly that check.

## Reproduce

    cd benchmarks/hydrogen_3_6_1
    python run_from_prompt_pair.py --task gen_orbital --tag my_run
    python run_from_prompt_pair.py --task gen_portal --tag my_run
    python reeval_release.py out.json runs/<run_dir> [runs/<run_dir> ...]
    node render_gifs.mjs <workspace_dir> <out.gif>
