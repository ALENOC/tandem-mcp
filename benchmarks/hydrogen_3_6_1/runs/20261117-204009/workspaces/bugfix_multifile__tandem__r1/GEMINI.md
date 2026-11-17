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
