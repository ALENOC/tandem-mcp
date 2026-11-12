# Tandem MCP — Live Benchmark Results

Measured live with [`benchmarks/run_benchmark.py`](run_benchmark.py) (cache disabled, isolated temporary `TANDEM_HOME`, sequential execution).

## Environment

- **Date**: 2026-11-13
- **Platform**: Linux x86_64 / Python 3.13.17
- **Local server**: LM Studio (`http://127.0.0.1:1234/v1`)
- **Local model**: `qwen3.8-27b@iq3_s` (context `65536`, probed speed `11.1` tokens/s, native tool calls + reasoning stripped)
- **Sandbox**: `bubblewrap` (machine read-only, workspace writable, credentials hidden, env secrets stripped, no network)
- **Token estimate convention**: `1 orchestrator token ≈ 3.6 chars` (`store.CHARS_PER_TOKEN`), comparing raw material bytes vs. the compact output/receipt returned to the cloud orchestrator.

---

## 1. Reading & Evidence Benchmarks (`digest_file`, `digest_many`)

| Scenario | Tool | Source read | Returned to cloud | Cloud tokens (without → with) | Est. cloud tokens saved | Local tokens | Wall time | Evidence check |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Full-file doc QA (`README.md`) | `digest_file` | 20,822 B (226/226 lines) | 403 B | 5,784 → 112 | **5,672 (98.1%)** | 6,732 | 23.97 s | `0` ok / `3` dropped (`unsupported`)* |
| Targeted grep QA (`agent.py`) | `digest_file (grep)` | 52,912 B (7/1,065 lines) | 682 B | 14,698 → 189 | **14,508 (98.7%)** | 532 | 16.05 s | `2` ok / `0` dropped (`contested`) |
| Multi-file survey (`tandem_mcp/*.py`) | `digest_many` (8 files) | 149,656 B (8 files) | 1,616 B | 41,571 → 449 | **41,122 (98.9%)** | 58,535 | 473.84 s | `13` ok / `0` dropped |

*\*Note on `README.md`: the local model paraphrased its quotes instead of copying them verbatim, so Tandem's lexical evidence verifier dropped all 3 quotes and flagged `claim_supported = unsupported`. This is an intentional safety feature rather than a silent pass.*

---

## 2. Delegated Coding Benchmarks (`delegate`)

Baseline assumes the cloud orchestrator reads the workspace files plus a ~600 B failing test output.

| Scenario | Workspace size (+test out) | Receipt returned | Cloud tokens (without → with) | Est. cloud tokens saved | Local tokens | Wall time | Outcome |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Micro bugfix (1 tiny file, 6 lines) | 1,047 B | 422 B | 291 → 117 | **174 (59.7%)** | 4,058 | 19.07 s | `VERIFIED` (3 steps, 0 repairs) |
| Multi-file bugfix (`config_loader.py` + 3 files) | 6,094 B | 469 B | 1,693 → 130 | **1,562 (92.3%)** | 7,414 | 34.18 s | `VERIFIED` (4 steps, 0 repairs) |

---

## 3. Honest Takeaways: When Tandem Pays Off (and When It Doesn't)

1. **Highest ROI (`digest_file` with `grep`, `digest_many`)**:
   - Targeted `grep` on a 53 KB source file saved **~14,508 cloud input tokens (98.7%)** in **16 s**.
   - Surveying 8 Python modules (150 KB) saved **~41,122 cloud input tokens (98.9%)**, at the cost of **~7m 54s** on a single 11 tok/s local GPU.
2. **Low ROI (`delegate` on trivial 1-file edits)**:
   - Fixing a 6-line file took **19.1 s** and saved only **~174 cloud tokens**. Delegating is only worthwhile when there are multiple files to inspect, larger context, or iterative test-fix-repair cycles.
3. **Single-GPU concurrency limit**:
   - Sending multiple heavy `digest_*` calls in parallel queues requests on a single local GPU and can hit the 3-minute MCP client timeout. Sequential calls or `grep` pre-filtering avoid this.
4. **Verification catches local-model hallucinations**:
   - In the `README.md` run, the local model's non-verbatim quotes were caught and flagged (`0/3` verified) instead of being trusted blindly.
