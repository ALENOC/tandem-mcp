# Tandem MCP v3.6.1 Benchmark — Gemini 4 Hydrogen (Medium) + qwen3.8-27b@iq3_s

- **Run ID**: `20261117-190714`
- **Date (UTC)**: `2026-11-17T18:07:14.194866+00:00`
- **Orchestrator**: `gemini-4-hydrogen-medium` (`agy` 1.5.10)
- **Executor**: `qwen3.8-27b@iq3_s` on LM Studio (`http://127.0.0.1:1234/v1`)
- **Accounting**: Cloud tokens measured directly via `agy --output-format json`; local tokens measured via Tandem `ledger.jsonl`.

## Summary Table

| Task | Scenario | n | E2E Success | Mean Cloud Tokens | Cloud Savings vs Direct | Median Time (s) | Mean Local Tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `reading_agent_rollback` | `direct` | 1 | 100.0% (1/1) | 20,073.0 | baseline | 26.76 | 0.0 |
| `reading_agent_rollback` | `tandem` | 1 | 100.0% (1/1) | 21,977.0 | -9.5% | 278.96 | 8,062.0 |
| `reading_package_survey` | `direct` | 1 | 100.0% (1/1) | 27,327.0 | baseline | 20.56 | 0.0 |
| `reading_package_survey` | `tandem` | 1 | 100.0% (1/1) | 54,416.0 | -99.1% | 620.79 | 35,508.0 |
| `reading_git_log` | `direct` | 1 | 100.0% (1/1) | 24,439.0 | baseline | 34.66 | 0.0 |
| `reading_git_log` | `tandem` | 1 | 0.0% (0/1) | 26,478.0 | -8.3% | 401.16 | 9,688.0 |
| `extraction_manifest` | `direct` | 1 | 100.0% (1/1) | 15,490.0 | baseline | 12.20 | 0.0 |
| `extraction_manifest` | `tandem` | 1 | 100.0% (1/1) | 17,893.0 | -15.5% | 176.07 | 1,324.0 |
| `bugfix_multifile` | `direct` | 1 | 100.0% (1/1) | 24,702.0 | baseline | 28.68 | 0.0 |
| `bugfix_multifile` | `tandem` | 1 | 100.0% (1/1) | 44,096.0 | -78.5% | 237.86 | 7,444.0 |
| `feature_rate_limiter` | `direct` | 1 | 100.0% (1/1) | 23,593.0 | baseline | 28.62 | 0.0 |
| `feature_rate_limiter` | `tandem` | 1 | 100.0% (1/1) | 48,147.0 | -104.1% | 576.54 | 33,767.0 |

## Per-Attempt Details

| Attempt | Completed | Valid | E2E | Time (s) | Turns | Cloud Input | Cloud Output | Cloud Total | Local Total | Reason |
| --- | :---: | :---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `reading_agent_rollback__direct__r1` | True | True | True | 26.76 | 1 | 17491 | 2582 | 20073 | 0 | Verified rollback None=unbacked/skip and string=blob-restore |
| `reading_package_survey__direct__r1` | True | True | True | 20.56 | 1 | 25137 | 2190 | 27327 | 0 | Found 6/6 modules |
| `reading_git_log__direct__r1` | True | True | True | 34.66 | 1 | 21957 | 2482 | 24439 | 0 | Matched 3/3 top files (['README.md', 'tests/test_offline.py', 'tandem_mcp/sandbox.py']) |
| `extraction_manifest__direct__r1` | True | True | True | 12.20 | 1 | 14220 | 1270 | 15490 | 0 | Schema and values verified |
| `bugfix_multifile__direct__r1` | True | True | True | 28.68 | 1 | 22980 | 1722 | 24702 | 0 | test_suite.py passed |
| `feature_rate_limiter__direct__r1` | True | True | True | 28.62 | 1 | 19908 | 3685 | 23593 | 0 | Hidden eval + user tests passed |
| `reading_agent_rollback__tandem__r1` | True | True | True | 278.96 | 1 | 20014 | 1963 | 21977 | 8062 | Verified rollback None=unbacked/skip and string=blob-restore |
| `reading_package_survey__tandem__r1` | True | True | True | 620.79 | 1 | 50929 | 3487 | 54416 | 35508 | Found 6/6 modules |
| `reading_git_log__tandem__r1` | True | False | False | 401.16 | 1 | 24092 | 2386 | 26478 | 9688 | Only matched [] of top3 ['README.md', 'tests/test_offline.py', 'tandem_mcp/sandbox.py'] |
| `extraction_manifest__tandem__r1` | True | True | True | 176.07 | 1 | 17089 | 804 | 17893 | 1324 | Schema and values verified |
| `bugfix_multifile__tandem__r1` | True | True | True | 237.86 | 1 | 38927 | 5169 | 44096 | 7444 | test_suite.py passed |
| `feature_rate_limiter__tandem__r1` | True | True | True | 576.54 | 1 | 43341 | 4806 | 48147 | 33767 | Hidden eval + user tests passed |
