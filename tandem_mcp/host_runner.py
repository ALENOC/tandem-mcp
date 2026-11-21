"""Host-managed execution loop for Tandem MCP:
1. Cloud planning (1 cloud call): interprets request and starts delegate / delegate_contract / delegate_many.
2. Host-managed local wait (0 cloud calls): keeps worker alive, monitors progress, enforces timeout/cancellation,
   and supports reconnecting to an existing job_id without starting duplicates.
3. Conditional cloud review (0 or 1 cloud call): only wakes the cloud if a failure or contract decision requires it.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import agent, server, store


@dataclass
class HostRunResult:
    mode: str  # "host_managed" | "local_contract_only"
    job_id: str | None
    state: str
    accepted: bool
    receipt: str
    wall_seconds: float
    wait_polls: int
    cloud_calls: list[dict[str, Any]] = field(default_factory=list)
    local_tokens: int = 0
    timed_out: bool = False
    cancelled: bool = False
    error: str = ""

    @property
    def cloud_calls_during_wait(self) -> int:
        return sum(1 for c in self.cloud_calls if c.get("phase") == "wait")

    @property
    def total_cloud_calls(self) -> int:
        return len(self.cloud_calls)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _known_job_ids() -> set[str]:
    if not store.JOBS.exists():
        return set()
    return {p.name for p in store.JOBS.iterdir() if p.is_dir()}


def _total_job_tokens(job_id: str) -> int:
    data = store.read_job(job_id) or {}
    if data.get("kind") == "batch":
        total = 0
        for row in data.get("tasks", []):
            sub_id = row.get("job")
            if sub_id:
                sub = store.read_job(sub_id) or {}
                total += int(sub.get("tokens") or 0)
        return total
    return int(data.get("tokens") or 0)


def _job_alive(job_id: str) -> bool:
    entry = agent.RUNNING.get(job_id)
    return bool(entry and entry[0].is_alive())


def _stop_job_tree(job_id: str, wait_s: float = 10.0) -> None:
    data = store.read_job(job_id) or {}
    if data.get("kind") == "batch":
        for row in data.get("tasks", []):
            if row.get("job"):
                agent.request_stop(row["job"])
    agent.request_stop(job_id)
    entry = agent.RUNNING.get(job_id)
    if entry and entry[0].is_alive():
        entry[0].join(wait_s)


def _build_receipt(job_id: str) -> str:
    data = store.read_job(job_id) or {}
    if data.get("kind") == "batch":
        return server._lean_batch_receipt(job_id)
    return server._lean_receipt(job_id)


def start_local_http_mcp(host: str = "127.0.0.1", port: int = 0) -> tuple[Any, threading.Thread, str]:
    """Start Tandem MCP streamable-http server in a daemon thread on localhost."""
    import uvicorn

    if port <= 0:
        port = _find_free_port()
    app = server.mcp.streamable_http_app()
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    uv_server = uvicorn.Server(config)
    thread = threading.Thread(target=uv_server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    return uv_server, thread, f"http://{host}:{port}/mcp"


def run_host_managed(
    cloud_planner_fn: Callable[[str], dict[str, Any]] | None = None,
    *,
    mcp_url: str = "",
    attach_job_id: str | None = None,
    local_contract: tuple[str, str, str] | None = None,
    cloud_reviewer_fn: Callable[[str, str], dict[str, Any]] | None = None,
    poll_interval_s: float = 2.0,
    timeout_s: float = 2400.0,
    stop_event: threading.Event | None = None,
    review_on_failure: bool = True,
) -> HostRunResult:
    """Execute or re-attach to a Tandem job with zero cloud calls during the local wait phase."""
    t0 = time.monotonic()
    cloud_calls: list[dict[str, Any]] = []
    mode = "local_contract_only" if (cloud_planner_fn is None and local_contract is not None) else "host_managed"

    job_id = attach_job_id
    if job_id is None:
        before_jobs = _known_job_ids()
        if cloud_planner_fn is not None:
            plan_res = cloud_planner_fn(mcp_url)
            cloud_calls.append({"phase": "plan", **plan_res})
            after_jobs = _known_job_ids()
            new_jobs = sorted(after_jobs - before_jobs)
            if plan_res.get("job_id"):
                job_id = str(plan_res["job_id"])
            elif new_jobs:
                # Prefer batch job if one was created alongside child jobs
                batches = [j for j in new_jobs if (store.read_job(j) or {}).get("kind") == "batch"]
                job_id = batches[-1] if batches else new_jobs[-1]
            if not job_id:
                return HostRunResult(
                    mode=mode,
                    job_id=None,
                    state="plan_failed",
                    accepted=False,
                    receipt=str(plan_res.get("response") or "No job started by planner"),
                    wall_seconds=round(time.monotonic() - t0, 2),
                    wait_polls=0,
                    cloud_calls=cloud_calls,
                    error=str(plan_res.get("error") or "Planner did not start a Tandem job"),
                )
        elif local_contract is not None:
            ws, cfile, sha = local_contract
            out = server.lean_delegate_contract(ws, cfile, sha)
            import re

            m = re.match(r"(?:batch|job) (\S+):", out)
            if not m:
                return HostRunResult(
                    mode=mode,
                    job_id=None,
                    state="contract_error",
                    accepted=False,
                    receipt=out,
                    wall_seconds=round(time.monotonic() - t0, 2),
                    wait_polls=0,
                    cloud_calls=cloud_calls,
                    error=out,
                )
            job_id = m.group(1)
        else:
            raise ValueError("Provide cloud_planner_fn, attach_job_id, or local_contract")

    # Phase 2: Host-managed local wait (ZERO cloud calls!)
    wait_polls = 0
    timed_out = False
    cancelled = False
    deadline = t0 + float(timeout_s) if timeout_s > 0 else None

    while True:
        data = store.read_job(job_id) or {}
        state = data.get("state", "unknown")
        alive = _job_alive(job_id)
        if state != "running" and not alive:
            break
        if stop_event is not None and stop_event.is_set():
            cancelled = True
            _stop_job_tree(job_id)
            break
        if deadline is not None and time.monotonic() >= deadline:
            timed_out = True
            _stop_job_tree(job_id)
            break
        wait_polls += 1
        time.sleep(min(poll_interval_s, max(0.01, (deadline - time.monotonic()) if deadline else poll_interval_s)))

    data = store.read_job(job_id) or {}
    state = "timeout" if timed_out else ("cancelled" if cancelled else data.get("state", "unknown"))
    receipt = _build_receipt(job_id)
    accepted = "ACCEPTED (" in receipt or (data.get("accepted") is True)

    # Phase 3: Conditional cloud review ONLY if needed
    if (
        cloud_reviewer_fn is not None
        and review_on_failure
        and not timed_out
        and not cancelled
        and state != "verified"
    ):
        rev_res = cloud_reviewer_fn(job_id, receipt)
        cloud_calls.append({"phase": "review", **rev_res})
        data = store.read_job(job_id) or {}
        state = data.get("state", state)
        receipt = _build_receipt(job_id)
        accepted = "ACCEPTED (" in receipt or (data.get("accepted") is True)

    return HostRunResult(
        mode=mode,
        job_id=job_id,
        state=state,
        accepted=accepted,
        receipt=receipt,
        wall_seconds=round(time.monotonic() - t0, 2),
        wait_polls=wait_polls,
        cloud_calls=cloud_calls,
        local_tokens=_total_job_tokens(job_id),
        timed_out=timed_out,
        cancelled=cancelled,
    )


def run_targeted_repair(
    *,
    goal: str,
    workspace: str | Path,
    write_globs: list[str],
    repair_checks: list[str],
    repair_constraints: list[str],
    regression_checks: list[str] | None = None,
    immutable: list[str] | None = None,
    read_globs: list[str] | None = None,
    allow_run: list[str] | None = None,
    context: str = "",
    model: str = "",
    max_steps: int = 12,
    max_repairs: int = 2,
    timeout_s: float = 600.0,
    unjailed_checks: bool = False,
    poll_interval_s: float = 2.0,
) -> dict[str, Any]:
    """Run a targeted local repair job (0 cloud calls) followed by host-side regression checks."""
    from . import sandbox

    t0 = time.monotonic()
    ws_root = Path(workspace).resolve()
    ws = sandbox.Workspace(
        str(ws_root),
        write_globs=write_globs,
        allow_run=allow_run or [],
        immutable=immutable or [],
        read_globs=read_globs or [],
    )
    job_id = agent.start(
        goal=goal,
        workspace=ws,
        verify=list(repair_checks),
        max_steps=max_steps,
        max_repairs=max_repairs,
        model=model,
        context=context,
        baseline=True,
        max_seconds=int(timeout_s),
        unjailed_checks=unjailed_checks,
        constraints=list(repair_constraints),
        require_proof=True,
    )
    res = run_host_managed(
        attach_job_id=job_id,
        poll_interval_s=poll_interval_s,
        timeout_s=timeout_s,
        review_on_failure=False,
    )
    reg_results = []
    reg_passed = True
    for cmd in (regression_checks or []):
        proc = subprocess.run(cmd, shell=True, cwd=str(ws_root), capture_output=True, text=True, timeout=60)
        ok = proc.returncode == 0
        reg_passed = reg_passed and ok
        reg_results.append({
            "command": cmd,
            "returncode": proc.returncode,
            "passed": ok,
            "stdout_tail": (proc.stdout or "")[-400:],
            "stderr_tail": (proc.stderr or "")[-400:],
        })
    return {
        "job_id": job_id,
        "state": res.state,
        "accepted": res.accepted,
        "wall_seconds": round(time.monotonic() - t0, 2),
        "wait_polls": res.wait_polls,
        "cloud_calls": res.total_cloud_calls,
        "local_tokens": res.local_tokens,
        "timed_out": res.timed_out,
        "regression_passed": reg_passed,
        "regression_checks": reg_results,
        "receipt": res.receipt,
    }


def make_agy_planner(
    prompt: str,
    workspace: Path,
    model: str,
    env: dict[str, str],
    timeout_s: float = 180.0,
) -> Callable[[str], dict[str, Any]]:
    """Build a single-turn cloud planner using agy against the host's local HTTP MCP server."""

    def _plan(mcp_url: str) -> dict[str, Any]:
        subprocess.run(["agy", "mcp", "add", "--type", "http", "tandem-mcp", mcp_url], check=True, capture_output=True)
        subprocess.run(["agy", "mcp", "enable", "tandem-mcp"], check=True, capture_output=True)
        cmd = [
            "agy",
            "-p", prompt,
            "--model", model,
            "--output-format", "json",
            "--mode", "auto",
            "--dangerously-skip-permissions",
            "--disable-slash-commands",
        ]
        t0 = time.monotonic()
        proc = subprocess.run(cmd, cwd=str(workspace), env=env, capture_output=True, text=True, timeout=timeout_s)
        elapsed = round(time.monotonic() - t0, 2)
        parsed: dict[str, Any] = {}
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    pass
        return {
            "status": parsed.get("status", "ERROR" if proc.returncode else "SUCCESS"),
            "duration_seconds": parsed.get("duration_seconds", elapsed),
            "num_turns": parsed.get("num_turns"),
            "conversation_id": parsed.get("conversation_id"),
            "usage": parsed.get("usage") or {},
            "response": parsed.get("response", ""),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }

    return _plan


