<div align="center">

<h1>Tandem MCP</h1>

<img src="assets/logo.svg" alt="Tandem MCP logo: a tandem bicycle, two riders on one frame" width="240">

<p>
  <a href="https://github.com/ALENOC/tandem-mcp/releases"><img src="https://img.shields.io/github/v/release/ALENOC/tandem-mcp" alt="GitHub Release"></a>
  <a href="https://github.com/ALENOC/tandem-mcp/actions/workflows/tests.yml"><img src="https://github.com/ALENOC/tandem-mcp/actions/workflows/tests.yml/badge.svg" alt="CI"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
</p>

</div>

Tandem MCP lets the model in your chat hand part of a coding task to a model running on your own machine. A typical request is “fix this function, leave the tests alone, and show me the diff.” The cloud model decides what to hand off. The local model does the edit, and Tandem returns the changes and test results for review.

## Connect your agent

Tandem runs as a local MCP server over standard input and output (stdio). The installer registers it with **Claude Code**, **Codex** and **Antigravity**. You can also register the same server manually in **Gemini CLI** or another client that can launch a local stdio server. Each client handles its own tool permissions. [Setup and manual configuration](docs/GETTING_STARTED.md#3-register-with-your-mcp-client)

## How a delegated edit works

[![Delegation from the chat agent to Tandem and the local model. The four steps are described below.](assets/architecture.svg)](assets/architecture.svg)

1. **Your agent sets the task.** Say you ask it to fix a discount calculation. The agent can call `delegate` with the goal, the file the worker may edit and the test to run.
2. **Tandem asks the local model.** The server sends the task and relevant context to your model endpoint. The model can ask to read a file, propose an edit or request a command.
3. **Tandem applies the edit and checks it.** The server handles those tool calls inside the workspace limits. It runs the requested test and records the result and the diff. Command isolation depends on the configured sandbox.
4. **Your agent reviews the result.** It can inspect the diff and test output, report a failure or request a rollback. For a read-only question, it can use a digest tool and ask for the relevant lines directly.

[Architecture in detail](docs/ARCHITECTURE.md) · [Workspace and sandbox permissions](docs/SECURITY_MODEL.md)

## Does it save cloud tokens?

Yes, on medium and large work. With **Opus 5.5** as the orchestrator in Claude Code and the autonomous profile, Opus writes a contract once. Tandem's local model then writes the code and repairs it against the checks, with no cloud call, and Opus gets back one line. Over five tasks, three pairs each, Tandem cut the total cloud bill by **61%** and the cost per successful result by **52%**. It used **72% fewer output tokens**, the most expensive kind.

| Task | Direct | With Tandem | Cloud cost per success |
| --- | --- | --- | ---: |
| 5-line bug fix | $0.046 · 3/3 · 12 s | $0.050 · 3/3 · 2 min | **+10%** |
| Cron parser module with tests | $0.243 · 3/3 · 66 s | $0.177 · 2/3 · 25 min | **-27%** |
| Boids web simulation | $0.242 · 3/3 · 65 s | $0.157 · 2/3 · 10 min | **-35%** |
| Orbital web simulation | $0.459 · 2/3 · 79 s | $0.199 · 2/3 · 26 min | **-57%** |
| 3D neon portal | 0/3 · $0.537 per attempt | 0/3 · $0.135 per attempt | -75% per attempt |
| **All 15 attempts** | **$4.12 · 11/15** | **$1.62 · 9/15** | **-52%** |

Each cell gives the cost per success (list prices, failed attempts counted), the successes inside the time budget and the median time.

The trade-offs:

- **Small edits do not pay:** writing the contract costs about as much as the edit. Tandem tells Opus to do edits under about 30 lines itself.
- **Time:** a result takes minutes to an hour on the local model instead of seconds.
- **Punctuality:** ignoring the time budget both arms deliver 11 correct results of 15, and Tandem is 61% cheaper. Inside the budget Tandem delivers 9 against 11, because two results came after the deadline.
- **Finish:** the local model does what the contract says and little more. On the 3D portal its renderer runs at about 16 FPS against 60.

[All results, method and earlier iterations](docs/BENCHMARKS.md)

### 3D neon portal

<table>
  <tr>
    <th width="50%">Direct</th>
    <th width="50%">With Tandem</th>
  </tr>
  <tr>
    <td><img src="benchmarks/opus/gifs/portal_direct.gif" width="100%" alt="3D portal written directly by Opus"></td>
    <td><img src="benchmarks/opus/gifs/portal_tandem.gif" width="100%" alt="3D portal written by the local model through Tandem"></td>
  </tr>
  <tr>
    <td align="center">$0.33 cloud · 82 s</td>
    <td align="center">$0.11 cloud · 52 min</td>
  </tr>
</table>

### Orbital simulation

<table>
  <tr>
    <th width="50%">Direct</th>
    <th width="50%">With Tandem</th>
  </tr>
  <tr>
    <td><img src="benchmarks/opus/gifs/orbital_direct.gif" width="100%" alt="Orbital simulation written directly by Opus"></td>
    <td><img src="benchmarks/opus/gifs/orbital_tandem.gif" width="100%" alt="Orbital simulation written by the local model through Tandem"></td>
  </tr>
  <tr>
    <td align="center">$0.31 cloud · 79 s · passed</td>
    <td align="center">$0.14 cloud · 19 min · passed</td>
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

For manual setup or a different model endpoint, see [Getting Started](docs/GETTING_STARTED.md) and [Configuration](docs/CONFIGURATION.md). The decision report describes the experimental routing used in the chat benchmarks. The released server's tools are listed in the [tool reference](docs/TOOLS.md).

[Changelog](CHANGELOG.md) · [Security policy](SECURITY.md) · [MIT license](LICENSE) · Copyright (c) 2026 [Alessandro Nocentini](https://github.com/ALENOC)
