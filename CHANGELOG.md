# Changelog

## 3.8.0

### Quality floor for delegated work
- `tandem:ui_test {json}`: a declarative UI acceptance test that the orchestrator writes into `verify_commands`. Tandem runs it in headless Chromium (click, input, key, wait, expect moving or static, exists, text, js, color share). It lives in the contract, so the executor cannot edit it; each failed step goes back to the executor with its observed value and is repaired locally. Receipts for the orchestrator show it as `tandem:ui_test (N steps)`.
- Strict contracts refuse a task that writes an `.html` page when its checks only parse or lint the code.
- Built-in web check: Pause followed by Reset must bring back the initial running state (unless a constraint says Reset keeps the pause), and a dark or neon page fails when more than 5% of the central canvas is near-white. The Play button is now found when its label starts with a symbol (`▶ Play`).
- `host_runner.run_host_managed(cloud_fallback_fn=...)`: when the local result still does not verify after the review, the cloud does the work itself. After a review, the host now waits for the continued job before deciding.
- A failure receipt after a `job_continue` hint tells the orchestrator to stop sending the job on and do the work itself.

### Routing
- `auto_route` estimates the local success rate of a task family (`web`, `python`, `other`) from finished jobs and routes direct when it is below `TANDEM_MIN_LOCAL_SUCCESS` (default `0.6`, used after 3 jobs).
- The lean guide asks for exact colors and the effect of every control in UI contracts.

### Fixes
- `write_file` refuses the context placeholder of an earlier write (`[compacted persisted write_file: ...]`) as file content. The executor had copied it into a source file in 2 benchmark runs.
- The wheel now ships the browser scripts (`*.mjs`), so the web check works after `pip install`.

### Benchmarks
- 3D Portal: 3/3 delegated runs passed at 41,149 cloud tokens per success, against 74,372 direct (-44.7%). Orbital: 2/3 at 38,800 against 35,488 (+9.3%), because writing the acceptance test costs more than it saves on a small page.
- The Orbital speed check uses 2.5 s windows, so a HUD showing whole seconds is measured correctly. `reeval_release.py` reports input, output and cache-read tokens and the number of fallbacks. `run_from_prompt_pair.py --no-fallback` measures the local path alone.

## 3.7.0

### Routing and host-managed execution
- Added `auto_route` (`tandem_mcp/router.py`): classifies a request as `deterministic`, `direct_or_targeted` or `delegate_local` with no LLM call, and honors `solo locale` / `read only` constraints. `TANDEM_AUTO_POLICY` selects `first_turn` (default: act directly in turn 1) or `mandatory_route`.
- Added `tandem_mcp/host_runner.py` and `TANDEM_HOST_MANAGED=1`: one cloud planning call starts the job, a local host process waits with no cloud polling, and the cloud is woken for review only when a failure needs a decision.
- Added the lean profile receipts and `TANDEM_WAIT_SECONDS` for lean calls.

### Executor efficiency
- `TANDEM_COMPACT_WRITES=1` (default): older `write_file` bodies are replaced by a short stub in the executor context, while `messages.json` keeps the full history. On the 3D Portal task this cut local tokens by 18.1% and wall time by 21.6% (3 pairs).
- `TANDEM_COMPACT_RECEIPT=1` (default): host-managed receipts start with `VERDICT:` and carry only the evidence needed for review.

### Verification
- Added a built-in Chromium runtime and animation check for web deliverables (`tandem_mcp/web_check.py`, `tandem_mcp/_web_probe.mjs`, `TANDEM_WEB_CHECK`, `TANDEM_CHROME`). Start-paused pages are resumed through their Play/Start button before motion is measured.
- New job state `not_evaluated`: a check that cannot run because a prerequisite is missing (exit code `2`) ends the job without repair attempts and never reports `verified`.

### Benchmarks
- Behavioral evaluators for the Orbital and 3D Portal demos (`check_orbital_behavioral.mjs`, `check_portal_behavioral.mjs`) and from-prompt A/B runners (`run_from_prompt_pair.py`, `run_ab_portal.py`, `run_compaction_ab.py`).
- Fixed false negatives in the Orbital evaluator (speed label read as time, value-before-label HUDs, trails timing under load) and in the Portal Orbit check (edge-on floor). Negative controls still fail.
- Added `reeval_release.py`: every artifact is evaluated three times and the report records the evaluator SHA-256.
- `docs/BENCHMARKS.md` and the README now report only the latest runs, with direct vs Tandem previews of both demos.

### Testing
- New offline suites for routing, host runner, compaction, compact receipts, `not_evaluated` and the web check. Updated outdated assertions in `tests/test_protocol.py`, `tests/test_compaction.py` and `tests/test_web_check.py`.

## 3.6.1

### Testing
- Mocked `engine.default_model` in the offline `extract_from_file` multi-chunk conflict test so `tests/test_offline.py` runs deterministically without a live LLM server in CI.

## 3.6.0

### Security & Permissions
- Added optional `read_globs` parameter to `Workspace`, `delegate`, `delegate_many`, and `BatchTaskSpec` to restrict `read_file`, `list_files`, and `search` via normalized glob matching with symlink resolution and traversal checks. Documented that `allow_run` shell commands still run against the mounted workspace.
- Enforced mandatory Bubblewrap verification in `.github/workflows/tests.yml` (`bwrap --version`, `jail_available()`, and `TANDEM_REQUIRE_JAIL=1 TANDEM_SANDBOX=secure`) and distinguished passed vs skipped counts in `tests/test_offline.py`.

### Reliability & Structured Extraction
- Fixed `rollback()` batch aggregation in `tandem_mcp/agent.py` so a batch is marked `rolled_back` only when all relevant child jobs succeed; child `partial_rollback`, running children, exceptions, missing journals, or interruptions mark the batch `partial_rollback`.
- Added deterministic multi-chunk conflict detection in `tandem_mcp/digest.py` (`_merge_dicts`, `_merge_extractions_with_conflicts`, `extract_with_conflicts`) and surfaced `CONFLICTS:` metadata in `extract_from_file` without breaking JSON Schema validity.

### Documentation & Benchmarks
- Added a mobile-friendly Mermaid delegation sequence diagram in `docs/ARCHITECTURE.md`.
- Updated `docs/TOOLS.md`, `docs/SECURITY_MODEL.md`, `docs/CONFIGURATION.md`, and `docs/BENCHMARKS.md` (with live LM Studio `qwen3.8-27b@iq3_s` phase profiling).

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