def _set_data_dir(data_dir: str | Path) -> None:
    root = Path(data_dir).expanduser().resolve()
    store.DATA = root
    store.JOBS = root / "jobs"
    store.CACHE = root / "cache"
    store.LEDGER = root / "ledger.jsonl"
    store.LESSONS = root / "lessons.jsonl"
    store.MODELS = root / "models.json"
    store.init()


def _request_disk_stop(job_id: str) -> None:
    data = store.read_job(job_id) or {}
    targets = [job_id]
    if data.get("kind") == "batch":
        targets.extend(r["job"] for r in data.get("tasks", []) if r.get("job"))
    for tid in targets:
        jdir = store.JOBS / tid
        if jdir.is_dir():
            (jdir / "stop.requested").write_text("host_timeout\n", encoding="utf-8")
        agent.request_stop(tid)


def _compact_receipt_enabled() -> bool:
    val = os.environ.get("TANDEM_COMPACT_RECEIPT", "1").strip().lower()
    return val not in ("0", "false", "no", "off")


def _format_host_summary(job_id: str, elapsed: float, timed_out: bool) -> str:
    data = store.read_job(job_id) or {}
    state = "timeout" if timed_out and data.get("state") == "running" else str(data.get("state") or "unknown")
    tokens = _total_job_tokens(job_id)
    lines = [
        f"HOST_MANAGED_RESULT job={job_id} state={state} wall_seconds={elapsed:.2f} local_tokens={tokens}",
    ]
    checks = data.get("checks") or []
    if not _compact_receipt_enabled():
        if checks:
            lines.append("CHECKS_SUMMARY:")
            for c in checks:
                lines.append(f"  - exit={c.get('exit')} cmd={c.get('command')}")
        elif data.get("kind") == "batch":
            lines.append("BATCH_TASKS:")
            for row in data.get("tasks", []):
                sub = store.read_job(row.get("job", "")) or {}
                lines.append(f"  - {row.get('name')}: job={row.get('job')} state={sub.get('state')} checks={len(sub.get('checks') or [])}")
        lines.append("RECEIPT:")
        lines.append(_build_receipt(job_id))
        return "\n".join(lines)

    changes = data.get("changes") or []
    if changes:
        files_s = ", ".join(f"{c[0]} (+{c[2]} -{c[3]})" if len(c) >= 4 else str(c[0]) for c in changes)
        lines.append(f"FILES_MODIFIED: {files_s}")
    elif data.get("kind") == "batch":
        lines.append("BATCH_TASKS:")
        for row in data.get("tasks", []):
            sub = store.read_job(row.get("job", "")) or {}
            lines.append(f"  - {row.get('name')}: job={row.get('job')} state={sub.get('state')} checks={len(sub.get('checks') or [])}")
    else:
        lines.append("FILES_MODIFIED: none")

    passed_checks = [
        c for c in checks
        if not c.get("skipped")
        and not c.get("not_evaluated")
        and (c.get("outcome") == "passed" or ("outcome" not in c and c.get("exit") == 0))
    ]
    not_eval_checks = [
        c for c in checks
        if not c.get("skipped") and (c.get("outcome") == "not_evaluated" or c.get("not_evaluated"))
    ]
    failed_checks = [
        c for c in checks
        if not c.get("skipped")
        and not c.get("not_evaluated")
        and c.get("outcome") != "not_evaluated"
        and (c.get("outcome") == "failed" or ("outcome" not in c and c.get("exit") not in (0, None)))
    ]
    skipped_checks = [c for c in checks if c.get("skipped") or c.get("exit") is None]

    if checks:
        lines.append("CHECKS_SUMMARY:")
        for c in passed_checks:
            lines.append(f"  - exit=0 cmd={c.get('command')}")
        for c in not_eval_checks:
            mp = c.get("missing_prerequisite") or "prerequisite missing"
            lines.append(f"  - not_evaluated (exit={c.get('exit')}) cmd={c.get('command')} ({mp})")
        for c in skipped_checks:
            lines.append(f"  - skipped cmd={c.get('command')}")
        for c in failed_checks:
            hist_note = " [historical exit=2: outcome_unknown_prereq_vs_defect]" if ("outcome" not in c and c.get("exit") == 2) else ""
            lines.append(f"  - exit={c.get('exit')} cmd={c.get('command')}{hist_note}")
            if c.get("tail"):
                lines.append(f"    tail: {str(c.get('tail')).strip()[-300:]}")
    else:
        lines.append("CHECKS_SUMMARY: none")

    constraints = data.get("constraints") or []
    n_req = len(constraints)
    all_req_ids = set(range(1, n_req + 1))
    evidence = data.get("evidence") or {}
    if isinstance(evidence, dict):
        evidence_ids = {int(k) for k in evidence if str(k).isdigit()}
    elif isinstance(evidence, list):
        evidence_ids = {int(e["constraint"]) for e in evidence if isinstance(e, dict) and str(e.get("constraint", "")).isdigit()}
    else:
        evidence_ids = set()
    unproven = data.get("unproven") or []
    missing_proof = bool(data.get("require_proof")) and bool(constraints) and not evidence

    covered_ids: set[int] = set()
    observed_notes: list[str] = []
    for c in passed_checks:
        cov = c.get("covers_constraints")
        if isinstance(cov, list) and cov:
            for item in cov:
                if str(item).isdigit():
                    covered_ids.add(int(item))
            if c.get("observed"):
                observed_notes.append(str(c["observed"]).strip())
        elif c.get("command") == "tandem:web_check":
            observed_notes.append("startup, 0 JS errors, canvas animation (tandem:web_check smoke only)")
        elif c.get("observed"):
            observed_notes.append(str(c["observed"]).strip())

    if observed_notes:
        lines.append(f"OBSERVED: {'; '.join(dict.fromkeys(observed_notes))}")
    elif passed_checks:
        lines.append("OBSERVED: command exit=0 only (no per-requirement behavioral proof)")
    else:
        lines.append("OBSERVED: none")

    if state == "not_evaluated" or (not_eval_checks and not failed_checks):
        prereqs = [str(c.get("missing_prerequisite") or c.get("command")) for c in not_eval_checks]
        lines.append("VERDICT: Verification incomplete: mandatory check not_evaluated due to missing verifier prerequisite. Artifact and passing checks preserved; do not repair code.")
        lines.append(f"COVERAGE: incomplete_not_evaluated (not_evaluated={len(not_eval_checks)}, passed={len(passed_checks)}/{len(checks)})")
        lines.append(f"MISSING_PREREQUISITE: {'; '.join(prereqs) if prereqs else 'verifier prerequisite unavailable'}")
        if data.get("summary"):
            lines.append(f"WORKER_CLAIM (not server verdict): {str(data.get('summary')).strip()[:200]}")
    elif state != "verified" or failed_checks:
        reasons = []
        if state != "verified":
            reasons.append(f"state={state}")
        if failed_checks:
            reasons.append(f"failed_checks={len(failed_checks)}")
        if unproven:
            reasons.append(f"unproven_constraints={unproven}")
        if missing_proof:
            reasons.append("missing_evidence")
        lines.append("VERDICT: Verification failed or incomplete. Inspect only the affected file/lines or run targeted checks before finalizing.")
        lines.append(f"COVERAGE: failed_or_incomplete ({', '.join(reasons)})")
        if n_req > 0:
            missing_reqs = sorted(all_req_ids - covered_ids)
            if missing_reqs:
                lines.append(f"FAILED_OR_UNVERIFIED_REQUIREMENTS: {missing_reqs}")
        if data.get("summary"):
            lines.append(f"WORKER_CLAIM (not server verdict): {str(data.get('summary')).strip()[:200]}")
    elif not passed_checks:
        lines.append("COVERAGE: none (no passing checks executed)")
        if skipped_checks:
            lines.append(f"MISSING_PROOF: skipped_checks={len(skipped_checks)}")
        lines.append("VERDICT: No passing checks executed. Run targeted verification or inspect affected files before finalizing.")
    elif n_req > 0 and covered_ids >= all_req_ids and not unproven and not missing_proof and not skipped_checks:
        scope = "; ".join(f"#{i}: {str(c).strip()[:50]}" for i, c in enumerate(constraints, 1))
        lines.append(f"COVERAGE: complete ({n_req}/{n_req} contract requirements verified: {scope})")
        lines.append("MISSING_PROOF: none")
        if data.get("summary"):
            lines.append(f"SUMMARY: {str(data.get('summary')).strip()[:200]}")
        lines.append("VERDICT: All contract requirements behaviorally verified. Summarize directly without re-reading full files.")
    elif covered_ids and (covered_ids & all_req_ids):
        verified_set = sorted(covered_ids & all_req_ids)
        missing_reqs = sorted(all_req_ids - covered_ids)
        lines.append(f"COVERAGE: partial ({len(verified_set)}/{n_req} requirements verified; covered={verified_set})")
        miss_parts = []
        if missing_reqs:
            miss_parts.append(f"requirements={missing_reqs}")
        if unproven:
            miss_parts.append(f"unproven={unproven}")
        if skipped_checks:
            miss_parts.append(f"skipped_checks={len(skipped_checks)}")
        lines.append(f"MISSING_PROOF: {', '.join(miss_parts) if miss_parts else 'partial'}")
        lines.append(f"VERDICT: Partial coverage. Verify or inspect only missing requirements ({missing_reqs or unproven}) before promising full completion.")
    else:
        lines.append(f"COVERAGE: copertura non determinabile dai dati del job ({n_req} requirements; static_evidence={len(evidence_ids)}/{n_req})")
        miss_msg = "per-requirement runtime proof not recorded"
        if unproven:
            miss_msg += f"; unproven={unproven}"
        if skipped_checks:
            miss_msg += f"; skipped_checks={len(skipped_checks)}"
        lines.append(f"MISSING_PROOF: {miss_msg}")
        lines.append("VERDICT: Copertura non determinabile; esegui una verifica mirata sui requisiti chiave prima di promettere copertura completa.")
    return "\n".join(lines)


