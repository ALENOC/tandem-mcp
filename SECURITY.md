# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub private vulnerability reporting: open the **Security** tab of this repository and choose **Report a vulnerability**. Include the version (`pyproject.toml`), the operating system, whether bubblewrap was in use (`TANDEM_SANDBOX`), and the steps that reproduce the problem.

I will answer as soon as I can; this is a one person project and there is no fixed response time.

## Supported versions

Only the latest release on the `main` branch receives fixes.

## Scope

The threat model and the limits of the sandbox are described in the Security section of the [README](README.md). A report is most useful when it shows a way out of those limits: a path outside the workspace, a command that passes the allow list and the safety list but should not, a write to a protected file, or a way to reach the network or the credential folders from a sandboxed command.
