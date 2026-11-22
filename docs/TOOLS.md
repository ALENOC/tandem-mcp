# MCP Tools Reference

All 20 tools exposed by `tandem-mcp` over stdio MCP. Every tool output passes through `sandbox.redact_secrets()` (unless `TANDEM_REDACT=0`).

## Autonomous profile (`TANDEM_PROFILE=autonomous`)

Only four tools are exposed, for an orchestrator that should spend as few tokens as possible:

- `delegate(goal, workspace, write_globs, verify_commands, constraints, allow_run, context)`: same strict contract as below. The call blocks while the local model writes, runs the checks and repairs (up to `TANDEM_MAX_REPAIRS` rounds within `TANDEM_JOB_SECONDS`), with no cloud call. It returns `job ...: ACCEPTED. N checks and M constraints verified locally (...). Changed: ... Nothing else to do.` or `FAILED (state)` followed only by the failing checks (for a `tandem:ui_test`, only its failing steps).
- `job_continue(job_id, hint)`: sends a failed job on locally with a one-line hint, and blocks the same way.
- `job_status(job_id)`: waits for a job that was still running.
- `job_rollback(job_id)`: undoes every change of a job.

A job is accepted on the orchestrator's behalf when it verified, every constraint has cited evidence, and no changed file has a syntax error. The orchestrator guide asks it to delegate new code and changes of more than about 30 lines, to answer the user after `ACCEPTED` without reading the files, and to do smaller edits itself.

## Read & Analyze

### `ask`
Text generation for drafting, translation, boilerplate, or classification.
- **Parameters:** `prompt` (required), `system_prompt` (`""`), `json_schema` (`""`), `samples` (`1`..`5`), `max_tokens` (`3000`), `model` (`""`).
- **Notes:** Uses `TANDEM_MODEL_DIGEST` when `model` is omitted. With `samples > 1`, reports agreement score.

### `digest_file`
Q&A on a file (text, source, log, JSON, PDF via `pdftotext`) with lexical quote verification.
- **Parameters:** `path` (required), `question` (required), `grep` (`""`), `max_words` (`120`), `model` (`""`).
- **Output:** Concise answer, verified quotes (`quote_found`, `claim_supported`), ungrounded numbers (`loose`), and read coverage.

### `digest_many`
Ask the same question across many files matching a glob.
- **Parameters:** `root` (required), `glob` (required), `question` (required), `max_files` (`25`), `max_words_each` (`40`).
- **Output:** One line per file with a verified quote or `[UNVERIFIED]`.

### `extract_from_file`
Structured JSON extraction from a file against a JSON schema string.
- **Parameters:** `path` (required), `json_schema` (required), `instructions` (required), `grep` (`""`).
- **Output:** Compact JSON matching `json_schema` (multi-chunk extractions are merged deterministically and validated; raises an error on schema mismatch), followed by `CONFLICTS:` metadata if different chunks disagree on a scalar/type value, and `NOTE:` if extracted values were not found verbatim in the file.

## Delegate & Execute

### `auto_route`
Classify a request before acting, with no LLM call. Returns JSON with a `route`: `deterministic` (exact parsing or counting with scripts), `direct_or_targeted` (the cloud model acts directly, or reads and edits a few lines) or `delegate_local` (local executor). Honors explicit `solo locale` / `local only` and `read only` constraints.
- **Parameters:** `request` (required), `workspace` (required), `budget_seconds` (`null`).
- **When it is called:** only when `TANDEM_AUTO_POLICY=mandatory_route`. With the default `first_turn` policy the orchestrator acts directly in turn 1 and may skip it.
- **Local success rate:** before choosing `delegate_local` for a write, the router counts finished jobs of the same family (`web`, `python`, `other`) in the job store. With at least 3 of them and an estimated success rate `(verified + 1) / (n + 2)` below `TANDEM_MIN_LOCAL_SUCCESS` (default `0.6`), it routes direct: a failed delegation costs the plan and then the direct work, so the break-even is about 0.5. `solo locale` is always honoured.