def attach_and_wait(
    job_id: str,
    *,
    data_dir: str | Path | None = None,
    poll_interval_s: float = 2.0,
    timeout_s: float = 1800.0,
) -> dict[str, Any]:
    """Attach an external host watcher to an existing Tandem job_id with 0 cloud calls."""
    if data_dir:
        _set_data_dir(data_dir)
    t0 = time.monotonic()
    deadline = t0 + max(1.0, float(timeout_s))
    timed_out = False
    polls = 0
    while True:
        polls += 1
        data = store.read_job(job_id) or {}
        state = data.get("state")
        if state and state != "running":
            break
        if time.monotonic() >= deadline:
            timed_out = True
            _request_disk_stop(job_id)
            stop_wait = time.monotonic() + 10.0
            while time.monotonic() < stop_wait:
                d2 = store.read_job(job_id) or {}
                if d2.get("state") and d2.get("state") != "running":
                    break
                time.sleep(0.25)
            break
        time.sleep(max(0.1, float(poll_interval_s)))

    elapsed = round(time.monotonic() - t0, 2)
    final_data = store.read_job(job_id) or {}
    final_state = "timeout" if timed_out and final_data.get("state") == "running" else str(final_data.get("state") or "unknown")
    summary = _format_host_summary(job_id, elapsed, timed_out)
    return {
        "job_id": job_id,
        "state": final_state,
        "timed_out": timed_out,
        "wall_seconds": elapsed,
        "wait_polls": polls,
        "local_tokens": _total_job_tokens(job_id),
        "summary": summary,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Tandem MCP host-managed local job watcher")
    parser.add_argument("--attach", required=True, help="Existing Tandem job_id or batch_id")
    parser.add_argument("--data-dir", default=os.environ.get("TANDEM_DATA", ""), help="Tandem data directory")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Local poll interval in seconds")
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("TANDEM_HOST_TIMEOUT", "1800")),
        help="Local timeout in seconds",
    )
    args = parser.parse_args(argv)
    res = attach_and_wait(
        args.attach,
        data_dir=args.data_dir or None,
        poll_interval_s=args.poll_interval,
        timeout_s=args.timeout,
    )
    print(res["summary"], flush=True)
    return 0 if res["state"] == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
