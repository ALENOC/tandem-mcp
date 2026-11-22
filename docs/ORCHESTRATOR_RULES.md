# Tandem MCP: orchestrator rules (cloud-token saving)

With Claude Code, use `TANDEM_PROFILE=autonomous`: its rules are built into the server's instructions and
`delegate` blocks until the local work is done, so no rules file is needed. See [Benchmarks](BENCHMARKS.md).

For other clients, copy this block into the client's rules file (`AGENTS.md` for Codex, `GEMINI.md` for
Gemini CLI and Antigravity) and run Tandem with `TANDEM_PROFILE=lean`. Every rule removes a step that costs
cloud tokens.

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
   If it fails again after the hint, do the work yourself (roll back first if the files got worse).
7. Never debug Tandem itself (processes, job folders, ledgers): report the error and stop.
8. Do it yourself when the whole task is smaller than one delegate call: a 1-line edit,
   or a file you have already read.
9. Web page: add a `tandem:ui_test` check that clicks every control and asserts its effect
   (`expect` moving/static, `text`, `color`), with exact hex colors in the constraints. The
   executor repairs against it locally, so a passed receipt needs no render from you.
```

## Why each rule exists

Each rule removes a step that was seen to cost cloud tokens without changing the result:

| Wasted step | Rule |
| --- | --- |
| Reading every source file before `delegate` | 1, 3 |
| Reading large tool schemas on every run | `TANDEM_PROFILE=lean` or `autonomous` |
| Checking processes, job folders and ledgers | 7 |
| Re-reading files and re-running tests after a verified job | 4 |
| Deleting the output and delegating a second time | 5 |
| Polling `job_status`, then opening evidence and feedback tools | 4, 5 + auto-accept |
| Editing files blind after a failed job, which broke a working page | 6 |
