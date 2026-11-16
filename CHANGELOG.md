# Changelog

## 3.5.2

### Documentation
- Redesigned `README.md` for clarity, scannability, and mobile/GitHub UX (vertical Mermaid architecture diagram, 4-step flow, concise Quick Start with LM Studio example, grouped tool overview, and clear compatibility-mode security notice).
- Restructured detailed documentation into `docs/`: `GETTING_STARTED.md`, `ARCHITECTURE.md`, `TOOLS.md`, `CONFIGURATION.md`, `SECURITY_MODEL.md`, `BENCHMARKS.md`, and `COMPARISON.md`.
- Updated `docs/tandem-mcp-architecture.pdf` (English) and `docs/tandem-mcp-architettura.pdf` (Italian) to reflect the 3.5.x architecture.

## 3.5.1

### Security fixes
- Default `TANDEM_SANDBOX` to `secure` on Linux (fail-closed when Bubblewrap is unavailable) and `compatible` on non-Linux hosts; unknown profiles raise `SandboxError`.
- Replaced `--ro-bind / /` in Bubblewrap with an allowlist of system directories, empty tmpfs over `/tmp`, `/run`, and host `$HOME`, and read-only binds for the active Python runtime (`sys.base_prefix`, `sys.prefix`, and `sys.executable` symlink targets).
- Fixed `glob_match` and `_glob_to_re` prefix stripping (`_strip_rel_prefix`) so dotfiles (`.env`, `.github/...`) are not stripped to `env` or `github/...`, and rejected `..` traversal and absolute paths.

### Reliability and rollback
- Added `TANDEM_REQUIRE_FULL_BACKUP=1` to refuse `run` commands when workspace files exceed snapshot caps and block `job_feedback(accepted=True)` when changes are unbacked.
- Required `job_diff` inspection in `job_feedback(accepted=True)` whenever `backup_status` is `partially_backed` or `unbacked`.
- Marked incomplete rollbacks with state `partial_rollback` instead of `rolled_back`.
- Streamed `digest_command` output directly to `output.txt` on disk up to `TANDEM_LOG_CAP` (default 64 MiB) while keeping RAM bounded by `TANDEM_RUN_OUTPUT_CAP`.

### Structured extraction
- Merged multi-chunk `digest.extract()` results deterministically by schema (objects, nested objects, arrays, first non-null scalar) and raised `ExecutorError` if the merged result fails schema validation.

### Testing and CI
- Installed `bubblewrap` and added `scripts/verify_traps.py` to `.github/workflows/tests.yml`.
- Verified end-to-end against live LM Studio (`qwen3.8-27b@iq3_s`).
