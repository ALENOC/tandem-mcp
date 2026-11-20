<div align="center">

<h1>Tandem MCP</h1>

<img src="assets/logo.svg" alt="Tandem MCP logo: a tandem bicycle, two riders on one frame" width="360">

<p>
  <a href="https://github.com/ALENOC/tandem-mcp/releases"><img src="https://img.shields.io/github/v/release/ALENOC/tandem-mcp" alt="GitHub Release"></a>
  <a href="https://github.com/ALENOC/tandem-mcp/actions/workflows/tests.yml"><img src="https://github.com/ALENOC/tandem-mcp/actions/workflows/tests.yml/badge.svg" alt="CI"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
</p>

</div>

Tandem MCP gives a cloud orchestrator access to a local OpenAI-compatible model. It can read files locally, delegate edits within a workspace, run acceptance checks and return a receipt showing what was verified.

## Quick start

Use Python 3.11 or newer. For delegated commands under the default secure sandbox on Linux, install `bubblewrap`. Start your local model server and load a model. LM Studio commonly serves the API at `http://127.0.0.1:1234/v1`. Set `TANDEM_BASE_URL` if your endpoint differs.

```sh
git clone https://github.com/ALENOC/tandem-mcp
cd tandem-mcp
python3 -m venv .venv
.venv/bin/pip install .
```

For Antigravity (`agy`), run this from the repository root:

```sh
agy mcp add \
  --env TANDEM_PROFILE=lean \
  tandem-mcp "$PWD/.venv/bin/python" "$PWD/main.py"
agy mcp enable tandem-mcp
agy mcp list
```

For other supported clients, run `.venv/bin/python scripts/install.py` and restart the client. See [Getting Started](docs/GETTING_STARTED.md) for manual registration and [Configuration](docs/CONFIGURATION.md) for endpoint and sandbox settings.

## Using Tandem in chat

The examples below describe the experimental first-turn policy used in the benchmark workspace. The installation above registers the published lean server.

| Example request | Expected behavior in agy |
| --- | --- |
| `usa Tandem: correggi questa funzione e verifica i test esistenti` | The orchestrator can edit and test directly on the first turn. This is the recommended path for routine changes. |
| `usa Tandem, privilegia il risparmio cloud: crea un modulo con test` | The orchestrator may delegate substantial new code with executable checks. A preference for savings still allows a direct edit. |
| `usa Tandem, solo locale: analizza questo file` | Request local processing with cloud fallback disabled. The initial request still reaches the cloud orchestrator in agy. |

For delegated jobs, the orchestrator specifies the goal, writable paths, allowed commands and verification steps. In the experimental host-managed mode the client starts the watcher returned by `delegate`. The watcher waits locally and returns the job receipt to the chat. Review the checks and any missing proof before accepting changes. A passing browser startup check alone establishes no coverage for individual interactions. See [Architecture](docs/ARCHITECTURE.md) and the [tool reference](docs/TOOLS.md) for evidence, diffs and rollback.

## Benchmark results

In ordinary agy chat, direct execution is the best-supported default for the tasks measured. Cloud tokens per success include failed attempts. Time below is end-to-end unless indicated otherwise.

| Task and execution path | Result |
| --- | --- |
| Small edit with tests, MCP active | On the discount task both paths passed. Direct used 26,953 cloud tokens in 24 s. Delegation used 33,479 in 105 s. One attempt per path. |
| Boids web app, ordinary chat | Both paths passed 3/3. Delegation saved 0.95% of cloud tokens per success and added 8.6 minutes to median delivery time. The direct reference had MCP disabled. |
| 3D Portal, external host orchestration | Delegation passed 2/3 and used 37,975 cloud tokens per success, including the failed attempt. The direct reference passed 1/1 at 92,941 tokens. Successful delegated attempts took 37 and 58 minutes. |

The [decision report (Italian)](docs/DECISION_REPORT_20261120.md) includes per-task results, missing token counts and the limits of each comparison. See [benchmark methodology](docs/BENCHMARKS.md) and the [visual demos](benchmarks/hydrogen_3_6_1/gifs/).

## Workspace isolation

On Linux the default secure mode requires Bubblewrap for command isolation. Compatibility mode relies on application-level checks and has weaker isolation. Contracts limit writes, protect verification files and record changes for review and rollback. See the [security model](docs/SECURITY_MODEL.md) for platform differences and backup limits.

## Documentation

- [Getting Started](docs/GETTING_STARTED.md)
- [Architecture](docs/ARCHITECTURE.md) ([English PDF](docs/tandem-mcp-architecture.pdf) · [Italian PDF](docs/tandem-mcp-architettura.pdf))
- [MCP Tools Reference](docs/TOOLS.md)
- [Security Model](docs/SECURITY_MODEL.md)
- [Configuration](docs/CONFIGURATION.md)
- [Benchmarks](docs/BENCHMARKS.md)
- [Comparison With Alternatives](docs/COMPARISON.md)
- [Changelog](CHANGELOG.md)

## License & Attribution

[MIT License](LICENSE) · Copyright (c) 2026 **Alessandro Nocentini** ([@ALENOC](https://github.com/ALENOC)) · [Security Policy](SECURITY.md)
