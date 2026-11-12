# Tandem MCP

<p align="center">
  <img src="assets/logo.svg" alt="Tandem MCP logo: a tandem bicycle, two riders on one frame" width="420">
</p>

<p align="center">
  <a href="https://github.com/ALENOC/tandem-mcp/actions/workflows/tests.yml"><img src="https://github.com/ALENOC/tandem-mcp/actions/workflows/tests.yml/badge.svg" alt="tests"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+">
</p>

An MCP server that pairs a cloud orchestrator model with a local executor model. The orchestrator keeps the decisions and the final check. The local model reads, edits and runs things on the machine and reports in a few lines, so the material never enters the context of the orchestrator.

The local model can be any model behind an OpenAI compatible server: LM Studio, Ollama, llama.cpp, vLLM, Jan, KoboldCpp, LocalAI. The server finds it, measures what it can do and adapts to it.

The usual "ask a local model" tool only moves text generation. Most of the cost of an agent session is the material it reads (logs, sources, reports), and the risk of a small model is that it invents. Tandem is built around that risk: nothing the local model says is passed on without a check that the model cannot influence.

## What it does that the others do not

Compared in November 2026, from the README of each project (not from running them), with the MCP servers [houtini-lm](https://github.com/houtini-ai/lm) and [local-vibes](https://github.com/OpenSourceWTF/local-vibes) and with the Fusion mode of [Atomic Agent](https://github.com/AtomicBot-ai/atomic-agent) (a full agent, not an MCP server). "no" means the README does not describe it; it is not a claim that the feature cannot exist there. Corrections are welcome.

| | Tandem | houtini-lm | local-vibes | Atomic Agent Fusion |
| --- | --- | --- | --- | --- |
| Local model edits files in a tool loop | yes | no (text only) | yes | yes |
| Acceptance checks run by the server, failures sent back for repair | yes | no | no (the task can ask the model to run a test) | `verify.run` runs checks (repair loop not confirmed) |
| Checks run before the work, so a check that already passes is reported as proving nothing | **yes** | no | no | no (`verify.run` runs on a throwaway copy of the working directory) |
| Files of the checks are read only, and put back if a command changes them | **yes** | no | no | no |
| Journal of every change: diff and rollback per task, without git | **yes** | no | diff stat only | not described (opt-in git worktrees, run checkpoints) |
| Quotes of an answer looked up in the source, invented ones dropped and reported | **yes** | no | no | no |
| Numbers of an answer and extracted values looked up in the source | **yes** | no | no | no |
| Agreement score over repeated runs | **yes** | no | no | no |
| Verdict of the orchestrator becomes a lesson for the next tasks of the project | **yes** | no | no | no (lessons come from reflection on episodes and votes) |
| A stopped task goes on in the same conversation with a hint | **yes** | no | no | partly (a hint from an escalation model; a run cut off by a crash resumes) |
| Models without native tool calling do delegated work | yes (JSON replies, schema forced where the server can) | not applicable | no | yes (grammar, own llama.cpp) |
| Capabilities of each model measured, not assumed | yes (probe) | profiles per family, speed measured per model | no | not confirmed |
| Command allow list checked on every part of a pipeline | **yes** | not applicable | no (shell on or off) | approval ladder, detail not confirmed |
| Operating system sandbox for the commands of the local model | yes (bubblewrap: no network, machine read only) | not applicable | no (path confinement only) | no (approval ladder, secrets removed from the command environment) |
| Tasks with dependencies, file ownership between parallel tasks | yes | no | no (parallel calls, separate directories advised) | yes (waves, optional worktrees) |
| Accounting of what delegation saved | yes, with quote failure rate and acceptance per model | yes | no | tokens and cost per worker |

Where the others are ahead: houtini-lm reaches cloud providers too and keeps richer per-model performance statistics; Atomic Agent is a complete agent with its own model manager, a user interface and parallel workers across several cloud providers. Tandem is only the part between an orchestrator you already use and a model you already run.

## The ideas

- **Contracts.** `delegate` hands over a task with a workspace, the files that may be written, the commands that may be run, and the checks that decide acceptance. The server runs the checks itself, sends failures back to the executor for repair, and returns a receipt. Every changed file is journalled: the task can be shown as a diff and undone.
- **Checks that mean something.** The checks run once before the work. The executor starts from their failures, and a check that already passed is marked in the receipt: it proves nothing about this task. The files the checks name, and test folders, are read only for the executor unless the contract names them as writable, so a small model cannot make a test pass by editing the test. If a command changes them anyway, the server puts them back and tells the executor why. The syntax of every changed file is checked too, and a file with no checker is reported as unchecked, not as passing.
- **Checked evidence.** `digest_file`, `digest_command` and `digest_many` answer a question about material the orchestrator does not read. Each answer carries line numbers and quotes, and the server looks every quote up in the source. A quote that is not there is dropped and reported. Numbers in the answer that are nowhere in the source are listed as well, and so are the values of `extract_from_file`. A made-up answer is visible without reading the source.
- **Supervised memory.** `job_feedback` records the verdict of the orchestrator; its lesson is given to the executor at its next tasks in the same project. `job_continue` sends a stopped task on with one sentence of advice, in the same conversation, so what the executor already read is not paid twice.
- **Any model.** `executor_probe` measures three things once per model: native tool calls, a JSON schema forced by the server, printed reasoning. A model without tool calling does the same delegated work through JSON replies, constrained by the schema where the server can force it. Reasoning text is stripped and never returned as an answer. Reading parts and tool results are sized to the context length the server reports.
- **Accounting.** `ledger_report` shows calls, tokens, the characters read against the characters returned, and per model the speed, the share of quotes that failed the check, the outcome of delegated tasks and the verdicts. It answers "what is worth delegating, and to which model" with data from your own use.

## Tools

| Tool | Purpose |
| --- | --- |
| `executor_status` | Server found, models, the one in use, context length, capabilities, how commands are confined |
| `executor_probe` | Measure what a model can do; the result is stored and used |
| `ask` | Text task; optional JSON schema; `samples` for an agreement score |
| `digest_file` | Question about a file (text, source, log, JSON, PDF), answer with checked quotes; long files are read in parts; `grep` narrows first; repeated questions come from a cache keyed on the content |
| `digest_command` | Runs a command of the orchestrator and returns exit code, verdict with checked quotes, last lines and the path of the full output |
| `digest_many` | Same question for many files, one line per file |
| `extract_from_file` | Structured data in a JSON schema, with the values that are not in the file listed |
| `delegate` | Bounded task with limits and checks; returns a receipt |
| `delegate_many` | Several tasks with dependencies, each with its own checks, job and rollback |
| `job_status`, `job_diff`, `job_rollback` | Follow, inspect and undo a delegated task or a batch |
| `job_continue` | Send a stopped task on with a hint, same conversation, also after a restart of the server |
| `job_feedback` | Verdict and lesson for the executor |
| `lesson_add`, `lessons` | Standing rules per project or for all projects |
| `ledger_report` | Activity, estimated savings, and quality per model |
| `ask_local_qwen`, `generate_code_with_qwen`, `check_lmstudio_status` | Names of version 1, kept for existing setups |

## A delegated task

```
delegate(
  goal="test_calc.py fails. Fix calc.py so that the test passes.",
  workspace="/path/to/project",
  verify_commands=["python3 test_calc.py"],
  allow_run=["^python3 test_calc\\.py$"])

job 20261112-224042-d6d2a6: VERIFIED  (6 steps, 0 repairs, 182.0 s, 10728 executor tokens, native tool calls)
executor: Fixed dbm_to_mw to use 10**(dbm/10) instead of 10**(dbm/20), and added a zero-division guard in swr returning 1.0 when forward is 0.
  changed calc.py  +3 -1
  syntax ok: calc.py
  check PASS  $ python3 test_calc.py  (failed before the job)
Checks passed. Read job_diff if the change is delicate, then job_feedback.
```

States of a receipt: `verified` (checks passed), `unverified` (no check given), `checks_failed`, `blocked` (the executor says why), `stuck` (it repeated the same call), `out_of_steps`, `out_of_time`, `error`. A receipt of a task that did not succeed ends with the last steps of the executor, so the orchestrator can take over or give a hint without reading a transcript.

A receipt can also carry these notes:

- `every check already passed before the job`: the checks do not discriminate, read the diff.
- `the executor changed files of the checks through a command; they were put back`.
- `changed by commands, covered by workspace snapshot (job_rollback undoes them)` (or `outside the journal` if no snapshot exists).

## Limits of the executor

- Paths are resolved (symbolic links included) and must stay inside the workspace; `.git` is never writable; `write_globs` narrows further, and `immutable` marks files or globs read-only even when `write_globs` would allow them.
- The executor runs a command only if every part of it (between `;`, `&&`, `||`, `|`, `&` and line ends) matches `allow_run` and none matches the safety list (sudo, git push/commit/reset, recursive deletes of root or home, package installs, remote shells and others, see `tandem_mcp/sandbox.py`). Command substitution is refused. A redirection must point at a file the task may write, and any file modified outside `write_globs` by a shell command is reverted from the pre-task snapshot with an error.
- Where [bubblewrap](https://github.com/containers/bubblewrap) is installed, commands of the executor and `verify_commands` run in a sandbox: the machine is read only, only the workspace is writable, `.git` stays read only, credential folders (`~/.ssh`, `~/.gnupg`, `~/.aws` and others) are hidden, secret environment variables are stripped, and there is no network. `executor_status` says which protection is active. `TANDEM_SANDBOX=require` fails closed when bubblewrap is unavailable, `TANDEM_SANDBOX=off` disables it, `TANDEM_SANDBOX_NET=1` allows the network.
- Without bubblewrap (macOS, Windows, restricted containers) only the checks on the command text apply. They are pattern checks, not a sandbox: allow only commands you would run yourself, or set `TANDEM_SANDBOX=require` to fail closed.
- `digest_command` is written by the orchestrator and run as given, with its rights. `verify_commands` run inside bubblewrap with secret env vars stripped and no network by default (`checks_network=True` allows network, `unjailed_checks=True` runs without bubblewrap when needed).
- The material the executor reads is declared as data in every prompt, and the limits above hold whatever a file tells it to do.
- The reasoning text of the model is never returned as an answer.

## Security

Read this before you point the server at a project you care about.

**What runs commands**

- `digest_command` is written by the orchestrator and run as given, with the rights of the user who started the server.
- `verify_commands` run inside bubblewrap by default (`jail=True`, `allow_net=False`, `strip_env=True`), with secret environment variables stripped and network disabled. Pass `checks_network=True` or `unjailed_checks=True` on `delegate` only when a check requires network access or cannot run inside bubblewrap.
- Commands the local model chooses in a `delegate` task run only if they match `allow_run`, pass the safety list and the text checks, and they run inside bubblewrap when it is usable (`jail=True`, `strip_env=True`).
- The orchestrator decides `allow_run`, `write_globs`, `immutable`, and `verify_commands`. Give a task the narrowest values that let it work.

**What the bubblewrap sandbox does** (`jail_command` in `tandem_mcp/sandbox.py`)

- The whole machine is bound read only (`--ro-bind / /`): files stay readable, they cannot be changed. A fresh `/tmp`, `/dev` and `/proc` are mounted.
- Only the workspace is writable. `.git` inside it is bound read only.
- These folders and files under the home folder are hidden or emptied: `.ssh`, `.gnupg`, `.aws`, `.azure`, `.kube`, `.docker`, `.config/gh`, `.config/gcloud`, `.password-store`, `.netrc`, `.git-credentials`, `.npmrc`, `.pypirc`. Other secrets that the user can read are not hidden.
- Secret environment variables matching `SECRET_ENV` (e.g. `*_API_KEY`, `*_SECRET`, `*_TOKEN`, `*_PASSWORD`) are stripped from sandboxed commands.
- No network (`--unshare-net`) unless `TANDEM_SANDBOX_NET=1` (or `checks_network=True` for `verify_commands`). The process runs in its own PID namespace, ends with the server and has a new session.

**Snapshot, rollback, and user-edit protection**

- When `allow_run` is non-empty, a pre-task snapshot (`snapshot.json` and compressed `blobs/`) captures workspace files up to 2 MB each (50 MB total). Pre-existing files larger than the cap are recorded as present without a backup so `job_rollback` leaves them untouched instead of deleting them.
- `post_state.json` records SHA-256 hashes of all changed/touched files at task end; `job_rollback` skips any file modified by the user after the job ended.
- `store.cleanup()` preserves jobs with pending un-rolled-back, un-accepted changes by default (`preserve_pending=True`).

**What it does not do**

- Non-secret environment variables of the server are passed on to sandboxed commands.
- It is not a container: no other namespaces are unshared, and a kernel or bubblewrap flaw is outside what this project can promise.
- It does not protect the workspace itself: a command may change or delete any file there that the task is allowed to write. Use `write_globs`, `immutable`, and look at `job_diff` or use `job_rollback`.

**When bubblewrap is missing**

- It is a Linux tool. On macOS, Windows or a container where it cannot create namespaces, `jail_available()` is false and the executor's commands run through a plain shell in the workspace, protected only by the checks on the command text. Those are pattern checks, not a sandbox.
- `TANDEM_SANDBOX=require` fails closed with `SandboxError` whenever bubblewrap is unavailable (`jail_available()` and `sandbox.run(..., jail=True)` never fall back to `shell=True`). `auto` (the default) falls back with a warning in `describe_jail()`, and `off` disables the sandbox.

**Hostile text**

- Files, logs and command output that the local model reads can contain instructions aimed at it. The prompts tell the model that this text is data and not to follow it (`SYSTEM` in `tandem_mcp/digest.py` and `tandem_mcp/agent.py`), which lowers the risk and does not remove it. The limits above hold whatever the model decides.
- A small local model can also simply be wrong. Read the receipt, check `job_diff` when the change matters, and close every job with `job_feedback` or `job_rollback` before you rely on it.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Install

```sh
git clone https://github.com/ALENOC/tandem-mcp
cd tandem-mcp
python3 -m venv .venv
.venv/bin/pip install .
```

MCP client configuration (stdio):

```json
{"command": "/path/to/tandem-mcp/.venv/bin/tandem-mcp"}
```

`python main.py` and `python -m tandem_mcp` start the same server. Python 3.11 or newer.

The distribution is `tandem-mcp` and the Python package is `tandem_mcp`. Version 3.0.0 imported as `tandem`, a name that the unrelated PyPI project `tandem` also installs; a client that started the server with `python -m tandem` must use `python -m tandem_mcp` (or `python main.py`, or the `tandem-mcp` command, which did not change).

Start a local model server and load a model. With no configuration Tandem tries the usual ports in this order: LM Studio (1234), Ollama (11434), llama.cpp (8080), vLLM (8000), Jan (1337), KoboldCpp (5001), text-generation-webui (5000), LocalAI (8081).

| Variable | Meaning | Default |
| --- | --- | --- |
| `TANDEM_BASE_URL` | Address of the OpenAI compatible server (`LM_STUDIO_BASE_URL` is read too) | found by itself |
| `TANDEM_MODEL` | Model to use | the loaded chat model, else the first one |
| `TANDEM_CONTEXT` | Context length in tokens, when the server does not report it | reported value, else 8192 (Ollama: 4096) |
| `TANDEM_API_KEY` | Key for a server that asks for one | `local` |
| `TANDEM_TIMEOUT` | Seconds allowed for one completion | 900 |
| `TANDEM_SANDBOX` | `auto`, `require` or `off` | `auto` |
| `TANDEM_SANDBOX_NET` | `1` lets sandboxed commands use the network | off |
| `TANDEM_HOME` | Ledger, lessons, model capabilities, cache and job folders | `~/.local/share/tandem-mcp` |

Notes on models:

- Ollama loads models with a small context unless told otherwise. Tandem reads the real value from a loaded model; raise it in Ollama (`OLLAMA_CONTEXT_LENGTH`) for delegated tasks. Reading tools work with any context, in more parts.
- A context under 8000 tokens is enough for `digest_*`, `extract_from_file` and `ask`, and tight for `delegate`.
- Models that print long reasoning are slower per answer; where the server has a switch for it, turning reasoning down helps mechanical tasks.

## Tests

```sh
.venv/bin/python tests/test_offline.py     # limits, evidence, journal, parsing: no model needed
.venv/bin/python tests/test_protocol.py    # the whole loop against a scripted server: no model needed
.venv/bin/python tests/test_live.py        # the same tools against the model you run
.venv/bin/python tests/test_live.py --text # the same model driven through JSON replies
```

`test_protocol.py` plays four kinds of model (native tool calls; JSON replies with a forced schema; no schema and printed reasoning; a server that rejects both parameters) through the same task, and checks the behaviours listed above one by one: bent tests put back, weak checks flagged, circles stopped, small contexts respected, hints, batches, discovery of each kind of server, the MCP handshake.

## Measured on real models

`tests/test_live.py` on one machine, November 2026. Twelve checks per run: answers and quotes from a file, a question the file does not answer, extraction in a schema, agreement, and a delegated bug fix with two bugs, a failing test, diff and rollback.

| Model | Server | Context | Protocol | Result |
| --- | --- | --- | --- | --- |
| Qwen 27B (IQ3_S) | LM Studio | 65536 | native tool calls | 12 of 12 |
| Qwen 27B (IQ3_S) | LM Studio | 65536 | JSON replies | 12 of 12 |
| Gemma 5B (Q4_K_M) | Ollama | 4096 | native tool calls | 12 of 12, one repair |
| Gemma 5B (Q4_K_M) | Ollama | 4096 | JSON replies, schema by prompt | reading 7 of 7; the delegated fix verified in 1 run of 3 |

The last row is the honest limit of a 5B model: in the two failed runs it wrote Python that does not parse, the syntax check and the test caught it, and the receipt said `checks_failed` with the last steps. Nothing wrong was reported as done. That is the case `job_continue` and `job_rollback` exist for.

No quote was dropped in these runs. This is a small sample: `ledger_report` gives the figure for your own model and material.

## Layout

- `tandem_mcp/server.py`: the MCP tools and the receipts.
- `tandem_mcp/engine.py`: discovery of the server, capability probe, completions, JSON with repair, accounting.
- `tandem_mcp/digest.py`: reading in parts, evidence and number checks, extraction, agreement.
- `tandem_mcp/agent.py`: the executor loop, both protocols, journal, checks, guard, hints, batches, rollback.
- `tandem_mcp/sandbox.py`: workspace and command limits, the bubblewrap sandbox.
- `tandem_mcp/store.py`: ledger, lessons, model capabilities, cache, jobs.

## License

MIT, see [LICENSE](LICENSE).
