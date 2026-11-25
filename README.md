<div align="center">

<h1>Tandem MCP</h1>

<img src="assets/logo.svg" alt="Tandem MCP logo: a tandem bicycle, two riders on one frame" width="240">

<p>
  <a href="https://github.com/ALENOC/tandem-mcp/releases"><img src="https://img.shields.io/github/v/release/ALENOC/tandem-mcp" alt="GitHub Release"></a>
  <a href="https://github.com/ALENOC/tandem-mcp/actions/workflows/tests.yml"><img src="https://img.shields.io/github/actions/workflow/status/ALENOC/tandem-mcp/tests.yml?branch=main&amp;label=tests" alt="CI"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
</p>

</div>

Tandem MCP lets the model in your chat hand part of a coding task to a model running on your own machine. A typical request is “fix this function, leave the tests alone, and show me the diff.” The cloud model decides what to hand off. The local model does the edit, and Tandem returns the changes and test results for review.

## Connect your agent

Tandem runs as a local MCP server over standard input and output (stdio). The installer registers it with **Claude Code**, **Codex** and **Antigravity**. You can also register the same server manually in **Gemini CLI** or another client that can launch a local stdio server. Each client handles its own tool permissions. [Setup and manual configuration](docs/GETTING_STARTED.md#3-register-with-your-mcp-client)

## How a delegated edit works

<p align="center"><a href="assets/architecture.svg"><img src="assets/architecture.svg" alt="Delegation from the chat agent to Tandem and the local model. The four steps are described below."></a></p>

1. **Your agent sets the task.** Say you ask it to fix a discount calculation. The agent can call `delegate` with the goal, the file the worker may edit and the test to run.
2. **Tandem asks the local model.** The server sends the task and relevant context to your model endpoint, keeping the prompt prefix stable so the local server reuses its KV cache. The model can ask to read a file, propose an edit or request a command.
3. **Tandem applies the edit and checks it.** The server handles those tool calls inside the workspace limits. It runs the requested test and records the result and the diff. Command isolation depends on the configured sandbox.
4. **Your agent reviews the result.** It can inspect the diff and test output, report a failure or request a rollback. For a read-only question, it can use a digest tool and ask for the relevant lines directly.

[Architecture in detail](docs/ARCHITECTURE.md) · [Workspace and sandbox permissions](docs/SECURITY_MODEL.md)

## Why a server, and not just a prompt?

You could tell your agent to call the local model itself, for example with `curl` against LM Studio. It works, but it saves little and checks nothing.

| | Agent calls the local model directly | Through Tandem |
| --- | --- | --- |
| **Who writes the files** | The local model answers with text. The agent reads it and writes it to disk, paying output tokens, the most expensive kind, for code it did not write. | The local model edits the files itself through tools. The code never passes through the cloud model. |
| **Who runs the repair loop** | The agent. Each failed test is one more cloud turn: read the error, write a new prompt, read the new answer. | Tandem, locally. It runs the checks, keeps the failing lines even in long outputs, stops early if the worker repeats the same failure three times, and returns one line at the end. |
| **What gets checked** | Whatever the agent remembers to check, after it has read the output. | Every job: checks run before the edit and must pass after it, slow passing checks go back once, test files are read-only and restored if touched, each constraint needs a cited line, and web pages are checked in headless Chromium against a 40 FPS floor with live 1280x800 screenshot capture, optional local VLM visual review (against the contract or a `reference_image`), and screenshot attachment on the receipt. |
| **What the local model may touch** | Anything the agent's shell can reach. | Only the files in `write_globs` and the commands in `allow_run`, in a Bubblewrap jail on Linux. Outbound symlinks are refused and secrets are masked in tool output. |
| **Undo** | By hand, or with git if the work was committed. | `job_rollback` restores the original bytes from the job journal. |
| **Long jobs** | A shell call that runs for an hour hits the client timeout. | Progress notifications keep the call alive. Job state is stored on disk, and a failed job can go on with `job_continue`. |

In short: without a server, the agent still reads and writes everything the local model produces, so most of the cloud cost stays. Tandem keeps that traffic on your machine and returns only the verdict.

## Does it save cloud tokens?

Yes, on medium and large work. With **Opus 5.5** as the orchestrator in Claude Code and the autonomous profile (Tandem **4.2.0**), Opus writes a contract once. Tandem's local model then writes the code and repairs it against the checks, with no cloud call, and Opus gets back one line plus, on web work, a 1280x800 screenshot. In a fresh campaign of five tasks, three counterbalanced pairs each (15 attempts per arm), both arms delivered **10/15** results inside the budget, and Tandem cut the total cloud bill and the cost per successful result by **53%** (`$0.202` against `$0.429`), using **68% fewer output tokens**.

| Task | Direct | With Tandem | Cloud cost per success |
| --- | --- | --- | ---: |
| 5-line bug fix | $0.062 · 3/3 · 10 s | $0.067 · 3/3 · 2 min | **+8%** |
| Cron parser module with tests | $0.268 · 3/3 · 60 s | $0.210 · 2/3 · 26 min | **-22%** |
| Boids web simulation | $0.205 · 3/3 · 54 s | $0.127 · 3/3 · 11 min | **-38%** |
| Orbital web simulation | $0.951 · 1/3 · 86 s | $0.467 · 1/3 · 12 min | **-51%** |
| 3D neon portal (4 files) | no success · 0/6 (3 + 3 rerun) · 2.2 min · $0.562 per attempt | $0.548 · 1/3 · 33 min | Direct 0/6 (Tandem -68% per attempt) |
| **All 15 attempts** | **$4.29 · 10/15 · $0.429** | **$2.02 · 10/15 · $0.202** | **-53%** |

Each cell gives the cost per success (list prices, failed attempts counted), the successes inside the time budget and the median time. Run `20261124-174810_v4_2`, report [`REEVAL_4_2.json`](benchmarks/opus/REEVAL_4_2.json), evaluated three times per artifact by the same independent evaluators as 4.0.0 and 4.1.0 (identical SHA-256).

Direct portal rerun: because no Direct portal passed, 3 more Direct-only portal attempts were run later (run `20261125-093809_v4_2_portal_direct`, report [`REEVAL_4_2_PORTAL_DIRECT.json`](benchmarks/opus/REEVAL_4_2_PORTAL_DIRECT.json), same evaluators, identical SHA-256). They failed too: after Reset the scene stays paused (2 attempts), Orbit OFF does not stop the camera (1 attempt), and one also fails `visual`. Across all 6 Direct attempts the portal is **0/6**, `$3.37` in total, `$0.562` per attempt and 2.2 min median, against `$0.183` per attempt for Tandem (**-68%**). These 3 attempts are not paired and use Claude Code 2.1.332 instead of 2.1.331, so they stay out of the 15-attempt totals above.

The trade-offs:

- **Small edits do not pay:** the 5-line fix cost **+8%** with Tandem (`+10%` in 4.0.0). Tandem tells Opus to do edits under about 30 lines itself.
- **Time:** a Tandem result takes a median of 11 to 33 minutes on medium and large tasks, against 1 to 2.5 minutes direct. On the four tasks shared with earlier versions the Tandem median went from 25 min (4.0.0) to 19 min (4.1.0) to 16 min (4.2.0).
- **Not every loss is visible in the totals:** two Tandem attempts ended with Opus patching the files itself after the local job failed (Cron pair 2, out of time; Portal pair 1, stuck). Both still failed and are counted as failures. Cron pair 2 also ran 31 minutes over budget because `job_continue` opened a second full local time window.
- **Incident:** one Direct attempt (Orbital pair 1) hit an 82-minute cloud API stall and ran over budget; its page passes the evaluator. Without it, Direct is `$0.394` per success (10/14) and Tandem still saves **49%**.
- **Sample size:** with 3 pairs per task, a 1-success gap is not statistically decisive.
- **Visual review:** the local VLM reviewed 7 of the 9 Tandem web pages and raised 2 strikes, both false positives (see [BENCHMARKS](docs/BENCHMARKS.md#visual-review-and-screenshots)). After seeing the attached screenshot, Opus sent 3 visual `job_continue` hints (HUD labels, HUD overflow, portal grid and rings), at $0.02 to $0.04 of extra cloud cost each. All Tandem web pages that passed run at 60 FPS at 1280x800. Direct pages still have more visual polish.

Test machine: Intel Core i9-9900K, AMD Radeon RX 6800 series GPU with 16 GB VRAM, LM Studio (llama.cpp Vulkan runtime 2.82.0) running `Qwen3.8-27B-UD-IQ3_S` with `mmproj-F16.gguf` (loaded as `type=vlm`, so the same model also does the visual review) fully on the GPU with a 40,960-token context. [Full hardware and model settings](docs/BENCHMARKS.md#test-machine-and-local-model)

[All results, method and earlier iterations](docs/BENCHMARKS.md) · [Interactive comparison, also on mobile](https://alenoc.github.io/tandem-mcp/)

### 3D neon portal

<table>
  <tr>
    <th width="50%">Direct (v4_2, pair 2)</th>
    <th width="50%">With Tandem (v4_2, pair 2)</th>
  </tr>
  <tr>
    <td><img src="benchmarks/opus/gifs/portal_direct.gif" width="100%" alt="3D portal written directly by Opus"></td>
    <td><img src="benchmarks/opus/gifs/portal_tandem.gif" width="100%" alt="3D portal written by the local model through Tandem"></td>
  </tr>
  <tr>
    <td align="center">$0.59 cloud · 134 s · failed (interactions) · 60 FPS</td>
    <td align="center">$0.15 cloud · 40 min · passed · 60 FPS · 1 visual hint</td>
  </tr>
</table>

The only Tandem portal that passed, next to the Direct portal from the same pair (no Direct portal passed: 0/3 in the campaign, 0/3 in the rerun). Direct's scene is richer and fills the frame; Tandem's is correct but small and plain.

### Orbital simulation

<table>
  <tr>
    <th width="50%">Direct (v4_2, pair 3)</th>
    <th width="50%">With Tandem (v4_2, pair 3)</th>
  </tr>
  <tr>
    <td><img src="benchmarks/opus/gifs/orbital_direct.gif" width="100%" alt="Orbital simulation written directly by Opus"></td>
    <td><img src="benchmarks/opus/gifs/orbital_tandem.gif" width="100%" alt="Orbital simulation written by the local model through Tandem"></td>
  </tr>
  <tr>
    <td align="center">$0.30 cloud · 86 s · passed · 60 FPS</td>
    <td align="center">$0.16 cloud · 14 min · passed · 60 FPS · 1 visual hint</td>
  </tr>
</table>

## Try it

Start a local OpenAI-compatible model server and load a model. LM Studio usually listens at `http://127.0.0.1:1234/v1`. You will also need Python 3.11 or newer and, for secure command execution on Linux, Bubblewrap.

```sh
git clone https://github.com/ALENOC/tandem-mcp
cd tandem-mcp
python3 -m venv .venv
.venv/bin/pip install .
.venv/bin/python scripts/install.py
```

Restart your MCP client, open a project and try a read-only request:

> Use Tandem to find where this project validates its input. Give me the file names and line numbers.

For a first edit, pick a failing test and tell the worker which file it may change:

> Use Tandem to fix the discount calculation in discount.py. Keep the tests unchanged, run them, and show me the diff.

For manual setup or a different model endpoint, see [Getting Started](docs/GETTING_STARTED.md) and [Configuration](docs/CONFIGURATION.md). The tools are listed in the [tool reference](docs/TOOLS.md).

## License

[MIT](LICENSE). Copyright (c) 2026 Alessandro Nocentini ([ALENOC](https://github.com/ALENOC)). As the MIT license requires, forks and derivative works must keep this copyright notice and the license text.

[Changelog](CHANGELOG.md) · [Security policy](SECURITY.md)
