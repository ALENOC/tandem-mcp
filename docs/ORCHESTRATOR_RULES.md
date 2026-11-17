# Tandem MCP: orchestrator rules (cloud-token saving)

Copy this block into your client's rules file (`GEMINI.md` / `AGENTS.md` for Antigravity and Gemini CLI,
`CLAUDE.md` for Claude Code, `AGENTS.md` for Codex) and run Tandem with `TANDEM_PROFILE=lean`.
Every rule removes a step that was measured to cost cloud tokens in the Hydrogen benchmark.

```markdown
## Using Tandem MCP

Tandem's local model is free; your context is not. Keep your own reading and turns to a minimum.

1. Do not open a file you are about to hand to Tandem. Pass its path; the executor reads it.
2. Reading: digest_file with `grep` when you know a keyword; digest_many for many files;
   digest_command for logs and command output; extract_from_file for structured data.
3. Coding: one `delegate` call. Name write_globs, give verify_commands that fail until the
   work is done, and list atomic constraints. Do not explore the sources first.
4. A receipt that says ACCEPTED is final. Do not re-read the files, re-run the checks,
   open the diff, or call status/ledger tools afterwards.
5. If the receipt says running, call job_status once more (it waits). Never resubmit a job
   and never delete its output to start over.
6. After a FAIL receipt, use job_continue with a one-line hint; use job_rollback to undo.
7. Never debug Tandem itself (processes, job folders, ledgers): report the error and stop.
8. Do it yourself when the whole task is smaller than one delegate call: a 1-line edit,
   or a file you have already read.
```

## Why each rule exists

Measured in run `20261117-190714` (Gemini 4 Hydrogen + qwen3.8-27b, default profile):

| Wasted step | Where it happened | Rule |
| --- | --- | --- |
| Read all 5 source files before `delegate` | multi-file bugfix | 1, 3 |
| Read 7 tool-schema files (`delegate.json` alone is 5 KB) | every tandem run | `TANDEM_PROFILE=lean` |
| `executor_status`, `ledger_report` x2, `ps aux`, listing job folders | multi-file bugfix | 7 |
| Re-read `parser.py`/`validator.py` and re-ran tests after VERIFIED | multi-file bugfix | 4 |
| Deleted the output and delegated a second time | rate limiter | 5 |
| 3 x `job_status`, then `job_evidence`, then `job_feedback` | rate limiter | 4, 5 + auto-accept |
