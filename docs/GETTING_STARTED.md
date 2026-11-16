# Getting Started

## Prerequisites

- **Python 3.11+**
- **Local OpenAI-compatible LLM server**, such as:
  - **LM Studio** (default endpoint `http://127.0.0.1:1234/v1`; port can be changed in LM Studio settings)
  - **Ollama** (`http://127.0.0.1:11434/v1`)
  - **llama.cpp**, **vLLM**, **Jan**, **KoboldCpp**, **text-generation-webui**, or **LocalAI**
- **Linux (`bubblewrap`)**: recommended for OS-level sandbox isolation (`sudo apt-get install bubblewrap` on Debian/Ubuntu). On Linux, `TANDEM_SANDBOX` defaults to `secure` (fail-closed if `bubblewrap` is unavailable). On macOS and Windows, it defaults to `compatible` (command-text checks and outbound symlink refusal, without OS-level filesystem isolation).

## 1. Install Tandem MCP

```sh
git clone https://github.com/ALENOC/tandem-mcp
cd tandem-mcp
python3 -m venv .venv
.venv/bin/pip install .
```

## 2. Start your local LLM server

Start **LM Studio** (or another supported server) and load a chat/coding model (for example `qwen3.8-27b@iq3_s` or similar). Tandem auto-detects usual local ports in order:

1. LM Studio (`1234`)
2. Ollama (`11434`)
3. llama.cpp (`8080`)
4. vLLM (`8000`)
5. Jan (`1337`)
6. KoboldCpp (`5001`)
7. text-generation-webui (`5000`)
8. LocalAI (`8081`)

If your server runs on a custom host or port, set `TANDEM_BASE_URL` (see [Configuration](CONFIGURATION.md)).

## 3. Register with your MCP client

### Automatic installer (Claude Code, Codex, Antigravity)

```sh
.venv/bin/python scripts/install.py
```

Useful installer flags:
- `--clients claude,codex,antigravity`: select specific clients (default: all three).
- `--replace-legacy`: remove any old `lmstudio` MCP entries while installing `tandem-mcp`.
- `--env KEY=VALUE`: pass environment variables to the MCP server (repeatable, e.g. `--env TANDEM_BASE_URL=http://127.0.0.1:1234/v1`).
- `--dry-run`: preview changes without modifying files.
- `--uninstall`: remove `tandem-mcp` from the selected clients.

### Manual stdio configuration

Add the following entry to your MCP client configuration:

```json
{
  "command": "/path/to/tandem-mcp/.venv/bin/python",
  "args": ["/path/to/tandem-mcp/main.py"]
}
```

`python main.py`, `python -m tandem_mcp`, and `.venv/bin/tandem-mcp` all start the same server.

## 4. Verify the connection

Restart your MCP client so it loads `tandem-mcp`, then ask your cloud agent:

```text
Run executor_status
```

You should see your active local server URL, loaded model, context length, and sandbox status.

## 5. Optional: agent instructions (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`)

You can add standing guidance to your project or global agent instructions file so your cloud AI prefers Tandem for large reads and bounded edits (note: instruction-file behavior depends on each MCP client):

```markdown
When `tandem-mcp` is available:
- Use `digest_file` (with `grep` when searching) or `digest_many` to inspect large files, logs, and unfamiliar modules instead of reading them directly into cloud context.
- Use `delegate` for bounded, test-verified mechanical edits, then review `job_diff` and close with `job_feedback` or `job_rollback`.
```
