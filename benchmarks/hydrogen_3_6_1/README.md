# Hydrogen 3.6.1 Benchmark Suite

Fresh, self-contained benchmark suite pairing **Gemini 4 Hydrogen (Medium)** (`gemini-4-hydrogen-medium` via `agy`) as the Tandem MCP orchestrator with **Qwen3.8 27B** (`qwen3.8-27b@iq3_s` via LM Studio) as the local executor.

## Scenarios

- `direct`: Gemini 4 Hydrogen runs with `tandem-mcp` disabled, using only native tools.
- `tandem`: Gemini 4 Hydrogen runs with `tandem-mcp` enabled, delegating reading, extraction, bugfixes, and bounded module generation to `qwen3.8-27b@iq3_s`.

## Workloads

1. `reading_agent_rollback` — Targeted code QA on `agent.py` (`digest_file`).
2. `reading_package_survey` — Multi-file survey across `tandem_mcp/*.py` (`digest_many`).
3. `reading_git_log` — Git history digestion (`git_log_25_stat.txt`).
4. `extraction_manifest` — Structured JSON extraction from `pyproject.toml` (`extract_from_file`).
5. `bugfix_multifile` — Multi-file bugfix across 4 Python modules verified by an independent unit test suite (`delegate` + `job_evidence` + `job_feedback`).
6. `feature_rate_limiter` — Bounded implementation of `rate_limiter.py` + `test_rate_limiter.py` from `SPEC.md`, verified by an external hidden test suite (`eval_rate_limiter.py`).

## Running

```sh
python3 benchmarks/hydrogen_3_6_1/suite.py --repeats 2
```

Run a subset:

```sh
python3 benchmarks/hydrogen_3_6_1/suite.py --tasks extraction_manifest,bugfix_multifile --repeats 1
```
