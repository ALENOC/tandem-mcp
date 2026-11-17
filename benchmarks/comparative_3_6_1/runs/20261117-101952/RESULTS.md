# Comparative Benchmark Results — Tandem MCP v3.6.1

- **Run ID**: `20261117-101952`
- **Date**: 2026-11-17 12:07:24
- **Tandem Commit**: `010cbb6` (clean=`True`, version=`3.6.1`)
- **Orchestrator**: requested=`gemini-4-hydrogen-medium`, verified_runs=`2/3`
- **Local executor**: `qwen3.8-27b@iq3_s` via LM Studio (`http://127.0.0.1:1234/v1`)
- **Cloud token collection**: `agy_cli_json_usage` (thinking included in `output_tokens`, not double-counted; cached tokens separate)

## Aggregated Comparison

| Task | Scenario | n | Completed | E2E Success | Artifact Valid | Timeouts | Cloud Tokens / Attempt (mean) | Usage Coverage | Cloud Tokens / Success | Cloud Savings vs Direct | Median Time (s) | Local Tokens (mean) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gen_portal` | `gemini_direct` | 1 | 1 | 100.0% | 100.0% | 0 | 58280 | 100.0% | 58280.0 | baseline | 93.35 | 0 |
| `gen_portal` | `gemini_lmstudio` | 1 | 1 | 100.0% | 100.0% | 0 | 208731 | 100.0% | 208731.0 | -258.2% | 2152.57 | 17158 |
| `gen_portal` | `gemini_tandem` | 1 | 0 | 0.0% | 0.0% | 1 | N/A | 0.0% | N/A | N/A | 4200.13 | 267995 |
