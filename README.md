# Tandem MCP

An MCP server that pairs a cloud orchestrator model with a local executor model running in LM Studio (tested with Qwen 3.8 27B). The orchestrator keeps the decisions and the final check. The local model reads, edits and runs things on the machine and reports in a few lines, so the material never enters the context of the orchestrator.

The usual "ask a local model" tool only moves text generation. Most of the cost of an agent session is the material it reads (logs, sources, reports), and the risk of a small model is that it invents. This server addresses both:

- **Contracts.** `delegate` hands over a task with a workspace, the files that may be written, the commands that may be run, and the checks that decide acceptance. The server runs the checks itself, sends failures back to the executor for repair, and returns a receipt. Every changed file is journalled: the task can be shown as a diff and undone.
- **Checked evidence.** `digest_file`, `digest_command` and `digest_many` answer a question about material the orchestrator does not read. Each answer carries line numbers and quotes, and the server looks every quote up in the source. A quote that is not there is dropped and reported, so a made-up answer is visible without reading the source.
- **Supervised memory.** `job_feedback` records the verdict of the orchestrator; its lesson is given to the executor at its next tasks in the same project. `ledger_report` shows calls, tokens, the characters read against the characters returned, the acceptance rate and the speed, to decide what is worth delegating.
- **Agreement score.** `ask` with `samples` runs a task several times and reports how many runs agree, a cheap sign of when not to trust the executor.

## Tools

| Tool | Purpose |
| --- | --- |
| `executor_status` | Models in LM Studio, which one is loaded, context length |
| `ask` | Text task; optional JSON schema; `samples` for an agreement score |
| `digest_file` | Question about a file (text, source, log, JSON, PDF), answer with checked quotes; long files are read in parts; `grep` narrows first |
| `digest_command` | Runs a command of the orchestrator and returns exit code, verdict with checked quotes, last lines and the path of the full output |
| `digest_many` | Same question for many files, one line per file |
| `extract_from_file` | Structured data in a JSON schema |
| `delegate` | Bounded task with limits and checks; returns a receipt |
| `job_status`, `job_diff`, `job_rollback` | Follow, inspect and undo a delegated task |
| `job_feedback` | Verdict and lesson for the executor |
| `lesson_add`, `lessons` | Standing rules per project or for all projects |
| `ledger_report` | Activity, estimated savings, acceptance rate, speed |
| `ask_local_qwen`, `generate_code_with_qwen`, `check_lmstudio_status` | Names of version 1, kept |

## A delegated task

```
delegate(
  goal="tests/test_calc.py fails. Fix calc.py so that the test passes. Do not change the test.",
  workspace="/path/to/project",
  verify_commands=["python3 tests/test_calc.py"],
  write_globs=["calc.py"],
  allow_run=["^python3 tests/"])

job 20261112-191600-f93060: VERIFIED  (4 steps, 0 repairs, 40.8 s, 6249 executor tokens)
executor: Fixed calc.py: dbm_to_mw now uses 10**(dbm/10) instead of /20, and swr returns 1.0 when forward power is zero.
  changed calc.py  +3 -1
  check PASS  $ python3 tests/test_calc.py
```

States of a receipt: `verified` (checks passed), `unverified` (no check given), `checks_failed`, `blocked` (the executor says why), `out_of_steps`, `error`.

## Limits of the executor

- Paths are resolved and must stay inside the workspace; `.git` is never writable; `write_globs` narrows further.
- The executor runs a command only if it matches `allow_run`, and never one of the safety list (sudo, git push/commit/reset, recursive deletes of root or home, package installs, remote shells and others, see `tandem/sandbox.py`).
- `verify_commands` and `digest_command` are written by the orchestrator and run as given.
- The reasoning text of the model is never returned as an answer.
- The command limits are pattern checks, not an operating system sandbox: allow only commands you would run yourself.

## Install

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

MCP client configuration (stdio):

```json
{"command": "/path/to/.venv/bin/python", "args": ["/path/to/main.py"]}
```

Environment: `LM_STUDIO_BASE_URL` (default `http://127.0.0.1:1234/v1`), `TANDEM_MODEL` (default: the loaded chat model), `TANDEM_HOME` (default `~/.local/share/tandem-mcp`, holds the ledger, the lessons and the job folders).

## Tests

```sh
.venv/bin/python tests/test_offline.py     # no model needed
```

## Layout

- `main.py`: the MCP tools and the receipts.
- `tandem/engine.py`: client of the local model, accounting.
- `tandem/digest.py`: reading in parts, evidence check, extraction, agreement.
- `tandem/agent.py`: the executor loop, journal, checks, rollback.
- `tandem/sandbox.py`: workspace and command limits.
- `tandem/store.py`: ledger, lessons, jobs.
