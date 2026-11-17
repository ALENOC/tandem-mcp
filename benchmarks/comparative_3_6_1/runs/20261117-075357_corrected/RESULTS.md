# Comparative Benchmark Results — Tandem MCP v3.6.1

- **Run ID**: `20261117-075357_corrected`
- **Date**: 2026-11-17 10:19:39
- **Tandem Commit**: `010cbb6` (clean=`True`, version=`3.6.1`)
- **Orchestrator**: requested=`gemini-4-hydrogen-medium`, verified_runs=`53/54`
- **Local executor**: `qwen3.8-27b@iq3_s` via LM Studio (`http://127.0.0.1:1234/v1`)
- **Cloud token collection**: `agy_cli_json_usage` (thinking included in `output_tokens`, not double-counted; cached tokens separate)

## Aggregated Comparison

| Task | Scenario | n | Completed | E2E Success | Artifact Valid | Timeouts | Cloud Tokens / Attempt (mean) | Usage Coverage | Cloud Tokens / Success | Cloud Savings vs Direct | Median Time (s) | Local Tokens (mean) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `reading_grep_agent` | `gemini_direct` | 3 | 3 | 100.0% | 100.0% | 0 | 19627.3 | 100.0% | 19627.3 | baseline | 15.58 | 0 |
| `reading_grep_agent` | `gemini_lmstudio` | 3 | 3 | 100.0% | 100.0% | 0 | 24371 | 100.0% | 24371.0 | -24.2% | 145.09 | 18124.3 |
| `reading_grep_agent` | `gemini_tandem` | 3 | 3 | 100.0% | 100.0% | 0 | 25704.7 | 100.0% | 25704.7 | -31.0% | 69.77 | 1262.7 |
| `extraction_manifest` | `gemini_direct` | 3 | 3 | 100.0% | 100.0% | 0 | 14463.3 | 100.0% | 14463.3 | baseline | 8.11 | 0 |
| `extraction_manifest` | `gemini_lmstudio` | 3 | 3 | 100.0% | 100.0% | 0 | 20375.7 | 100.0% | 20375.7 | -40.9% | 32.94 | 2014.3 |
| `extraction_manifest` | `gemini_tandem` | 3 | 3 | 100.0% | 100.0% | 0 | 17853.7 | 100.0% | 17853.7 | -23.4% | 38.54 | 1065 |
| `reading_readme` | `gemini_direct` | 3 | 3 | 100.0% | 100.0% | 0 | 15652.7 | 100.0% | 15652.7 | baseline | 11.06 | 0 |
| `reading_readme` | `gemini_lmstudio` | 3 | 3 | 100.0% | 100.0% | 0 | 20731 | 100.0% | 20731.0 | -32.4% | 83.46 | 6496.7 |
| `reading_readme` | `gemini_tandem` | 3 | 3 | 100.0% | 100.0% | 0 | 22336.3 | 100.0% | 22336.3 | -42.7% | 85.25 | 4469.3 |
| `bugfix_micro` | `gemini_direct` | 3 | 3 | 100.0% | 100.0% | 0 | 19155.3 | 100.0% | 19155.3 | baseline | 16.22 | 0 |
| `bugfix_micro` | `gemini_lmstudio` | 3 | 3 | 100.0% | 100.0% | 0 | 28489.3 | 100.0% | 28489.3 | -48.7% | 54.99 | 5202 |
| `bugfix_micro` | `gemini_tandem` | 3 | 3 | 100.0% | 100.0% | 0 | 21540.7 | 100.0% | 21540.7 | -12.5% | 60.46 | 6391 |
| `bugfix_multifile` | `gemini_direct` | 3 | 3 | 100.0% | 100.0% | 0 | 23470.7 | 100.0% | 23470.7 | baseline | 17.4 | 0 |
| `bugfix_multifile` | `gemini_lmstudio` | 3 | 3 | 100.0% | 100.0% | 0 | 22166.3 | 100.0% | 22166.3 | +5.6% | 90.9 | 12599 |
| `bugfix_multifile` | `gemini_tandem` | 3 | 3 | 100.0% | 100.0% | 0 | 21055.3 | 100.0% | 21055.3 | +10.3% | 85.1 | 9010.7 |
| `reading_package_survey` | `gemini_direct` | 1 | 1 | 100.0% | 100.0% | 0 | 27564 | 100.0% | 27564.0 | baseline | 26.75 | 0 |
| `reading_package_survey` | `gemini_tandem` | 1 | 1 | 100.0% | 100.0% | 0 | 40437 | 100.0% | 40437.0 | -46.7% | 220.57 | 1113 |
| `reading_package_survey` | `gemini_lmstudio` | 1 | 1 | 100.0% | 100.0% | 0 | 29014 | 100.0% | 29014.0 | -5.3% | 474.46 | 45520 |
| `reading_git_history` | `gemini_direct` | 1 | 1 | 100.0% | 100.0% | 0 | 22127 | 100.0% | 22127.0 | baseline | 17.9 | 0 |
| `reading_git_history` | `gemini_lmstudio` | 1 | 1 | 100.0% | 100.0% | 0 | 18374 | 100.0% | 18374.0 | +17.0% | 181.77 | 18591 |
| `reading_git_history` | `gemini_tandem` | 1 | 1 | 100.0% | 100.0% | 0 | 43707 | 100.0% | 43707.0 | -97.5% | 318.98 | 17202 |
| `gen_orbital` | `gemini_direct` | 1 | 1 | 100.0% | 100.0% | 0 | 35975 | 100.0% | 35975.0 | baseline | 56.75 | 0 |
| `gen_orbital` | `gemini_lmstudio` | 1 | 1 | 100.0% | 100.0% | 0 | 40847 | 100.0% | 40847.0 | -13.5% | 816.11 | 37149 |
| `gen_orbital` | `gemini_tandem` | 1 | 0 | 0.0% | 100.0% | 1 | N/A | 0.0% | N/A | N/A | 2400.12 | 125923 |
