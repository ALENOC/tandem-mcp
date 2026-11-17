# Tandem MCP v3.6.1 Benchmark Campaign (Gemini 4 Hydrogen + Qwen 27B)

This directory contains the full reproduction of the historical Tandem MCP v3.1.0 benchmark suite on **Tandem MCP v3.6.1** (commit `010cbb6`) using **Gemini 4 Hydrogen** as the cloud orchestrator and **`qwen3.8-27b@iq3_s`** (LM Studio) as the local executor.

- **[RESULTS.md](RESULTS.md)** — Full technical report and historical comparison (Fable 5.2 v3.1.0 vs. Gemini 4 Hydrogen v3.6.1)
- **[results.json](results.json)** — Raw measurements for reading, extraction, and delegated bugfixes
- **[generation.json](generation.json)** — Raw measurements for Orbital Animation and 3D Neon Portal
- **[environment.json](environment.json)** — Hardware, runtime, sandbox, and LM Studio environment metadata
- **[run_benchmark.py](run_benchmark.py)** — Reproducible script for the 7 reading/extraction/bugfix workloads
- **[animation_comparison.html](animation_comparison.html)** — Interactive A/B demo: Orbital Animation (`animation_direct/` vs `animation_tandem/`)
- **[scene3d_comparison.html](scene3d_comparison.html)** — Interactive A/B demo: 3D Neon Portal (`portal_direct/` vs `portal_tandem/`)
