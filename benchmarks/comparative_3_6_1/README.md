# Comparative Benchmark Suite - Tandem MCP v3.6.1

Three-way evaluation with configurable cloud orchestrator and local executor.
Frozen fixtures target Tandem MCP v3.6.1 (`010cbb6`). Historical reports retain
the model identities recorded when they were run.

## Scenarios

1. **`direct`**: the configured orchestrator solves the task with native tools.
2. **`lmstudio`**: it delegates through the minimal local harness.
3. **`tandem`**: it delegates through Tandem MCP contracts and tools.

## Methodology & Metrics

- **Context Reduction (`derived` / `estimated`)**: Measures source bytes avoided in cloud context. Kept strictly separate from actual cloud token savings.
- **Actual Cloud Token Savings (`measured` / `unavailable`)**: Measured directly from `agy --output-format json` (`input_tokens`, `output_tokens`, `thinking_tokens`, `cache_read_tokens`, `total_tokens`, `num_turns`). Negative savings are never clamped to zero.
- **Local Compute Cost (`measured`)**: Local prompt/completion tokens, inference time, throughput (tok/s), requests, retries, and repairs from LM Studio / Tandem ledger.
- **Frozen Fixtures**: All 24 input files are frozen from tag `v3.6.1` (`010cbb6`) and verified by SHA-256 (`fixtures/manifest.json`) before every run.
- **Independent Quality Evaluation**: `evaluate.py` scores every scenario independently (never trusting `VERIFIED` alone), including headless Chromium checks for generated web apps.

## Usage

```sh
# Dry run (verifies commit 010cbb6 and all 24 SHA-256 fixture hashes)
python3 benchmarks/comparative_3_6_1/run_comparison.py --dry-run

# Run specific tasks or categories
python3 benchmarks/comparative_3_6_1/run_comparison.py --task reading_grep_agent,extraction_manifest --repeats 3
python3 benchmarks/comparative_3_6_1/run_comparison.py --category bugfix --repeats 3

# Resume an interrupted run
python3 benchmarks/comparative_3_6_1/run_comparison.py --resume <run_id>
```

Each attempt has a finite wall-time budget: reading 1200s, extraction 180s,
bugfix 300s, generation 2400s. `--timeout N` overrides the budget for every
scenario equally; `0` selects category defaults and negative values are rejected.
The full default suite contains 69 attempts (three repeats except generation).
Use `--repeats 1` for a first pass through all 27 task/scenario combinations.
These limits bound individual attempts; a full suite can still take hours.

The runner checks the local endpoint and required model before changing MCP
settings or starting live attempts. An unavailable server fails immediately with
`runs/<run_id>/preflight.json`. Dry runs verify fixtures and prepare prompts
without contacting models, and are never reported as performance measurements.

LM Studio requests and shell tools share the task's remaining budget. The
harness saves usage after each response and records timeouts, step exhaustion,
and failures explicitly. A cloud response saying it is still waiting cannot
count as a completed local execution. Tandem prompts poll the same job in 30s
intervals within the budget, without resubmitting a job after a tool timeout.

Timeouts and Ctrl-C terminate the launched process group, including subprocesses.
Interrupted attempts are saved before the suite stops. Each live attempt retains
stdout/stderr under `runs/<run_id>/logs/`, including partial output on timeout;
generated web artifacts are copied under `artifacts/`. The configuration is
saved with the run, and the original MCP enablement is restored on exit.

## Configurable orchestrators

The runner accepts `--orchestrator-cli`, `--orchestrator-model`, and
`--executor-model`. Supported CLI adapters are `agy` and `codex`; model IDs
are passed through without a fixed model allowlist. Scenarios are `direct`,
`lmstudio`, and `tandem`; historical prefixed scenario names remain accepted.
The corresponding defaults live in `orchestrator.cli`, `orchestrator.model_id`,
and `executor.model_id` in the selected JSON configuration.

The event-stream adapter isolates MCP settings per process, enables only Tandem
for the Tandem scenario, and pins its executor and ledger directory. It collects
reported input, output, and cached tokens. Independent model identity and tool
payload sizes are unavailable when the CLI does not attest them. Missing usage
is never reported as zero. Resume rejects a different configuration.