### `delegate`
Delegate a bounded coding task in `workspace` under a strict contract (`TANDEM_STRICT=1` default).
- **Parameters:** `goal` (required), `workspace` (required), `verify_commands` (`[]`), `write_globs` (`[]`), `allow_run` (`[]`), `immutable` (`[]`), `context` (`""`), `max_steps` (`30`), `max_repairs` (`2`), `wait_seconds` (`240`), `model` (`""`), `baseline` (`true`), `max_seconds` (`0`), `checks_network` (`false`), `unjailed_checks` (`false`), `constraints` (`[]`), `read_globs` (`[]`).
- **Contract rules (strict mode):** `goal` must have concrete targets (>= 8 words, >= 40 chars); `write_globs` must name specific files/folders (no `*` or `**/*`); `verify_commands` must include at least one command that can fail; `constraints` (<= 160 chars, one requirement each) are required for visual/UI files or text-only checks. `read_globs` optionally restricts `read_file`, `list_files`, and `search` (empty: all workspace files).
- **Web pages:** a task that writes `.html` is refused when its checks only parse or lint the code (`node --check`, `py_compile`, `eslint`, ...). Add a behavioural check, usually a `tandem:ui_test` (below), or a script that runs the page.

#### `tandem:ui_test`: UI acceptance tests in the contract
A verify command of the form `tandem:ui_test {json}` is not run in the shell: Tandem runs the JSON scenario in headless Chromium. The scenario lives in the contract, so the executor cannot edit or weaken it, and the full scenario is shown to the executor while receipts for the orchestrator show only `tandem:ui_test (N steps)`.

```json
{"steps": [
  {"expect": "moving"},
  {"click": "text:^pause"}, {"expect": "static"},
  {"click": "#reset"}, {"expect": "moving"},
  {"input": "#speed", "value": "3"}, {"text": "#speedVal", "match": "^3\\.0x$"},
  {"color": "#0b1020", "min": 0.3}, {"color": "#ffffff", "max": 0.05}
]}
```

| Step | Meaning |
| --- | --- |
| `click` | CSS selector, or `text:<regex>` for a visible control by its label |
| `input` + `value` | set a value and fire `input` and `change` |
| `key` | press a key (`Space`, `ArrowLeft`, ...) |
| `wait` | milliseconds |
| `expect` | `moving` or `static`: the canvas (or the whole view) changes or not over 0.8 s; `region` limits it to part of the view |
| `exists` | an element is present |
| `text` + `match` | visible text matches a regex |
| `js` | a JavaScript expression is truthy |
| `color` + `min`/`max` | share of screenshot pixels near a color (`tol` 48, optional `region` `[x0, y0, x1, y1]` as fractions) |
| `snapshot` | remember the view under a name (optional `region`) |
| `differs` + `min`/`max` | share of pixels changed since the named snapshot (`tol` 30): checks that an action has a visible effect |

Top-level keys: `entry` (default `index.html`), `wait_ms` (default `1000`), `viewport` `[w, h]`, `allow_errors`. JavaScript errors fail the test unless `allow_errors` is `true`. A scenario must assert something, not only act. A failed step is reported to the executor with its observed value, so it is repaired locally at no cloud cost.

#### Built-in web check
Every web deliverable also gets `tandem:web_check`: startup with 0 JavaScript errors and, for animations, a moving canvas. Two generic rules are added:
- **Reset restores the initial state:** when the page animates at load and Pause stops it, Pause followed by Reset must bring the motion back. A constraint saying that Reset keeps the paused state turns this rule off.
- **No overexposure on dark themes:** when the goal or constraints ask for a dark, neon, night or space look, more than 5% near-white pixels in the central part of the canvas fails the check.

