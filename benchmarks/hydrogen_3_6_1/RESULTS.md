# Tandem MCP v3.6.1 Benchmark — Gemini 4 Hydrogen (Medium) + qwen3.8-27b@iq3_s

- **Run ID**: `20261118-152320`
- **Date (UTC)**: `2026-11-18T14:23:20.901521+00:00`
- **Orchestrator**: `gemini-4-hydrogen-medium` (`agy` 1.5.11)
- **Executor**: `qwen3.8-27b@iq3_s` on LM Studio (`http://127.0.0.1:1234/v1`)
- **Accounting**: Cloud tokens measured directly via `agy --output-format json`; local tokens measured via Tandem `ledger.jsonl`.

## Summary Table

| Task | Scenario | n | E2E Success | Mean Cloud Tokens | Cloud Savings vs Direct | Median Time (s) | Mean Local Tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `gen_orbital` | `direct` | 3 | 100.0% (3/3) | 35,887.3 | baseline | 50.99 | 0.0 |
| `gen_orbital` | `tandem` | 3 | 66.7% (2/3) | 51,800.7 | -44.3% | 892.90 | 108,343.0 |
| `gen_portal` | `direct` | 3 | 100.0% (3/3) | 68,495.0 | baseline | 84.97 | 0.0 |
| `gen_portal` | `tandem` | 3 | 33.3% (1/3) | 52,921.7 | +22.7% | 32.60 | 397,527.0 |

## Per-Attempt Details

| Attempt | Completed | Valid | E2E | Time (s) | Turns | Cloud Input | Cloud Output | Cloud Total | Local Total | Reason |
| --- | :---: | :---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `gen_orbital__tandem__r1` | True | False | False | 21.79 | 1 | 20242 | 1857 | 22099 | unavailable | index.html missing |
| `gen_orbital__direct__r1` | True | True | True | 51.41 | 1 | 26686 | 9539 | 36225 | 0 | check_page.js and browser check passed |
| `gen_portal__direct__r1` | True | True | True | 101.31 | 1 | 46322 | 16337 | 62659 | 0 | check_engine.js and browser check passed |
| `gen_portal__tandem__r1` | True | True | True | 3390.64 | 1 | 86947 | 8227 | 95174 | 397527 | check_engine.js and browser check passed |
| `gen_orbital__direct__r2` | True | True | True | 50.99 | 1 | 26460 | 9353 | 35813 | 0 | check_page.js and browser check passed |
| `gen_orbital__tandem__r2` | True | True | True | 1763.37 | 1 | 86038 | 5010 | 91048 | 152159 | check_page.js and browser check passed |
| `gen_portal__tandem__r2` | True | False | False | 32.35 | 1 | 26422 | 4302 | 30724 | unavailable | Missing files: ['index.html', 'scene.js', 'engine3d.js', 'app.js'] |
| `gen_portal__direct__r2` | True | True | True | 75.14 | 1 | 35767 | 15331 | 51098 | 0 | check_engine.js and browser check passed |
| `gen_orbital__tandem__r3` | True | True | True | 892.90 | 1 | 38192 | 4063 | 42255 | 64527 | check_page.js and browser check passed |
| `gen_orbital__direct__r3` | True | True | True | 46.68 | 1 | 26404 | 9220 | 35624 | 0 | check_page.js and browser check passed |
| `gen_portal__direct__r3` | True | True | True | 84.97 | 1 | 73906 | 17822 | 91728 | 0 | check_engine.js and browser check passed |
| `gen_portal__tandem__r3` | True | False | False | 32.60 | 1 | 29362 | 3505 | 32867 | unavailable | Missing files: ['index.html', 'scene.js', 'engine3d.js', 'app.js'] |
