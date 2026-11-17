# Tandem MCP v3.6.1 Benchmark — Gemini 4 Hydrogen (Medium) + qwen3.8-27b@iq3_s

- **Run ID**: `20261117-204009`
- **Date (UTC)**: `2026-11-17T19:40:09.222901+00:00`
- **Orchestrator**: `gemini-4-hydrogen-medium` (`agy` 1.5.10)
- **Executor**: `qwen3.8-27b@iq3_s` on LM Studio (`http://127.0.0.1:1234/v1`)
- **Accounting**: Cloud tokens measured directly via `agy --output-format json`; local tokens measured via Tandem `ledger.jsonl`.

## Summary Table

| Task | Scenario | n | E2E Success | Mean Cloud Tokens | Cloud Savings vs Direct | Median Time (s) | Mean Local Tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `bugfix_multifile` | `direct` | 1 | 100.0% (1/1) | 24,760.0 | baseline | 25.80 | 0.0 |
| `bugfix_multifile` | `tandem` | 1 | 100.0% (1/1) | 23,048.0 | +6.9% | 144.65 | 20,644.0 |
| `refactor_rename` | `direct` | 1 | 100.0% (1/1) | 25,558.0 | baseline | 26.18 | 0.0 |
| `refactor_rename` | `tandem` | 1 | 100.0% (1/1) | 24,884.0 | +2.6% | 220.02 | 30,885.0 |
| `reading_incident_log` | `direct` | 1 | 100.0% (1/1) | 72,298.0 | baseline | 21.36 | 0.0 |
| `reading_incident_log` | `tandem` | 1 | 100.0% (1/1) | 25,151.0 | +65.2% | 397.79 | 40,083.0 |

## Per-Attempt Details

| Attempt | Completed | Valid | E2E | Time (s) | Turns | Cloud Input | Cloud Output | Cloud Total | Local Total | Reason |
| --- | :---: | :---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `bugfix_multifile__direct__r1` | True | True | True | 25.80 | 1 | 22966 | 1794 | 24760 | 0 | test_suite.py passed |
| `refactor_rename__direct__r1` | True | True | True | 26.18 | 1 | 23766 | 1792 | 25558 | 0 | test_rename.py passed (13 files renamed) |
| `reading_incident_log__direct__r1` | True | True | True | 21.36 | 1 | 69759 | 2539 | 72298 | 0 | Incident reconstructed (service, start, cause, resolution) |
| `bugfix_multifile__tandem__r1` | True | True | True | 144.65 | 1 | 20909 | 2139 | 23048 | 20644 | test_suite.py passed |
| `refactor_rename__tandem__r1` | True | True | True | 220.02 | 1 | 22551 | 2333 | 24884 | 30885 | test_rename.py passed (13 files renamed) |
| `reading_incident_log__tandem__r1` | True | True | True | 397.79 | 1 | 22197 | 2954 | 25151 | 40083 | Incident reconstructed (service, start, cause, resolution) |
