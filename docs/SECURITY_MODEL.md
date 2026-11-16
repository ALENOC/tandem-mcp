# Security Model

This document describes Tandem MCP's threat model, OS-level isolation, application-level contract checks, and explicit limitations. To report a vulnerability, see [SECURITY.md](../SECURITY.md).

## Sandbox Profiles (`TANDEM_SANDBOX`)

| Profile | Aliases | Behavior when Bubblewrap is unavailable |
| --- | --- | --- |
| `secure` | `require` | **Fail-closed:** raises `SandboxError` on `jail_available()` and `run(..., jail=True)` |
| `compatible` | `auto` | Falls back to command-text checks + outbound symlink refusal with a warning in `executor_status` |
| `trusted` | `off` | Disables Bubblewrap; relies on command-text checks + outbound symlink refusal |

- **Default:** `secure` on Linux, `compatible` on non-Linux systems (macOS, Windows). Unknown profile values fail closed with `SandboxError`.

## OS-Level Isolation (Bubblewrap on Linux)

When `bubblewrap` (`bwrap`) is active, both executor `run` commands and `verify_commands` execute inside isolated namespaces:

- **Allowlisted system directories:** Read-only binds for `/usr`, `/bin`, `/sbin`, `/lib`, `/lib64`, `/lib32`, `/etc`, `/opt`, `/nix` (preserving symlinks) and the active Python runtime (`sys.base_prefix`, `sys.prefix`, and `sys.executable` symlink targets).
- **Hidden host `$HOME`, `/tmp`, `/run`:** Mounted as fresh empty `tmpfs` instances so host documents, SSH keys, cloud configs, other repositories, and host Unix sockets (Docker socket, D-Bus, key agents) are not visible.
- **Writable workspace:** Only the delegated `workspace` is bound writable; `SKIP_DIRS` (`.git`, `node_modules`, `.venv`, `build`, `dist`, ...) are bound read-only.
- **Namespace & environment isolation:** `--unshare-net` (unless `checks_network=True` or `TANDEM_SANDBOX_NET=1`), `--unshare-pid`, `--unshare-ipc`, `--die-with-parent`, `--new-session`, and `SECRET_ENV` variables stripped.

## Unjailed Mode & Outbound Symlink Refusal

When running without Bubblewrap (`compatible`/`auto` off-Linux, or `unjailed_checks=True`), OS-level filesystem isolation is **not** guaranteed. Tandem enforces:

- **Outbound symlink refusal:** `sandbox.run()` refuses workspaces containing symlinks (including relative or dangling ones, excluding `SKIP_DIRS`) whose resolved target lies outside the workspace (override with `TANDEM_ALLOW_OUTBOUND_SYMLINKS=1`).
- **Command text parser (`split_command` / `allow_run` / `DENY`):** Every pipeline/chain part must match `allow_run` (anchor with `^`, e.g. `^pytest\b`), must not match `DENY` or `DENY_COMMANDS` (even behind `env`, `xargs`, `sh -c`), and refuses command substitution (`$(...)`, backticks, `<(...)`, `>(...)`), `$'...'`/`$"..."` quoting, and heredocs/herestrings (`<<`, `<<<`). Redirection targets must be writable inside `write_globs`.

## Privileged Commands (`digest_command`)

`digest_command` executes the orchestrator's own command directly on the host with the user's rights (not sandboxed, and exempt from `outbound_symlinks`). Output is streamed to `output.txt` up to `TANDEM_LOG_CAP` (default 64 MiB) while RAM usage stays bounded by `TANDEM_RUN_OUTPUT_CAP` (default 2 MiB head+tail).

## Contract Enforcement, Rollback & Redaction

- **SHA-256 `stamp()`:** Hashes workspace files before and after executor `run` (using a `ctime_ns` fast-path on POSIX to prevent `mtime` spoofing). Files modified outside `write_globs` or owned by another parallel task are reverted immediately.
- **Protected test files:** Files named in `verify_commands` and test folders are read-only (`guard`) and restored if modified.
- **Workspaces refused:** `/`, `$HOME` and its parents, system directories (`/etc`, `/usr`, `/tmp` itself), and credential folders (`~/.ssh`, ...).
- **Backup & rollback:** `journal_bin.json` + `snapshot.json` back up original bytes (up to `TANDEM_SNAPSHOT_FILE_CAP` = 8 MiB/file, `TANDEM_SNAPSHOT_TOTAL_CAP` = 256 MiB/job; `0` disables backup). Aggregate disk usage can reach ~`TANDEM_JOBS_KEEP` x `TANDEM_SNAPSHOT_TOTAL_CAP` before retention pruning (`TANDEM_JOBS_TTL_DAYS` = 30, `TANDEM_JOBS_PENDING_TTL_DAYS` = 120). Set `TANDEM_REQUIRE_FULL_BACKUP=1` to refuse `run` and `job_feedback(accepted=True)` when unbacked files exist. Incomplete rollbacks set state to `partial_rollback`, and `post_state.json` prevents overwriting later user edits.
- **Secret redaction & API keys:** Tool outputs pass through `redact_secrets()` (`TANDEM_REDACT=1` default) masking private key blocks, API tokens, Bearer tokens, and `SECRET_ENV` assignments. `TANDEM_API_KEY` is sent only to the configured/selected server, never during port discovery. Data under `TANDEM_HOME` is `0700`.
- **Retries & timeouts:** `engine.chat` retries connection errors and `408`/`409`/`429`/`5xx` with exponential backoff (`OpenAI(..., max_retries=0)`), while `APITimeoutError` is not retried.
- **Hostile text:** File contents and command outputs are marked as data in prompts; always review receipts and diffs before accepting.
