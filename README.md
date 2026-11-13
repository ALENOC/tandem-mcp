# Tandem MCP

<p align="center">
  <img src="assets/logo.svg" alt="Tandem MCP logo: a tandem bicycle, two riders on one frame" width="360">
</p>

<p align="center">
  <a href="https://github.com/ALENOC/tandem-mcp/actions/workflows/tests.yml"><img src="https://github.com/ALENOC/tandem-mcp/actions/workflows/tests.yml/badge.svg" alt="tests"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+">
</p>

An MCP server that pairs a cloud orchestrator model with a local executor model. The orchestrator keeps the decisions and the final check; the local model reads, edits, and runs things on the machine and reports in a few lines, so large files never enter the cloud context.

Works with any OpenAI-compatible local server: **LM Studio**, **Ollama**, **llama.cpp**, **vLLM**, **Jan**, **KoboldCpp**, **LocalAI**.

> [!NOTE]
> Most "ask a local model" tools only offload text generation. Most of an agent's cost is reading material (logs, sources, reports), and small local models often hallucinate details or make syntax mistakes.
>
> **Why you can trust a small model here:** Tandem never takes the model's word for it. Before returning anything to the cloud orchestrator, the server runs deterministic Python checks (no LLM involved) to verify that every quote actually exists in the source, flag any invented numbers, check syntax on every modified file, and run your acceptance tests.

