# MCP Tools Reference

All 19 tools exposed by `tandem-mcp` over stdio MCP. Every tool output passes through `sandbox.redact_secrets()` (unless `TANDEM_REDACT=0`).

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

### `delegate`
Delegate a bounded coding task in `workspace` under a strict contract (`TANDEM_STRICT=1` default).
- **Parameters:** `goal` (required), `workspace` (required), `verify_commands` (`[]`), `write_globs` (`[]`), `allow_run` (`[]`), `immutable` (`[]`), `context` (`""`), `max_steps` (`30`), `max_repairs` (`2`), `wait_seconds` (`240`), `model` (`""`), `baseline` (`true`), `max_seconds` (`0`), `checks_network` (`false`), `unjailed_checks` (`false`), `constraints` (`[]`), `read_globs` (`[]`).
- **Contract rules (strict mode):** `goal` must have concrete targets (>= 8 words, >= 40 chars); `write_globs` must name specific files/folders (no `*` or `**/*`); `verify_commands` must include at least one command that can fail; `constraints` (<= 160 chars, one requirement each) are required for visual/UI files or text-only checks. `read_globs` optionally restricts `read_file`, `list_files`, and `search` (empty: all workspace files).

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
