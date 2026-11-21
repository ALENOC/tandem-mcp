# Benchmarks

This page reports only the latest runs (Tandem 3.8.0, November 2026). Older campaigns stay in the git history.

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

Each task runs the same prompt in two ways:

- **Direct:** the orchestrator writes the demo itself, with Tandem disabled.
- **With Tandem:** the orchestrator writes a contract with a `tandem:ui_test` acceptance test and calls `delegate` once. A local host process (`tandem_mcp/host_runner.py`) waits for the job with no cloud polling, and the local worker repairs against the test at no cloud cost. The cloud is called again only for one review when the job fails, and then for a direct fallback when the local result still does not verify. The fallback is counted in the cost.

The direct runs are the 3.7.0 runs of 20-21 November: the direct path did not change. The Tandem runs are new (21 November).

Runner: [`benchmarks/hydrogen_3_6_1/run_from_prompt_pair.py`](../benchmarks/hydrogen_3_6_1/run_from_prompt_pair.py) · Re-evaluation: [`reeval_release.py`](../benchmarks/hydrogen_3_6_1/reeval_release.py) · Report: [`REEVAL_3_8_0.json`](../benchmarks/hydrogen_3_6_1/REEVAL_3_8_0.json)

### 3D neon portal (4 files, software renderer, 3 runs per arm, budget 70 min)

| | Direct | With Tandem |
| --- | ---: | ---: |
| Successful attempts | 2/3 | 3/3 |
| Cloud tokens per success | 74,372 | 41,149 |
| Cloud change vs direct | | **-44.7%** |
| Output tokens per attempt | 15,800 | 7,440 |
| Median time per attempt | 82 s | 57 min |
| Local tokens per attempt | 0 | 300,579 |
| Direct fallbacks | | 1 |

Evaluator: [`check_portal_behavioral.mjs`](../benchmarks/hydrogen_3_6_1/check_portal_behavioral.mjs). It checks startup errors, canvas motion, the HUD metrics, pause, orbit, speed, the visual palette, and Reset. Reset must restart the animation even after a pause.

- **Tandem, run 1:** the local job ran out of its 60 minutes with the pause test still failing, and the orchestrator wrote the demo directly: 75,045 cloud tokens, more than the direct path. In that run the worker also copied a context placeholder into `app.js` as if it were code; 3.8.0 refuses such a write.
- **Tandem, runs 2 and 3:** written and repaired locally, 26,389 and 22,013 cloud tokens.
- **Direct, run 2:** failed, the base plate is lit almost white.

Every Tandem run passes the evaluator, but the delegated portals are plainer than the direct ones: in run 3 the crystals are black instead of colored.

With 3.7.0 (no acceptance test, no fallback) Tandem passed 1 run of 3, at 75,769 cloud tokens per success (+1.9%).

### Orbital simulation (single `index.html`, 3 runs per arm, budget 40 min)

| | Direct | With Tandem |
| --- | ---: | ---: |
| Successful attempts | 3/3 | 2/3 |
| Cloud tokens per success | 35,488 | 38,800 |
| Cloud change vs direct | | **+9.3%** |
| Output tokens per attempt | 9,508 | 4,507 |
| Median time per attempt | 50 s | 18 min |
| Local tokens per attempt | 0 | 87,846 |

Evaluator: [`check_orbital_behavioral.mjs`](../benchmarks/hydrogen_3_6_1/check_orbital_behavioral.mjs). It checks canvas size, time, pause and resume, the speed slider, the trails toggle, click bursts, reset, the FPS readout, JavaScript errors and the star distribution.

- **Tandem, run 1:** failed. The Trails button changes its label, but turning trails off barely changes the picture. The acceptance test written by the orchestrator checked only the label, so the job verified and no fallback ran.
- Writing the acceptance test raises the planning call from about 20,400 to about 25,900 cloud tokens. On this small page that is more than the test saves: with 3.7.0 Tandem passed 3 of 3 at 20,410 cloud tokens per success (-42.5%).

### Both tasks together

Cloud tokens per success summed over the two tasks: direct 109,860, Tandem 79,949 (**-27.2%**). With 3.7.0 the sum was 96,179 (-12.5%).

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

## Evaluator corrections

The Orbital evaluator rejected correct pages in four ways. Every stored verdict, direct and Tandem, was re-computed with the fixed evaluator:

- a speed label such as `Time Speed 1.0x` was read as the simulation time;
- a HUD that puts the number before its label (`60 FPS`, `1.2 Sec`) was not parsed;
- the trails check ran for 1.1 s, which under CPU load sat right at its threshold. It now runs for 2 s;
- the speed check compared two 0.6 s windows, so a HUD that shows whole seconds read 0 s at 1x. It now uses 2.5 s windows and asks for at least twice the time at 3x. A page whose slider has no effect reads 2 s against 3 s and still fails.

The Portal Orbit check measured camera motion only in the floor band. When the camera sits low, the floor is seen edge-on and that band does not change even while the camera orbits. The check now also compares whole frames: with Orbit off, the frame difference must fall to at most half. A correct page measured 0.40 and a page whose Orbit button does not stop the camera measured 0.96.

Negative controls still fail after the fixes. Pages with a frozen time, frozen FPS, frozen particle counter or a speed slider without effect are rejected on exactly that check. The fixes changed no verdict of the 3.7.0 runs.

## Reproduce

    cd benchmarks/hydrogen_3_6_1
    python run_from_prompt_pair.py --task gen_orbital --tag my_run
    python run_from_prompt_pair.py --task gen_portal --tag my_run
    python run_from_prompt_pair.py --task gen_portal --skip-direct --no-fallback --tag local_only
    python reeval_release.py out.json runs/<run_dir> [runs/<run_dir> ...]
    node render_gifs.mjs <workspace_dir> <out.gif>
