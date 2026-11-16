# Configuration

All settings are controlled via environment variables read by the `tandem-mcp` server process.

## Environment Variables

| Variable | Meaning | Default |
| --- | --- | --- |
| `TANDEM_BASE_URL` | OpenAI-compatible URL (`LM_STUDIO_BASE_URL` also read) | auto-detected |
| `TANDEM_MODEL` | Default model ID | loaded chat model |
| `TANDEM_MODEL_DIGEST` | Model ID for reading/text tools (`digest_*`, `extract_from_file`, `ask`) | `TANDEM_MODEL` |
| `TANDEM_MODEL_DELEGATE` | Model ID for coding delegation (`delegate`, `delegate_many`, `job_continue`) | `TANDEM_MODEL` |
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
| `TANDEM_JOBS_KEEP` | Max persisted job folders kept on disk | `200` |
| `TANDEM_JOBS_TTL_DAYS` | Days persisted job folders are kept before pruning | `30` |
| `TANDEM_JOBS_PENDING_TTL_DAYS` | Days a job with changes and no verdict is kept | `120` |
| `TANDEM_LEDGER_KEEP_DAYS` | Days of ledger lines kept (`0`: all) | `180` |

## Backend & Model Notes

- **LM Studio:** Default endpoint `http://127.0.0.1:1234/v1`. Ensure a chat/coding model is loaded in memory (or use JIT loading if enabled). `TANDEM_DIGEST_WORKERS > 1` only speeds up `digest_*` if LM Studio's *Max concurrent predictions* is > 1.
- **Ollama:** Raise `OLLAMA_CONTEXT_LENGTH` for `delegate` tasks; reading tools (`digest_*`) work at any context length by chunking.
- **Small contexts (< 8000 tokens):** Suitable for `digest_*`, `extract_from_file`, and `ask`; tight for `delegate`.
- **Reasoning models:** Thinking blocks (`<think>...</think>`) are stripped automatically; disabling verbose thinking on the server speeds up mechanical tasks.
- **Early-stop (`TANDEM_DIGEST_MIN_NOTES > 0`):** Trades completeness for speed; do not use it for exhaustive queries such as "list every error with line numbers".