### `delegate_many`
Run a dependency-ordered DAG of delegated tasks (`BatchTaskSpec` items).
- **Parameters:** `tasks` (required, list of `BatchTaskSpec`: `name`, `goal`, `write_globs`, `read_globs`, `verify_commands`, `after`, `context`, `immutable`, `checks_network`, `unjailed_checks`, `constraints`), `workspace` (required), `allow_run` (`[]`), `immutable` (`[]`), `context` (`""`), `workers` (`1`), `max_steps` (`30`), `max_repairs` (`2`), `wait_seconds` (`240`), `model` (`""`), `checks_network` (`false`), `unjailed_checks` (`false`), `read_globs` (`[]`).

### `digest_command`
Run an orchestrator command on the host with user rights and get a summarized verdict.
- **Parameters:** `command` (required), `cwd` (required), `question` (`""`), `max_words` (`120`), `timeout` (`600`).
- **Output:** Exit code, executor verdict, last lines, and `output.txt` path (streamed up to `TANDEM_LOG_CAP`).
- **Security note:** Runs with the host user's permissions (not sandboxed).

## Inspect & Control

### `job_status`
Poll a running or finished job/batch and return its current receipt.
- **Parameters:** `job_id` (required), `wait_seconds` (`120`).

### `job_stop`
Request a clean stop for a running job or batch at its next safe point (in-flight LLM calls finish up to `TANDEM_TIMEOUT`).
- **Parameters:** `job_id` (required), `wait_seconds` (`10`).

### `job_evidence`
Show the source lines cited by the executor for each contract constraint, with surrounding context.
- **Parameters:** `job_id` (required), `context` (`1`, max `8`).

### `job_diff`
Show the unified diff of changes made by a delegated job.
- **Parameters:** `job_id` (required), `path` (`""`), `max_lines` (`200`).

### `job_rollback`
Restore files changed by a job (or batch, newest first), skipping files modified later by the user.
- **Parameters:** `job_id` (required).
- **States:** Sets `rolled_back`, or `partial_rollback` if any file could not be restored.

### `job_continue`
Resume a stopped/failed job in the same conversation with a hint from the orchestrator.
- **Parameters:** `job_id` (required), `hint` (required), `extra_steps` (`15`), `wait_seconds` (`240`).

### `job_feedback`
Record acceptance verdict and optional standing lesson.
- **Parameters:** `job_id` (required), `accepted` (required), `lesson` (`""`), `constraints_verified` (`false`).
- **Gates:** Requires `job_evidence` or `job_diff` inspection before `accepted=True` on non-trivial/unverified/constrained jobs, `constraints_verified=True` when constraints exist, and `job_diff` when `backup_status` is `partially_backed`/`unbacked` (or refuses acceptance if `TANDEM_REQUIRE_FULL_BACKUP=1`).

## Models, Monitoring & Knowledge

### `executor_status`
Report active local server, models, role routing, probed capabilities, and sandbox status.

### `executor_probe`
Measure a model's native tool calling, forced JSON schema, reasoning stripping, and speed (`tokens/s`).
- **Parameters:** `model` (`""`), `force` (`false`).

### `ledger_report`
Summarize tool calls, executor tokens, estimated cloud input tokens saved, transient retries, quote drop rate, and acceptance stats.
- **Parameters:** `days` (`30.0`).

### `lesson_add` / `lessons`
Add, list, or remove standing rules for a project scope (or `*` globally).
- **`lesson_add`:** `project_path` (required), `text` (required).
- **`lessons`:** `project_path` (required), `remove_containing` (`""`).

## Job States

`running`, `verified`, `unverified`, `checks_failed`, `blocked`, `stuck`, `out_of_steps`, `out_of_time`, `stopped`, `not_evaluated`, `error`, `rolled_back`, `partial_rollback`, `partial` (batch).

`not_evaluated` means a check could not run because a prerequisite was missing (for example no Chromium for the web check, exit code `2`). The job ends without repair attempts and is never reported as `verified`.
