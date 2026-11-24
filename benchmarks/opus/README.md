# Opus 5.5 benchmarks

Direct vs Tandem pairs with Opus 5.5 as the orchestrator in Claude Code. Results and method: [docs/BENCHMARKS.md](../../docs/BENCHMARKS.md).

| Run | Tandem code | What it is |
| --- | --- | --- |
| `runs/20261124-103103_adversarial_final` | 4.1.0 (round 3) | **4.1.0 final run**, 4 tasks x 1 pair, report `REEVAL_FINAL.json` (combined in `REEVAL_4_1.json`) |
| `runs/20261124-052842_adversarial_confirm` | 4.1.0 (rounds 1+2) | **4.1.0 confirmation run**, 4 tasks x 2 pairs, report `REEVAL_CONFIRM.json` (combined in `REEVAL_4_1.json`) |
| `runs/20261124-030230_adversarial_pilot1` | 4.1.0 (round 1) | **4.1.0 pilot run**, 4 tasks x 1 pair, report `REEVAL_PILOT1.json` (combined in `REEVAL_4_1.json`) |
| `runs/20261122-110735_v4` | 4.0.1 + read/sorting tasks | expanded run used to profile local loop bottlenecks |
| `runs/20261121-215741_v3` | 4.0.0 | **4.0.0 release baseline**, 5 tasks x 3 pairs, report `REEVAL_V3.json` |
| `runs/20261121-211511_v2` | before the language and finish rule | stopped after 9 attempts |
| `runs/20261121-151815_full`, `runs/20261121-183640_orbital_p1_tandem`, `runs/20261121-191242_orbital_p2p3` | v1, 300 ms wait after each `ui_test` action | first full iteration (Portal not run) |
| `runs/20261121-143711_pilot` | first autonomous profile | one pair of the fix and of Orbital |

Each run keeps `results.json` (cost, tokens, tools used, evaluator verdict), the full `claude -p` transcripts and the produced files. The Tandem code snapshot and job stores are not committed.
