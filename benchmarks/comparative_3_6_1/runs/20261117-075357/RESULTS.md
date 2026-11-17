# Comparative Benchmark Results — Tandem MCP v3.6.1

- **Run ID**: `20261117-075357`
- **Date**: 2026-11-17 10:02:27
- **Git commit**: `010cbb6` (expected `010cbb6`)
- **Orchestrator**: `gemini-4-hydrogen-medium` (identity verified: `True`)
- **Local executor**: `qwen3.8-27b@iq3_s` via LM Studio (`http://127.0.0.1:1234/v1`)
- **Cloud token collection**: `agy_cli_json_usage`

## Aggregated Comparison

| Task | Scenario | n | Success | Median Time (s) | Cloud Tokens (mean) | Cloud Savings vs Direct | Local Tokens (mean) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `reading_grep_agent` | `gemini_direct` | 3 | 100.0% | 15.58 | 19627.3 | baseline | 0 |
| `reading_grep_agent` | `gemini_lmstudio` | 3 | 100.0% | 145.09 | 24371 | -24.2% | 18124.3 |
| `reading_grep_agent` | `gemini_tandem` | 3 | 100.0% | 69.77 | 25704.7 | -31.0% | 1262.7 |
| `extraction_manifest` | `gemini_direct` | 3 | 100.0% | 8.11 | 14463.3 | baseline | 0 |
| `extraction_manifest` | `gemini_lmstudio` | 3 | 33.3% | 32.94 | 20532 | -42.0% | 2019 |
| `extraction_manifest` | `gemini_tandem` | 3 | 100.0% | 38.54 | 17853.7 | -23.4% | 1065 |
| `reading_readme` | `gemini_direct` | 3 | 33.3% | 11.06 | 15920 | baseline | 0 |
| `reading_readme` | `gemini_lmstudio` | 3 | 0.0% | 83.46 | N/A | N/A | N/A |
| `reading_readme` | `gemini_tandem` | 3 | 33.3% | 85.25 | 20787 | -30.6% | 5313 |
| `bugfix_micro` | `gemini_direct` | 3 | 100.0% | 16.22 | 19155.3 | baseline | 0 |
| `bugfix_micro` | `gemini_lmstudio` | 3 | 100.0% | 54.99 | 28489.3 | -48.7% | 5202 |
| `bugfix_micro` | `gemini_tandem` | 3 | 100.0% | 60.46 | 21540.7 | -12.5% | 6391 |
| `bugfix_multifile` | `gemini_direct` | 3 | 100.0% | 17.4 | 23470.7 | baseline | 0 |
| `bugfix_multifile` | `gemini_lmstudio` | 3 | 100.0% | 90.9 | 22166.3 | +5.6% | 12599 |
| `bugfix_multifile` | `gemini_tandem` | 3 | 100.0% | 85.1 | 21055.3 | +10.3% | 9010.7 |
| `reading_package_survey` | `gemini_direct` | 1 | 100.0% | 26.75 | 27564 | baseline | 0 |
| `reading_package_survey` | `gemini_tandem` | 1 | 100.0% | 220.57 | 40437 | -46.7% | 1113 |
| `reading_package_survey` | `gemini_lmstudio` | 1 | 100.0% | 474.46 | 29014 | -5.3% | 45520 |
| `reading_git_history` | `gemini_direct` | 1 | 100.0% | 17.9 | 22127 | baseline | 0 |
| `reading_git_history` | `gemini_lmstudio` | 1 | 100.0% | 181.77 | 18374 | +17.0% | 18591 |
| `reading_git_history` | `gemini_tandem` | 1 | 100.0% | 318.98 | 43707 | -97.5% | 17202 |
| `gen_orbital` | `gemini_direct` | 1 | 100.0% | 56.75 | 35975 | baseline | 0 |
| `gen_orbital` | `gemini_lmstudio` | 1 | 100.0% | 816.11 | 40847 | -13.5% | 37149 |
| `gen_orbital` | `gemini_tandem` | 1 | 100.0% | 2400.12 | N/A | N/A | 125923 |
