# Opus 5.5 benchmarks

Direct vs Tandem pairs with Opus 5.5 as the orchestrator in Claude Code. Results and method: [docs/BENCHMARKS.md](../../docs/BENCHMARKS.md).

## Running a fresh 4.2.0 campaign

```sh
cd benchmarks/opus
# Standard 4.2.0 run (live 1280x800 screenshot attached on web receipts; local VLM auto-used if loaded):
../../.venv/bin/python run_pair.py --tasks py_discount,py_cron,web_boids,gen_orbital,gen_portal --pairs 3 --tag v4_2

# With an explicit dedicated local VLM for stateless visual review:
../../.venv/bin/python run_pair.py --tasks py_cron,web_boids,gen_orbital,gen_portal --pairs 3 --tag v4_2_vlm --vision-model <vlm-id>

# Re-evaluate every artifact 3x with the immutable evaluators:
../../.venv/bin/python reeval.py REEVAL_4_2.json runs/<run_dir>

# Render real-time comparison GIFs from the chosen workspaces:
node render_gifs.mjs \
  runs/<run_dir>/workspaces/gen_portal__p1__direct gifs/portal_direct.gif \
  runs/<run_dir>/workspaces/gen_portal__p1__tandem gifs/portal_tandem.gif \
  runs/<run_dir>/workspaces/gen_orbital__p1__direct gifs/orbital_direct.gif \
  runs/<run_dir>/workspaces/gen_orbital__p1__tandem gifs/orbital_tandem.gif

# Build the GitHub Pages site from the new report:
../../.venv/bin/python ../../scripts/build_site.py ../../_site --report REEVAL_4_2.json
```

`run_pair.py` flags for Tandem 4.2.0+:
- `--vision-model <id>` (`BENCH_VISION_MODEL`): sets `TANDEM_MODEL_VISION` inside the Tandem MCP server.
- `--visual-review auto|on|off` (`BENCH_VISUAL_REVIEW`, default `auto`): sets `TANDEM_VISUAL_REVIEW`.
- `--receipt-screenshot 1|0` (`BENCH_RECEIPT_SCREENSHOT`, default `1`): sets `TANDEM_RECEIPT_SCREENSHOT` and preserves captured `screenshot.jpg` files in `runs/<run_dir>/screenshots/`.

## Recorded runs

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

Each run keeps `results.json` (cost, tokens, tools used, local job metrics, evaluator verdict), the full `claude -p` transcripts, captured screenshots, and the produced files. The Tandem code snapshot and job stores are not committed.