**Jump to:** [Quick Start](#quick-start) · [How to use it](#how-to-use-it) · [Tools](#tools) · [Benchmarks](#benchmarks) · [Security](#security) · [Tests](#tests)

---

## Quick Start

**1. Clone & install** (Python 3.11+):

```sh
git clone https://github.com/ALENOC/tandem-mcp
cd tandem-mcp
python3 -m venv .venv
.venv/bin/pip install .
```

**2. Register in Claude Code, Codex, and Antigravity** (one command):

```sh
.venv/bin/python scripts/install.py
```

<details>
<summary>Installer options &amp; manual MCP configuration</summary>

`scripts/install.py` options:
- `--clients claude,codex,antigravity`: select specific clients (default: all three).
- `--replace-legacy`: remove any old `lmstudio` MCP entries while installing `tandem-mcp`.
- `--env TANDEM_SANDBOX=require`: pass environment variables to the server (repeatable).
- `--dry-run`: preview changes without modifying files.
- `--uninstall`: remove `tandem-mcp` from the selected clients.

Manual stdio configuration (any MCP client):

```json
{
  "command": "/path/to/tandem-mcp/.venv/bin/python",
  "args": ["/path/to/tandem-mcp/main.py"]
}
```

`python main.py`, `python -m tandem_mcp`, and `.venv/bin/tandem-mcp` all start the same server. (Note: v3.0.0 used `tandem`; use `tandem_mcp` in v3.0.1+.)

</details>

**3. Start a local model server** and load a model. Tandem auto-detects usual ports in order: LM Studio (`1234`), Ollama (`11434`), llama.cpp (`8080`), vLLM (`8000`), Jan (`1337`), KoboldCpp (`5001`), text-generation-webui (`5000`), LocalAI (`8081`).

<details>
<summary>Environment variables &amp; model notes</summary>

| Variable | Meaning | Default |
| --- | --- | --- |
| `TANDEM_BASE_URL` | OpenAI-compatible URL (`LM_STUDIO_BASE_URL` also read) | auto-detected |
| `TANDEM_MODEL` | Model ID to use | loaded chat model |
| `TANDEM_CONTEXT` | Context length fallback when server omits it | `8192` (Ollama: `4096`) |
| `TANDEM_API_KEY` | API key if required by server | `local` |
| `TANDEM_TIMEOUT` | Per-completion timeout (seconds) | `900` |
| `TANDEM_SANDBOX` | `auto`, `require`, or `off` | `auto` |
| `TANDEM_SANDBOX_NET` | `1` allows network inside sandbox | off |
| `TANDEM_HOME` | Ledger, lessons, caps, cache, and jobs folder | `~/.local/share/tandem-mcp` |

**Model notes:**
- **Ollama**: raise `OLLAMA_CONTEXT_LENGTH` for `delegate` tasks; reading tools (`digest_*`) work at any context length by chunking.
- **Small contexts (< 8000 tokens)**: fine for `digest_*`, `extract_from_file`, and `ask`; tight for `delegate`.
- **Reasoning models**: reasoning blocks are stripped; disabling verbose thinking on the server speeds up mechanical tasks.

</details>

---

## How to use it

Once `tandem-mcp` is registered, **restart your client** (Claude Code, Codex, or Antigravity) so it loads the MCP server.

1. **Check the connection:** ask your agent `"Run executor_status"` — it should show your local server, loaded model, context length, and active sandbox.
2. **Talk normally (or prompt explicitly):** you don't need special syntax; the cloud agent sees Tandem's tool descriptions and calls them automatically. Typical prompts:
   - **Read large files / logs without burning cloud tokens:**
     `"Use tandem-mcp to inspect server.log and list every error with line numbers."` (`digest_file`)
   - **Survey a folder:**
     `"Ask tandem-mcp what each Python module in src/ is responsible for."` (`digest_many`)
   - **Delegate a bounded edit with tests:**
     `"Delegate fixing the failing test in tests/test_auth.py to tandem-mcp, then show me job_diff."` (`delegate` -> `job_diff` -> `job_feedback` or `job_rollback`)
   - **Check real savings:**
     `"Show me ledger_report for the last 7 days."` (`ledger_report`)

<details>
<summary>Optional: add a rule to CLAUDE.md / AGENTS.md / GEMINI.md so your agent prefers Tandem automatically</summary>

```markdown
When `tandem-mcp` is available:
- Use `digest_file` (with `grep` when searching) or `digest_many` to inspect large files, logs, and unfamiliar modules instead of reading them directly into cloud context.
- Use `delegate` for bounded, test-verified mechanical edits, then review `job_diff` and close with `job_feedback` or `job_rollback`.
```

</details>

---

## Why Tandem

- **Contracts (`delegate`)**: bounded workspace, `write_globs`, `immutable` files, `allow_run` regexes, and server-run `verify_commands`.
- **Meaningful checks**: baseline runs before work (pre-passing checks are flagged as `weak`); test files/folders are auto-protected (`read-only`) and restored if touched; changed files are syntax-checked.
- **Checked evidence (`digest_*`, `extract_from_file`)**: every quote is verified lexically against the source, `quote_found` is separated from `claim_supported`, ungrounded numbers are listed, and >2000-char line truncation is signaled.
- **Supervised memory**: `job_feedback` stores project lessons; `job_continue` resumes stopped jobs in the same conversation; `ledger_report` tracks savings and quote failure rates.
- **Any model**: `executor_probe` adapts automatically to native tool calling or JSON-reply fallback.

<details>
<summary>Comparison with houtini-lm, local-vibes, and Atomic Agent Fusion (Nov 2026)</summary>

Compared in November 2026 from each project's README (not from running them). `"no"` means the README does not describe the feature.

| Feature | Tandem | houtini-lm | local-vibes | Atomic Agent Fusion |
| --- | --- | --- | --- | --- |
| Local file-editing tool loop | yes | no | yes | yes |
| Server-run checks + repair loop | yes | no | no | `verify.run` (loop unconfirmed) |
| Baseline check (flags pre-passing) | **yes** | no | no | no |
| Read-only test protection + restore | **yes** | no | no | no |
| Per-task journal, diff & rollback (no git) | **yes** | no | diff stat only | opt-in worktrees |
| Quotes & numbers checked against source | **yes** | no | no | no |
| Agreement score (`samples`) | **yes** | no | no | no |
| Orchestrator feedback -> project lessons | **yes** | no | no | episode reflection |
| Resume stopped task with hint | **yes** | no | no | partly |
| Non-tool-calling models supported | yes (JSON) | n/a | no | yes (grammar) |
| Model capability probing | yes (`probe`) | per-family | no | unconfirmed |
| Pipeline-aware command allow list | **yes** | n/a | no | approval ladder |
| OS sandbox (bubblewrap) | yes | n/a | path only | env secret strip |
| Parallel tasks with file claims | yes | no | separate dirs | yes (waves) |
| Token savings & quality accounting | yes | yes | no | per-worker cost |

</details>

---

## Tools

| Tool | Purpose |
| --- | --- |
| `executor_status` | Active server, models, context length, capabilities, and sandbox status |
| `executor_probe` | Measure native tool calls, forced JSON schema, reasoning, and speed |
| `ask` | Text task with optional `json_schema` and `samples` agreement score |
| `digest_file` | Q&A on a file (text, code, log, JSON, PDF) with checked quotes and `grep` filter |
| `digest_command` | Run an orchestrator command and get exit code, verdict, and full log path |
| `digest_many` | Ask the same question across many files (`glob`), one line per file |
| `extract_from_file` | Structured JSON extraction with ungrounded values flagged |
| `delegate` | Bounded coding task with `verify_commands`, `write_globs`, `immutable`, `allow_run` |
| `delegate_many` | Dependency-ordered batch (`after`) with parallel file ownership and rollback |
| `job_status`, `job_diff`, `job_rollback` | Inspect status, unified diff, and undo changes per job or batch |
| `job_continue` | Resume a stopped job with a hint in the same conversation |
| `job_feedback`, `lesson_add`, `lessons` | Record verdicts and manage standing project/global rules |
| `ledger_report` | Calls, tokens, estimated cloud savings, and per-model quality stats |

<details>
<summary>Example delegated task &amp; receipt states</summary>

```python
delegate(
  goal="test_calc.py fails. Fix calc.py so that the test passes.",
  workspace="/path/to/project",
  verify_commands=["python3 test_calc.py"],
  allow_run=["^python3 test_calc\\.py$"]
)
```

```text
job 20261112-224042-d6d2a6: VERIFIED  (6 steps, 0 repairs, 182.0 s, 10728 executor tokens, native tool calls)
executor: Fixed dbm_to_mw to use 10**(dbm/10) instead of 10**(dbm/20).
  changed calc.py  +3 -1
  syntax ok: calc.py
  check PASS  $ python3 test_calc.py  (failed before the job)
Checks passed. Read job_diff if the change is delicate, then job_feedback.
```

**States:** `verified`, `unverified`, `checks_failed`, `blocked`, `stuck`, `out_of_steps`, `out_of_time`, `error`.

</details>

---

## Security

Read this before pointing Tandem at a sensitive repository:

- **Sandboxed execution (`bubblewrap`)**: when available, both executor `run` commands and `verify_commands` run inside `bubblewrap` (`--ro-bind / /`, workspace writable, `.git` and `SKIP_DIRS` read-only, home credential folders hidden, `SECRET_ENV` vars stripped, `--unshare-net` enabled).
- **Explicit exceptions**: pass `checks_network=True` or `unjailed_checks=True` on `delegate` only for checks that need network or host resources. `digest_command` runs the orchestrator's own command with the user's rights.
- **Fail-closed mode**: on systems without `bubblewrap`, `TANDEM_SANDBOX=auto` falls back to command-text checks (`allow_run` + `DENY` list) with a warning in `executor_status`. Set `TANDEM_SANDBOX=require` to fail closed with `SandboxError` instead.
- **Contract enforcement on shell commands**: `stamp()` hashes every workspace file with SHA-256 before and after `run` (no file-count cap, symlinks excluded). Any file modified outside `write_globs` or owned by another parallel task is reverted immediately.
- **Safe rollback**: `journal_bin.json` + `snapshot.json` back up original bytes (up to 2 MB/file, 50 MB total). Pre-existing files larger than the cap are tracked as `None` so `job_rollback` preserves them instead of deleting them; `post_state.json` prevents overwriting later user edits.
- **Hostile text**: file contents and command output are marked as data in prompts, and receipts/diffs should always be reviewed before accepting. See [SECURITY.md](SECURITY.md) to report vulnerabilities.

---

## Benchmarks

Reproducible live suite: [benchmarks/run_benchmark.py](benchmarks/run_benchmark.py) · Full report: [benchmarks/RESULTS.md](benchmarks/RESULTS.md)

Measured live on `qwen3.8-27b@iq3_s` (LM Studio, `65536` ctx, `23.8 tok/s` probed, cache disabled, `1 cloud tok ≈ 3.6 chars`) on **Intel Core i9-9900K @ 3.60GHz (16 threads)**, **22 GiB RAM**, **AMD Radeon Navi 21 (RX 6800/6900 XT, 16 GiB VRAM)**, Linux x86_64:

**Reading, Command Digest & Extraction (`digest_file`, `digest_many`, `digest_command`, `extract_from_file`)**

| Task | Source → Cloud | Cloud Saved (est.) | Local Tokens | Time | Verification |
| --- | --- | ---: | ---: | ---: | --- |
| Full doc QA (`README.md`) | 23.2 KB → 557 B | **~6,281 tok (97.6%)** | 9,132 | 64.2 s | 0/3 quotes (`unsupported`)* |
| Grep QA (`agent.py`, 7/1,506 lines) | 75.9 KB → 654 B | **~20,904 tok (99.1%)** | 878 | 22.9 s | 2/2 quotes (`quote_only`) |
| 8-file survey (`tandem_mcp/*.py`) | 176.2 KB → 1.7 KB | **~48,479 tok (99.0%)** | 80,840 | 620.4 s | 16/16 quotes (`checked`) |
| Command output (`git log -n 30 --stat`) | 13.9 KB → 2.0 KB | **~3,304 tok (85.7%)** | — | 118 s | 10/10 quotes verified |
| JSON extraction (`pyproject.toml`) | 686 B → 241 B | **~124 tok (64.9%)** | — | 15 s | JSON Schema validated |

**Delegated Coding (`delegate`)**

| Task | Baseline → Receipt | Cloud Saved (est.) | Local Tokens | Time | Result |
| --- | --- | ---: | ---: | ---: | --- |
| Micro bugfix (1 file, 6 lines) | 1.0 KB → 422 B | **~174 tok (59.7%)** | 4,061 | 19.1 s | `VERIFIED` (3 steps, 0 repairs) |
| Multi-file bugfix (4 files) | 6.1 KB → 490 B | **~1,557 tok (92.0%)** | 7,365 | 32.1 s | `VERIFIED` (4 steps, 0 repairs) |

**Animation A/B Comparison (Orbital Particle Simulation, identical spec)**

| Without Tandem — `Gemini Hydrogen` (Cloud Direct) | With Tandem MCP — `Gemini Hydrogen` (Orchestrator) + `qwen3.8-27b@iq3_s` (Local) |
| :---: | :---: |
| <img src="benchmarks/animation_without_tandem.gif" alt="Without Tandem — Gemini Hydrogen (Cloud Direct)" width="360" height="230" /> | <img src="benchmarks/animation_with_tandem.gif" alt="With Tandem MCP — Gemini Hydrogen orchestrator + qwen3.8-27b@iq3_s local executor" width="360" height="230" /> |
| *Cloud Direct: `Gemini Hydrogen` · 10.3 KB, 272 lines · **~2,873 cloud output tokens*** | *Orchestrator: `Gemini Hydrogen` · Local executor: `qwen3.8-27b@iq3_s` (`65536` ctx) · 10.2 KB, 333 lines · **~260 cloud spec + receipt tokens (~91.0% cloud output saved, -2,613 tok)** (`69,004` local tokens, `1` repair)* |

| Variant | Models Used (Caption) | Output | Cloud Tokens | Cloud Saved (est.) | Local Tokens | Time | Verification |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| **Without Tandem** | `Gemini Hydrogen` (Cloud Direct) | **[Live Demo](https://alenoc.github.io/tandem-mcp/benchmarks/animation_without_tandem/)** ([source](benchmarks/animation_without_tandem/index.html), 10.3 KB, 272 lines) | ~2,873 out | — | 0 | Immediate | `node --check` + DOM PASS |
| **With Tandem MCP** | Orchestrator: `Gemini Hydrogen` · Local: `qwen3.8-27b@iq3_s` (`LM Studio`, `delegate`) | **[Live Demo](https://alenoc.github.io/tandem-mcp/benchmarks/animation_with_tandem/)** ([source](benchmarks/animation_with_tandem/index.html), 10.2 KB, 333 lines) | ~260 spec+receipt | **~2,613 tok (91.0%)** | 69,004 | 819.7 s | `node --check` + PNG PASS + `job_feedback(accepted=True)` |

> **Cloud token savings:** offloading the 333-line animation generation to `qwen3.8-27b@iq3_s` cut cloud output tokens from **~2,873** down to **~260** (**~91.0% saved**, `-2,613` cloud tokens).

**[Open both interactive animations side-by-side in your browser](https://alenoc.github.io/tandem-mcp/benchmarks/animation_comparison.html)** ([source](benchmarks/animation_comparison.html))

<details>
<summary>Exact prompt used for 2D orbital animations</summary>

```text
Create a single self-contained file index.html implementing an interactive full-viewport HTML5 Canvas orbital particle simulation in dark space (#060913):
1. Responsive full-window <canvas> using requestAnimationFrame and devicePixelRatio scaling.
2. Central glowing star using createRadialGradient and a subtle corona pulse.
3. At least 5 orbiting planets with distinct orbital radii, speeds, colors, at least 3 moons/satellites, and fading orbital trails.
4. Twinkling background starfield with at least 150 stars.
5. Interactive glassmorphism HUD overlay with:
   - Play/Pause toggle button
   - Trails ON/OFF toggle button
   - Reset button
   - Speed range slider (<input type="range" min="0.2" max="3.0" step="0.1" value="1.0">) with live multiplier readout
   - Live FPS, simulation time (s), and active burst particle count
6. Clicking anywhere on the canvas spawns a radial burst of glowing particles with velocity damping and fade-out.
Keep everything self-contained in index.html with zero external dependencies and valid JavaScript syntax.
```

</details>

### 3D Neon Portal & Floating Monolith — Quality-Preserved Hybrid Delegation

Using Tandem's **hybrid quality-preservation workflow** (non-vague contract `constraints` + `delegate_many` decomposition into `html_css`, `engine3d`, and `app_loop` + `job_diff` & orchestrator visual PNG inspection + targeted `job_continue` polish + `job_feedback`), the local executor (`qwen3.8-27b@iq3_s`) matches the frontier cloud baseline (`Gemini Hydrogen`) in framing, geometry, lighting, and HUD layout while cutting cloud output tokens by **~82.1%**:

<table>
  <thead>
    <tr>
      <th align="center">Without Tandem (Cloud Direct)</th>
      <th align="center">With Tandem MCP (Hybrid Quality Control)</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td align="center">
        <a href="https://alenoc.github.io/tandem-mcp/benchmarks/scene3d_without_tandem/">
          <img src="benchmarks/scene3d_without_tandem.gif" alt="3D Neon Portal without Tandem (Cloud Direct)" width="360" height="230" />
        </a><br />
        <sub><b>Model:</b> <code>Gemini Hydrogen</code> (direct)</sub><br />
        <sub>403 lines &middot; 15,724 B &middot; ~4,368 cloud output tokens</sub>
      </td>
      <td align="center">
        <a href="https://alenoc.github.io/tandem-mcp/benchmarks/scene3d_with_tandem/">
          <img src="benchmarks/scene3d_with_tandem.gif" alt="3D Neon Portal with Tandem MCP" width="360" height="230" />
        </a><br />
        <sub><b>Orchestrator:</b> <code>Gemini Hydrogen</code> + <b>Local:</b> <code>qwen3.8-27b@iq3_s</code></sub><br />
        <sub>778 lines (3 files) &middot; 22,883 B &middot; ~780 cloud tokens (<b>82.1% saved</b>)</sub>
      </td>
    </tr>
  </tbody>
</table>

| Variant | Model(s) | Output & Live Demo | Cloud Output Tokens | Cloud Tokens Saved | Local Tokens (`qwen3.8-27b@iq3_s`) | Verification |
| :--- | :--- | :--- | ---: | ---: | ---: | :--- |
| **Without Tandem** | `Gemini Hydrogen` (cloud direct) | **[Live Demo](https://alenoc.github.io/tandem-mcp/benchmarks/scene3d_without_tandem/)** ([source](benchmarks/scene3d_without_tandem/index.html), 15.7 KB, 403 lines) | ~4,368 | — | — | `node --check` PASS + headless Chrome PNG/FPS check (`60 FPS`, `84` polys) |
| **With Tandem MCP** | Orchestrator: `Gemini Hydrogen` · Local: `qwen3.8-27b@iq3_s` (`LM Studio`, `delegate_many` + `job_continue`) | **[Live Demo](https://alenoc.github.io/tandem-mcp/benchmarks/scene3d_with_tandem/)** ([index.html](benchmarks/scene3d_with_tandem/index.html), [engine3d.js](benchmarks/scene3d_with_tandem/engine3d.js), [app.js](benchmarks/scene3d_with_tandem/app.js), 22.9 KB, 778 lines) | ~780 (specs + visual polish) | **~3,588 tok (82.1%)** | 199,095 | All 3 jobs `VERIFIED` (`node --check` PASS) + visual PNG parity check + `job_feedback(accepted=True)` |

> **Cloud token savings & quality parity:** decomposing the 3D engine into 3 contracted modules (`html_css`, `engine3d`, `app_loop`) and running targeted `job_continue` polish passes after `job_diff` and PNG inspection cut cloud output tokens from **~4,368** down to **~780** (**~82.1% saved**, `-3,588` cloud tokens) with **no visual degradation**.

**[Open both interactive 3D portals side-by-side in your browser](https://alenoc.github.io/tandem-mcp/benchmarks/scene3d_comparison.html)** ([source](benchmarks/scene3d_comparison.html))

<details>
<summary>Architectural spec & decomposition used for 3D Neon Portal</summary>

- `html_css` (`index.html`, 166 lines): full-viewport `<canvas id="c">`, dark radial gradient `#0d1633 -> #050814 -> #020309`, compact top-left glassmorphic `.hud` (`min-width: 220px`, `padding: 8px 10px`, `font-size: 11px`) with `#fps`, `#polys`, `#parts`, `#playBtn`, `#orbitBtn`, `#resetBtn`, `#spd`, `#spdVal`.
- `engine3d` (`engine3d.js`, 394 lines): `window.PortalEngine(canvas, hudRefs)` with `yaw=0.55, pitch=0.34, dist=9.6, fov=580`, `y=-2.0` cyber-grid, floating stepped obsidian platform (`y=-1.25` and `y=-0.85`), twin pillars (`x=±1.25`), lintel (`y=1.95`) + crown cap (`y=2.32`), 6 alternating cyan/magenta octahedral crystals orbiting at `r=2.45`, directional lighting + painter's sort, radial-gradient portal core + 2 counter-rotating tilted rings, 180 twinkling stars, 110 rising neon particles, pointer drag-orbit & wheel zoom.
- `app_loop` (`app.js`, 18 lines): binds `#c` and HUD refs, instantiates `PortalEngine`, calls `engine.start()`.

</details>

*\*In the `README.md` run, the local model paraphrased its quotes instead of copying them verbatim; Tandem's verifier dropped all 3 and flagged `unsupported` instead of passing unverified claims to the cloud model.*

**Takeaway:** `digest_file` (especially with `grep`) and `digest_many` deliver **98%+** cloud input savings; `delegate` pays off on multi-file or test-repair tasks, while trivial 1-file edits save too few tokens to justify local latency.

---

## Tests

```sh
.venv/bin/python tests/test_offline.py     # 156 checks: limits, evidence, journal, rollback, installer
.venv/bin/python tests/test_protocol.py    # 149 checks: full loop against scripted server (no model)
.venv/bin/python tests/test_live.py        # live checks against your running local model
.venv/bin/python tests/test_live.py --text # live checks via JSON-reply protocol
```

<details>
<summary>Measured on real models (tests/test_live.py, Nov 2026) &amp; repository layout</summary>

| Model | Server | Context | Protocol | Result |
| --- | --- | --- | --- | --- |
| Qwen 3.8 27B (IQ3_S) (`qwen3.8-27b@iq3_s`) | LM Studio | 65536 | native tool calls | 12 of 12 |
| Qwen 3.8 27B (IQ3_S) (`qwen3.8-27b@iq3_s`) | LM Studio | 65536 | JSON replies | 12 of 12 |
| Gemma 4 E2B (Q4_K_M) (`gemma4:e2b`) | Ollama | 4096 | native tool calls | 12 of 12 (1 repair) |
| Gemma 4 E2B (Q4_K_M) (`gemma4:e2b`) | Ollama | 4096 | JSON replies (prompt) | reading 7/7; fix verified 1/3 |

**Repository layout:**
- `tandem_mcp/server.py`: MCP tools and receipts
- `tandem_mcp/engine.py`: server discovery, probing, completions, JSON schema validation
- `tandem_mcp/digest.py`: chunked reading, quote/claim checks, extraction, agreement
- `tandem_mcp/agent.py`: executor loop, journal, snapshot, guard, batches, rollback
- `tandem_mcp/sandbox.py`: workspace/command limits, SHA-256 stamp, bubblewrap sandbox
- `tandem_mcp/store.py`: ledger, lessons, model caps, cache & job retention
- `scripts/install.py`: one-command installer for Claude Code, Codex, and Antigravity
- `benchmarks/`: reproducible benchmark script and results

</details>

## License

MIT, see [LICENSE](LICENSE).
