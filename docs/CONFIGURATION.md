# Configuration

All settings are controlled via environment variables read by the `tandem-mcp` server process.

## Environment Variables

| Variable | Meaning | Default |
| --- | --- | --- |
| `TANDEM_BASE_URL` | OpenAI-compatible URL (`LM_STUDIO_BASE_URL` also read) | auto-detected |
| `TANDEM_MODEL` | Default model ID | loaded chat model |
| `TANDEM_MODEL_DIGEST` | Model ID for reading/text tools (`digest_*`, `extract_from_file`, `ask`) | `TANDEM_MODEL` |
| `TANDEM_MODEL_DELEGATE` | Model ID for coding delegation (`delegate`, `delegate_many`, `job_continue`) | `TANDEM_MODEL` |
| `TANDEM_MODEL_VISION` | Optional local VLM model ID used for stateless screenshot visual review (works even when the coding model is text-only) | auto (loaded VLM if any) |
| `TANDEM_CONTEXT` | Context length fallback when server omits it | `8192` (Ollama: `4096`) |
| `TANDEM_API_KEY` | API key sent only to the selected/configured server | `local` |
| `TANDEM_TIMEOUT` | Per-completion timeout (seconds) | `900` |
| `TANDEM_LLM_RETRIES` | Extra retry attempts on transient errors (backoff 1/2/4 s, cap 30 s, jitter) | `3` |
| `TANDEM_JOB_AUTORESUME` | Bounded 15 s auto-resume waits per delegated job on transient errors | `2` |
| `TANDEM_SANDBOX` | Sandbox profile: `secure` (`require`), `compatible` (`auto`), or `trusted` (`off`) | `secure` on Linux, `compatible` elsewhere |
| `TANDEM_REQUIRE_JAIL` | `1` fails offline tests if Bubblewrap jail is unavailable | `0` |
| `TANDEM_SANDBOX_NET` | `1` allows network inside Bubblewrap | off |
| `TANDEM_ALLOW_OUTBOUND_SYMLINKS` | `1` allows unjailed `run` in workspaces with outbound symlinks | off |
| `TANDEM_STRICT` | `0` relaxes the strict delegation contract | `1` |
| `TANDEM_REQUIRE_FULL_BACKUP` | `1` refuses `run` and `job_feedback(accepted=True)` when files are unbacked | `0` |
| `TANDEM_RUN_OUTPUT_CAP` | Bytes of command output kept in RAM (head+tail) | `2097152` |
| `TANDEM_RUN_TIMEOUT` | Default timeout for executor `run` commands (seconds) | `180` |
| `TANDEM_LOG_CAP` | Max bytes streamed to `output.txt` by `digest_command` | `67108864` |
| `TANDEM_REDACT` | `0` disables secret redaction on tool outputs | `1` |
| `TANDEM_SNAPSHOT_FILE_CAP` | Max pre-task file size backed up by `take_snapshot` in bytes (`0` disables) | `8388608` |
| `TANDEM_SNAPSHOT_TOTAL_CAP` | Max total pre-task snapshot size per job in bytes (`0` disables) | `268435456` |
| `TANDEM_HOME` | Ledger, lessons, caps, cache, and jobs folder | `~/.local/share/tandem-mcp` |
| `TANDEM_MAX_PARTS` | Most parts one `digest_*` answer may read | `60` |
| `TANDEM_DIGEST_WORKERS` | Concurrent map calls per wave in `digest_*` (`1` = sequential) | `1` |
| `TANDEM_DIGEST_MIN_NOTES` | Early-stop map threshold in `digest_*` (`0` = full map) | `0` |
| `TANDEM_USE_RG` | `1` accelerates executor `search` with `rg --json` | `0` |
| `TANDEM_DIGEST_TIMEOUT` | Time budget of one `digest_*` answer (seconds) | `150` |
| `TANDEM_CACHE_KEEP` | Most cached digest answers kept on disk | `400` |
| `TANDEM_CACHE_TTL_DAYS` | Days a cached digest answer is kept | `14` |
| `TANDEM_JOBS_KEEP` | Max persisted job folders kept on disk | `200` |
| `TANDEM_JOBS_TTL_DAYS` | Days persisted job folders are kept before pruning | `30` |
| `TANDEM_JOBS_PENDING_TTL_DAYS` | Days a job with changes and no verdict is kept | `120` |
| `TANDEM_LEDGER_KEEP_DAYS` | Days of ledger lines kept (`0`: all) | `180` |
| `TANDEM_PROFILE` | `lean`: fewer tools, short schemas, compact receipts. `autonomous`: 4 tools, `delegate` blocks until the local model has met every check, one-line receipts | full profile |
| `TANDEM_JOB_SECONDS` | Time budget of an autonomous job: the local model repairs until every check passes or this runs out | `3600` |
| `TANDEM_SLOW_CHECK_S` | A check that passes but runs longer than this, and three times longer than before the work, goes back to the executor once with the output line after its longest silence; `0` turns it off | `30` |
| `TANDEM_MAX_REPAIRS` | Most repair rounds of an autonomous job | `20` |
| `TANDEM_MAX_STEPS` | Most executor steps of an autonomous job | `160` |
| `TANDEM_PROGRESS_SECONDS` | Interval of the MCP progress notifications sent while an autonomous job runs, so the client does not abort a silent tool | `30` |
| `TANDEM_AUTO_POLICY` | `first_turn`: act directly in turn 1, `auto_route` optional. `mandatory_route`: call `auto_route` first | `first_turn` |
| `TANDEM_HOST_MANAGED` | `1`: `delegate` returns the job ID at once and a local host process waits, with no cloud polling | off |
| `TANDEM_HOST_TIMEOUT` | Local timeout of the host-managed runner (`host_runner.py --timeout`, seconds) | `1800` |
| `TANDEM_WAIT_SECONDS` | Default wait of a lean `delegate` call (seconds, capped at `1500`) | `150` |
| `TANDEM_COMPACT_WRITES` | `1`: a `write_file` body is replaced by a short stub in the executor context once the file changes again or the context passes 60% of its budget, and stays replaced (the full history stays in `messages.json`) | `1` |
| `TANDEM_REPLY_TOKENS` | Most tokens of one executor reply: a whole file plus the reasoning a thinking model writes first. A reply cut off by this budget is asked again once with a larger one, within the context | `12000` |
| `TANDEM_COMPACT_RECEIPT` | `1`: host-managed receipts lead with `VERDICT:` and keep only the evidence needed for review | `1` |
| `TANDEM_WEB_CHECK` | `1`: run the built-in Chromium runtime and animation check on web deliverables | `1` |
| `TANDEM_WEB_MIN_FPS` | Frames per second an animated page must reach in the web check (headless Chromium, 1280x800). A slower page goes back to the executor with the measured cause, at most twice and not in the last quarter of the job time; after that the frame rate is only reported in the receipt. `0` turns the check off | `40` |
| `TANDEM_VISUAL_REVIEW` | Local VLM visual review on captured 1280x800 web screenshots (`auto`: runs when `TANDEM_MODEL_VISION` is set or a VLM is loaded; `on`: force; `off`: disable) | `auto` |
| `TANDEM_MAX_VISUAL_REPAIRS` | Most local visual-review repair rounds per job (never in the last quarter of the job time) | `2` |
| `TANDEM_RECEIPT_SCREENSHOT` | `1`: attach the captured 1280x800 web screenshot as MCP `ImageContent` on finished job receipts so the cloud orchestrator can inspect it and send one `job_continue(hint)` if needed | `1` |
| `TANDEM_CHROME` | Path to the Chromium or Chrome binary used by the web check | auto-detected |
| `TANDEM_MIN_LOCAL_SUCCESS` | Least estimated local success rate of a task family for `auto_route` to delegate a write (used after 3 finished jobs) | `0.6` |

## Backend & Model Notes

- **LM Studio:** Default endpoint `http://127.0.0.1:1234/v1`. Ensure a chat/coding model is loaded in memory (or use JIT loading if enabled). `TANDEM_DIGEST_WORKERS > 1` only speeds up `digest_*` if LM Studio's *Max concurrent predictions* is > 1.
- **Ollama:** Raise `OLLAMA_CONTEXT_LENGTH` for `delegate` tasks; reading tools (`digest_*`) work at any context length by chunking.
- **Small contexts (< 8000 tokens):** Suitable for `digest_*`, `extract_from_file`, and `ask`; tight for `delegate`.
- **Reasoning models:** Thinking blocks (`<think>...</think>`) are stripped automatically; disabling verbose thinking on the server speeds up mechanical tasks.
- **Early-stop (`TANDEM_DIGEST_MIN_NOTES > 0`):** Trades completeness for speed; do not use it for exhaustive queries such as "list every error with line numbers".
