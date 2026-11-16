# Comparison With Alternatives

Compared in November 2026 from each project's public README (not from running them). `"Not verified"` means the feature could not be confirmed from the available README at that date.

| Feature | Tandem MCP | houtini-lm | local-vibes | Atomic Agent Fusion |
| --- | --- | --- | --- | --- |
| Local file-editing tool loop | yes | no | yes | yes |
| Server-run checks + repair loop | yes | no | no | `verify.run` (loop not verified) |
| Baseline check (flags pre-passing) | **yes** | no | no | no |
| Read-only test protection + restore | **yes** | no | no | no |
| Per-task journal, diff & rollback (no git) | **yes** | no | diff stat only | opt-in worktrees |
| Quotes & numbers checked against source | **yes** | no | no | no |
| Agreement score (`samples`) | **yes** | no | no | no |
| Orchestrator feedback -> project lessons | **yes** | no | no | episode reflection |
| Resume stopped task with hint | **yes** | no | no | partly |
| Non-tool-calling models supported | yes (JSON) | n/a | no | yes (grammar) |
| Model capability probing | yes (`probe`) | per-family | no | Not verified |
| Pipeline-aware command allow list | **yes** | n/a | no | approval ladder |
| OS sandbox (bubblewrap) | yes | n/a | path only | env secret strip |
| Parallel tasks with file claims | yes | no | separate dirs | yes (waves) |
| Token savings & quality accounting | yes | yes | no | per-worker cost |
