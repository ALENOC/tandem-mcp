#!/usr/bin/env python3
"""Benchmark suite for Tandem MCP v3.6.1: Gemini 4 Hydrogen + Qwen3.8 27B."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluate import evaluate_attempt

BENCHMARKS_DIR = Path(__file__).resolve().parents[1]
if str(BENCHMARKS_DIR) not in sys.path:
    sys.path.insert(0, str(BENCHMARKS_DIR))
from suite_common import (  # noqa: E402
    read_ledger_entries,
    sha256_path as _sha256_path,
    summarize_local_ledger,
    write_agy_session_settings,
)

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
RUNS_DIR = ROOT / "runs"

ORCHESTRATOR_MODEL = "gemini-4-hydrogen-medium"
ORCHESTRATOR_LABEL = "Gemini 4 Hydrogen (Medium)"
EXECUTOR_MODEL = "qwen3.8-27b@iq3_s"
LM_STUDIO_URL = "http://127.0.0.1:1234/v1"

TASKS: list[dict[str, Any]] = [
    {
        "id": "reading_agent_rollback",
        "name": "Targeted code QA (agent.py rollback)",
        "category": "reading",
        "timeout_s": 900,
        "fixture_type": "dir",
        "fixture": "tandem_mcp_pkg",
        "direct_prompt": (
            "In tandem_mcp_pkg/agent.py, what does rollback do when a pre-existing file entry "
            "in snapshot.json has value None, and what does it do when the value is a string/path? "
            "Cite the relevant logic concisely."
        ),
        "tandem_prompt": (
            "Use Tandem MCP (`digest_file` with grep='snapshot.json' or focused question) on "
            "tandem_mcp_pkg/agent.py to answer: what does rollback do when a pre-existing file entry "
            "in snapshot.json has value None, and what does it do when the value is a string/path? "
            "Do not read the full file directly with native tools."
        ),
    },
    {
        "id": "reading_package_survey",
        "name": "Multi-file package survey (tandem_mcp/*.py)",
        "category": "reading",
        "timeout_s": 1200,
        "fixture_type": "dir",
        "fixture": "tandem_mcp_pkg",
        "direct_prompt": (
            "Summarize the primary responsibility of each .py module in tandem_mcp_pkg/ "
            "(excluding __init__.py). List each module name and a 1-sentence summary."
        ),
        "tandem_prompt": (
            "Use Tandem MCP (`digest_many` on tandem_mcp_pkg/*.py) to summarize the primary "
            "responsibility of each .py module in tandem_mcp_pkg/ (excluding __init__.py). "
            "List each module name and a 1-sentence summary. Do not read the files directly."
        ),
    },
    {
        "id": "reading_git_log",
        "name": "Git history digestion (25 commits)",
        "category": "reading",
        "timeout_s": 900,
        "fixture_type": "file",
        "fixture": "git_log_25_stat.txt",
        "direct_prompt": (
            "From git_log_25_stat.txt, which 3 files were modified in the most commits, "
            "and what are the main themes of these 25 commits?"
        ),
        "tandem_prompt": (
            "Use Tandem MCP (`digest_file` on git_log_25_stat.txt) to determine which 3 files "
            "were modified in the most commits and the main themes of these 25 commits. "
            "Do not read git_log_25_stat.txt directly."
        ),
    },
    {
        "id": "extraction_manifest",
        "name": "Structured JSON extraction (pyproject.toml)",
        "category": "extraction",
        "timeout_s": 240,
        "fixture_type": "file",
        "fixture": "pyproject.toml",
        "direct_prompt": (
            "From pyproject.toml, return ONLY a valid JSON object with keys: "
            "\"name\", \"requires_python\", \"dependencies\" (list of strings), \"console_script\" (string)."
        ),
        "tandem_prompt": (
            "Use Tandem MCP (`extract_from_file` on pyproject.toml) to extract a JSON object with keys: "
            "\"name\", \"requires_python\", \"dependencies\" (list of strings), \"console_script\" (string). "
            "Return ONLY the JSON object."
        ),
    },
    {
        "id": "bugfix_multifile",
        "name": "Multi-file bugfix (4 modules + tests)",
        "category": "bugfix",
        "timeout_s": 600,
        "fixture_type": "dir_flat",
        "fixture": "bugfix_multifile",
        "direct_prompt": (
            "Run `python3 -m unittest test_suite.py` in the workspace, diagnose the bugs across "
            "the modules (parser.py, validator.py, etc.), fix them without modifying test_suite.py, "
            "and re-run `python3 -m unittest test_suite.py` to confirm all tests pass."
        ),
        "tandem_prompt": (
            "Use Tandem MCP (`delegate` with `python3 -m unittest test_suite.py` as acceptance check, "
            "writable=['parser.py', 'validator.py', 'service.py', 'config.py']) to diagnose and fix "
            "the bugs in this workspace without modifying test_suite.py. Inspect `job_evidence` / `job_diff` "
            "and call `job_feedback` before finishing."
        ),
    },
    {
        "id": "feature_rate_limiter",
        "name": "Bounded module + tests (rate_limiter.py)",
        "category": "feature",
        "timeout_s": 900,
        "fixture_type": "dir_flat",
        "fixture": "feature_rate_limiter",
        "direct_prompt": (
            "Read SPEC.md and implement `rate_limiter.py` and `test_rate_limiter.py` satisfying "
            "every requirement. Run `python3 -m unittest test_rate_limiter.py` to verify all tests pass."
        ),
        "tandem_prompt": (
            "Read SPEC.md (via `digest_file` or directly), then use Tandem MCP (`delegate` with "
            "writable=['rate_limiter.py', 'test_rate_limiter.py'] and acceptance check "
            "`python3 -m unittest test_rate_limiter.py`) to implement `rate_limiter.py` and "
            "`test_rate_limiter.py`. Inspect `job_evidence` and call `job_feedback` before finishing."
        ),
    },
    {
        "id": "gen_orbital",
        "name": "Orbital animation (46 constraints)",
        "category": "generation",
        "timeout_s": 2400,
        "fixture_type": "dir_flat",
        "fixture": "generation",
        "direct_prompt": (
            (FIXTURES / "generation" / "orbital_prompt.txt").read_text(encoding="utf-8").strip()
            + "\n\nNote: `animation.json` in the workspace specifies the required element IDs (`btnPlay`, `btnTrails`, `btnReset`, `speed`, `speedVal`, `fps`, `simTime`, `bursts`) and `check_page.js` validates `index.html`. Run `node check_page.js` to verify your implementation passes."
        ),
        "tandem_prompt": (
            (FIXTURES / "generation" / "orbital_prompt.txt").read_text(encoding="utf-8").strip()
            + "\n\nRead animation.json and pass its goal, constraints, immutable files, write_globs "
            "and verify_commands to delegate using the current workspace. Poll the same job until terminal."
        ),
    },
    {
        "id": "gen_portal",
        "name": "3D neon portal (69 constraints)",
        "category": "generation",
        "timeout_s": 4200,
        "fixture_type": "dir_flat",
        "fixture": "generation",
        "direct_prompt": (
            (FIXTURES / "generation" / "portal_prompt.txt").read_text(encoding="utf-8").strip()
            + "\n\nNote: Create `index.html`, `scene.js`, `engine3d.js`, and `app.js` matching `scene3d.json` in the workspace, and run `node check_engine.js` to verify your implementation passes."
        ),
        "tandem_prompt": (
            (FIXTURES / "generation" / "portal_prompt.txt").read_text(encoding="utf-8").strip()
            + "\n\nRead scene3d.json and pass its tasks, dependencies and budgets to delegate_many "
            "using the current workspace. Poll the same batch until terminal."
        ),
    },
    {
        "id": "refactor_rename",
        "name": "Cross-file rename (13 modules + tests)",
        "category": "refactor",
        "timeout_s": 900,
        "fixture_type": "dir_flat",
        "fixture": "refactor_rename",
        "direct_prompt": (
            "In this workspace, rename `get_conf` to `load_settings` in `settings.py` and update "
            "every import and call site across all `svc_*.py` modules. Run `python3 -m unittest test_rename.py` "
            "to verify all tests pass."
        ),
        "tandem_prompt": (
            "Use Tandem MCP (`delegate` or `delegate_many` with `write_globs=['settings.py', 'svc_*.py']`, "
            "`verify_commands=['python3 -m unittest test_rename.py']`, and atomic constraints) to rename "
            "`get_conf` to `load_settings` in `settings.py` and update every `svc_*.py` module. "
            "Do not read the source files yourself first."
        ),
    },
    {
        "id": "reading_incident_log",
        "name": "Large incident log QA (85 KB)",
        "category": "reading",
        "timeout_s": 600,
        "fixture_type": "file",
        "fixture": "incident_log.txt",
        "common_prompt": (
            "From `incident_log.txt`, reconstruct the real incident: which service failed first, "
            "at what exact timestamp (HH:MM:SS), what was the root cause, and at what timestamp was it resolved?"
        ),
        "direct_prompt": (
            "From `incident_log.txt`, reconstruct the real incident: which service failed first, "
            "at what exact timestamp (HH:MM:SS), what was the root cause, and at what timestamp was it resolved? "
            "You may use targeted search/grep tools."
        ),
        "tandem_prompt": (
            "Use Tandem MCP (`digest_file` with targeted grep or focused queries) on `incident_log.txt` "
            "to reconstruct the real incident: which service failed first, at what exact timestamp (HH:MM:SS), "
            "what was the root cause, and at what timestamp was it resolved? "
            "Do not read `incident_log.txt` directly."
        ),
    },
]


def preflight() -> dict[str, Any]:
    """Verify LM Studio and agy CLI are ready."""
    req = urllib.request.Request(f"{LM_STUDIO_URL}/models", method="GET")
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    model_ids = [m.get("id") for m in data.get("data", [])]
    if EXECUTOR_MODEL not in model_ids:
        raise RuntimeError(f"Executor model {EXECUTOR_MODEL!r} not found in LM Studio models: {model_ids}")

    agy_ver = subprocess.run(["agy", "--version"], capture_output=True, text=True, check=True).stdout.strip()
    mcp_list = subprocess.run(["agy", "mcp", "list"], capture_output=True, text=True, check=True).stdout
    tandem_enabled = "tandem-mcp" in mcp_list and "enabled" in [
        line for line in mcp_list.splitlines() if "tandem-mcp" in line
    ][0]
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "lm_studio_url": LM_STUDIO_URL,
        "lm_studio_models": model_ids,
        "executor_model": EXECUTOR_MODEL,
        "orchestrator_model": ORCHESTRATOR_MODEL,
        "agy_version": agy_ver,
        "initial_tandem_mcp_enabled": tandem_enabled,
    }


def set_tandem_mcp(enabled: bool) -> None:
    cmd = ["agy", "mcp", "enable" if enabled else "disable", "tandem-mcp"]
    subprocess.run(cmd, capture_output=True, text=True, check=True)


def prepare_workspace(task: dict[str, Any], workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    src = FIXTURES / task["fixture"]
    ftype = task["fixture_type"]
    if ftype == "file":
        shutil.copy2(src, workspace / src.name)
    elif ftype == "dir":
        shutil.copytree(src, workspace / src.name, dirs_exist_ok=True)
    elif ftype == "dir_flat":
        shutil.copytree(src, workspace, dirs_exist_ok=True)
    else:
        raise ValueError(f"Unknown fixture_type: {ftype}")


def read_ledger_entries(ledger_path: Path) -> list[dict[str, Any]]:
    if not ledger_path.exists():
        return []
    entries = []
    for line in ledger_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def summarize_local_ledger(entries: list[dict[str, Any]], attempt_id: str | None = None) -> dict[str, Any]:
    """Summarize inference-only local ledger entries for an isolated attempt."""
    if not entries:
        return {
            "status": "unavailable",
            "delegation_verified": False,
            "local_calls": None,
            "local_prompt_tokens": None,
            "local_completion_tokens": None,
            "local_total_tokens": None,
            "estimated_saved_tokens": None,
            "retries": 0,
            "attempt_id": attempt_id,
        }
    llm_entries = [e for e in entries if e.get("kind") == "llm"]
    retries = sum(1 for e in entries if e.get("kind") == "retry")
    delegation_verified = any(e.get("kind") in ("llm", "result", "job") for e in entries)
    if not llm_entries:
        return {
            "status": "unavailable" if not delegation_verified else "no_llm_events",
            "delegation_verified": delegation_verified,
            "local_calls": 0,
            "local_prompt_tokens": None,
            "local_completion_tokens": None,
            "local_total_tokens": None,
            "estimated_saved_tokens": sum(int(e.get("saved_tokens_est", 0) or 0) for e in entries),
            "retries": retries,
            "attempt_id": attempt_id,
        }
    prompt_tok = sum(int(e.get("prompt_tokens", 0) or 0) for e in llm_entries)
    comp_tok = sum(int(e.get("completion_tokens", 0) or 0) for e in llm_entries)
    saved_tok = sum(int(e.get("saved_tokens_est", 0) or 0) for e in entries)
    return {
        "status": "available",
        "delegation_verified": delegation_verified,
        "local_calls": len(llm_entries),
        "local_prompt_tokens": prompt_tok,
        "local_completion_tokens": comp_tok,
        "local_total_tokens": prompt_tok + comp_tok,
        "estimated_saved_tokens": saved_tok,
        "retries": retries,
        "attempt_id": attempt_id,
    }


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    if path.is_file():
        h.update(path.read_bytes())
    elif path.is_dir():
        for p in sorted(path.rglob("*")):
            if p.is_file():
                h.update(str(p.relative_to(path)).encode("utf-8"))
                h.update(p.read_bytes())
    return h.hexdigest()


def compute_evaluator_sha256() -> str:
    """Combined SHA-256 identity of the task evaluator and shared browser checker."""
    h = hashlib.sha256()
    for path in (ROOT / "evaluate.py", BENCHMARKS_DIR / "web_browser_check.py"):
        if path.exists():
            h.update(path.name.encode("utf-8"))
            h.update(b"\0")
            h.update(path.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def compute_e2e_success(
    completed: bool,
    artifact_valid: bool,
    effective_scenario: str,
    delegation_verified: bool,
) -> bool:
    """Attribute E2E success: Tandem attempts require both valid answer and verified delegation."""
    if effective_scenario == "tandem":
        return bool(completed and artifact_valid and delegation_verified)
    return bool(completed and artifact_valid)


def deterministic_parse_manifest(workspace: Path) -> dict[str, Any]:
    """Deterministically extract required fields from pyproject.toml using tomllib."""
    toml_path = workspace / "pyproject.toml"
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    project = data["project"]
    scripts = project.get("scripts") or {}
    if not isinstance(scripts, dict) or not scripts:
        raise ValueError("Missing project.scripts in pyproject.toml")
    first_name, first_target = next(iter(scripts.items()))
    return {
        "name": str(project["name"]),
        "requires_python": str(project["requires-python"]),
        "dependencies": [str(d) for d in project.get("dependencies", [])],
        "console_script": f"{first_name} = {first_target}",
    }


def recommend_route(
    category: str,
    volume_bytes: int,
    file_count: int = 1,
    suffix: str = "",
    has_strong_checks: bool = False,
    explicit_mode: str | None = None,
) -> dict[str, Any]:
    """Simple selective routing policy (B06):
    - Preserves explicit_mode ('direct' or 'tandem') when chosen by the user.
    - Structured formats -> deterministic/direct parsing.
    - Small inputs -> direct focused reading.
    - Large volumes or multi-file code with strong checks -> Tandem delegation.
    """
    if explicit_mode in ("direct", "tandem"):
        return {
            "route": explicit_mode,
            "delegated": explicit_mode == "tandem",
            "reason": f"explicit user choice ({explicit_mode})",
            "estimated_volume_bytes": volume_bytes,
            "estimated_calls": 1 if explicit_mode == "direct" else max(1, file_count),
        }
    if category == "extraction" or suffix.lower() in {".toml", ".json", ".yaml", ".yml"}:
        return {
            "route": "direct_parse",
            "delegated": False,
            "reason": "structured format: deterministic/direct parsing avoids executor overhead",
            "estimated_volume_bytes": volume_bytes,
            "estimated_calls": 1,
        }
    if category == "reading":
        if volume_bytes >= 50_000 or file_count >= 5:
            return {
                "route": "tandem_digest",
                "delegated": True,
                "reason": f"large reading volume ({volume_bytes} B, {file_count} files)",
                "estimated_volume_bytes": volume_bytes,
                "estimated_calls": max(1, min(file_count, 6)),
            }
        return {
            "route": "direct_focused",
            "delegated": False,
            "reason": f"small/focused reading ({volume_bytes} B, {file_count} files)",
            "estimated_volume_bytes": volume_bytes,
            "estimated_calls": 1,
        }
    if has_strong_checks and (file_count >= 3 or volume_bytes >= 15_000):
        return {
            "route": "tandem_delegate",
            "delegated": True,
            "reason": f"local work with strong checks ({file_count} files, {volume_bytes} B)",
            "estimated_volume_bytes": volume_bytes,
            "estimated_calls": max(1, file_count),
        }
    return {
        "route": "direct_focused",
        "delegated": False,
        "reason": "small edit or weak checks: direct execution preferred",
        "estimated_volume_bytes": volume_bytes,
        "estimated_calls": 1,
    }


def _task_volume_stats(task: dict[str, Any]) -> tuple[int, int, str]:
    src = FIXTURES / task["fixture"]
    if src.is_file():
        return src.stat().st_size, 1, src.suffix
    files = [p for p in src.rglob("*") if p.is_file()]
    return sum(p.stat().st_size for p in files), len(files), ""


def build_execution_plan(
    tasks: list[dict[str, Any]],
    repeats: int,
    order: str = "counterbalanced",
    seed: int = 42,
    scenarios: tuple[str, ...] = ("direct", "tandem"),
) -> list[dict[str, Any]]:
    """Build a reproducible paired execution plan with counterbalanced scenario ordering."""
    plan: list[dict[str, Any]] = []
    rng = random.Random(seed)
    for rep in range(1, repeats + 1):
        for idx, task in enumerate(tasks):
            pair_id = f"{task['id']}__r{rep}"
            if order == "counterbalanced" and len(scenarios) >= 2:
                if len(scenarios) == 2:
                    flip = ((idx + rep) % 2 == 1) ^ bool(rng.randint(0, 1) if rep == 1 and idx == 0 else 0)
                    pair_scenarios = (scenarios[1], scenarios[0]) if flip else (scenarios[0], scenarios[1])
                else:
                    rot = (idx + rep + rng.randint(0, len(scenarios) - 1)) % len(scenarios)
                    pair_scenarios = scenarios[rot:] + scenarios[:rot]
            elif order == "tandem_first":
                pair_scenarios = tuple(reversed(scenarios))
            else:
                pair_scenarios = tuple(scenarios)
            for pos, scen in enumerate(pair_scenarios):
                plan.append({
                    "pair_id": pair_id,
                    "task": task,
                    "task_id": task["id"],
                    "repeat": rep,
                    "scenario": scen,
                    "pair_order": list(pair_scenarios),
                    "pair_position": pos,
                    "seed": seed,
                })
    return plan


def build_run_manifest(
    run_id: str,
    pre: dict[str, Any],
    selected_tasks: list[dict[str, Any]],
    args: argparse.Namespace,
    plan: list[dict[str, Any]],
) -> dict[str, Any]:
    """Capture full provenance for a benchmark run."""
    repo_root = ROOT.parents[1]
    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True
    ).stdout.strip()
    git_diff = subprocess.run(
        ["git", "diff"], cwd=repo_root, capture_output=True, text=True
    ).stdout
    fixture_hashes = {
        t["id"]: _sha256_path(FIXTURES / t["fixture"]) for t in selected_tasks
    }
    return {
        "schema_version": 2,
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "git_dirty": bool(git_diff.strip()),
        "local_diff_sha256": hashlib.sha256(git_diff.encode("utf-8")).hexdigest(),
        "evaluator_sha256": compute_evaluator_sha256(),
        "suite_sha256": _sha256_path(ROOT / "suite.py"),
        "fixture_hashes": fixture_hashes,
        "profile": "lean" if getattr(args, "lean", False) else "default",
        "cli": {"name": "agy", "version": pre.get("agy_version")},
        "requested_models": {
            "orchestrator": ORCHESTRATOR_MODEL,
            "executor": EXECUTOR_MODEL,
        },
        "observed_models": {
            "lm_studio_models": pre.get("lm_studio_models", []),
        },
        "parameters": {
            "repeats": args.repeats,
            "order": getattr(args, "order", "counterbalanced"),
            "seed": getattr(args, "seed", 42),
            "lean": bool(getattr(args, "lean", False)),
            "tasks": [t["id"] for t in selected_tasks],
        },
        "prompts": {
            t["id"]: {"direct": t["direct_prompt"], "tandem": t["tandem_prompt"]}
            for t in selected_tasks
        },
        "plan": [
            {
                "pair_id": step["pair_id"],
                "task_id": step["task_id"],
                "repeat": step["repeat"],
                "scenario": step["scenario"],
                "pair_order": step["pair_order"],
                "seed": step["seed"],
            }
            for step in plan
        ],
    }


def validate_merge(prior_payload: dict[str, Any], current_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Ensure merged runs share compatible evaluator/profile/fixtures/config and have no duplicate attempt_ids."""
    prior_manifest = prior_payload.get("manifest") or {}
    if prior_manifest:
        if prior_manifest.get("evaluator_sha256") != current_manifest.get("evaluator_sha256"):
            raise ValueError("Incompatible merge: evaluator_sha256 differs from prior run")
        if prior_manifest.get("profile") != current_manifest.get("profile"):
            raise ValueError("Incompatible merge: profile differs from prior run")
        prior_models = prior_manifest.get("requested_models")
        curr_models = current_manifest.get("requested_models")
        if prior_models and curr_models and prior_models != curr_models:
            raise ValueError("Incompatible merge: requested_models differ from prior run")
        prior_fixtures = prior_manifest.get("fixture_hashes") or {}
        curr_fixtures = current_manifest.get("fixture_hashes") or {}
        for tid in set(prior_fixtures) & set(curr_fixtures):
            if prior_fixtures[tid] != curr_fixtures[tid]:
                raise ValueError(f"Incompatible merge: fixture_hashes differ for {tid}")
        prior_prompts = prior_manifest.get("prompts") or {}
        curr_prompts = current_manifest.get("prompts") or {}
        for tid in set(prior_prompts) & set(curr_prompts):
            if prior_prompts[tid] != curr_prompts[tid]:
                raise ValueError(f"Incompatible merge: prompts differ for {tid}")
    prior_attempts = prior_payload.get("attempts", [])
    seen = set()
    for a in prior_attempts:
        aid = a.get("attempt_id")
        if aid in seen:
            raise ValueError(f"Duplicate attempt_id in prior run: {aid}")
        seen.add(aid)
    for step in current_manifest.get("plan") or []:
        planned_aid = f"{step['task_id']}__{step['scenario']}__r{step['repeat']}"
        if planned_aid in seen:
            raise ValueError(f"Duplicate attempt_id across merge and current plan: {planned_aid}")
    return prior_attempts


def run_attempt(
    task: dict[str, Any],
    scenario: str,
    repeat: int,
    run_dir: Path,
    lean_mode: bool = False,
) -> dict[str, Any]:
    attempt_id = f"{task['id']}__{scenario}__r{repeat}"
    workspace = run_dir / "workspaces" / attempt_id
    prepare_workspace(task, workspace)

    effective_scenario = scenario
    routing = None
    route_steps: list[str] = [scenario]
    fallback_used = False
    if scenario == "selective":
        vol, fcnt, suf = _task_volume_stats(task)
        has_strong = task["category"] in ("bugfix", "feature", "refactor")
        routing = recommend_route(task["category"], vol, fcnt, suf, has_strong_checks=has_strong)
        if routing["route"] == "direct_parse":
            t_parse0 = time.monotonic()
            parsed_ok = False
            ev_parse: dict[str, Any] = {}
            if task["id"] == "extraction_manifest":
                try:
                    parsed_manifest = deterministic_parse_manifest(workspace)
                    resp_parse = json.dumps(parsed_manifest)
                    ev_parse = evaluate_attempt(task["id"], resp_parse, workspace)
                    parsed_ok = bool(ev_parse.get("valid"))
                except Exception:
                    parsed_ok = False
            if parsed_ok:
                elapsed_parse = round(time.monotonic() - t_parse0, 4)
                return {
                    "attempt_id": attempt_id,
                    "task_id": task["id"],
                    "task_name": task["name"],
                    "category": task["category"],
                    "scenario": scenario,
                    "effective_scenario": "direct_parse",
                    "executed_route": "direct_parse",
                    "route_steps": ["direct_parse"],
                    "fallback_used": False,
                    "routing": routing,
                    "repeat": repeat,
                    "completed": True,
                    "timed_out": False,
                    "artifact_valid": True,
                    "delegation_verified": False,
                    "route_verified": True,
                    "attribution_reason": "ok",
                    "eval_reason": ev_parse["reason"],
                    "eval_requirements": (ev_parse.get("details") or {}).get("requirements"),
                    "e2e_success": True,
                    "duration_seconds": elapsed_parse,
                    "wall_seconds": elapsed_parse,
                    "num_turns": 0,
                    "conversation_id": None,
                    "cloud_usage_status": "not_invoked",
                    "cloud_usage": {
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "thinking_tokens": 0,
                        "cache_read_tokens": 0,
                        "total_tokens": 0,
                    },
                    "local_usage": {
                        "status": "not_applicable",
                        "delegation_verified": False,
                        "local_calls": 0,
                        "local_prompt_tokens": 0,
                        "local_completion_tokens": 0,
                        "local_total_tokens": 0,
                        "estimated_saved_tokens": 0,
                        "retries": 0,
                        "attempt_id": attempt_id,
                    },
                }
            # Fallback to direct prompt when deterministic parse fails or is unavailable
            effective_scenario = "direct"
            route_steps = ["direct_parse", "direct"]
            fallback_used = True
        elif routing["delegated"]:
            effective_scenario = "tandem"
            route_steps = ["tandem"]
        else:
            effective_scenario = "direct"
            route_steps = ["direct"]

    if lean_mode and effective_scenario == "tandem":
        rules_doc = ROOT.parents[1] / "docs" / "ORCHESTRATOR_RULES.md"
        if rules_doc.exists():
            text = rules_doc.read_text(encoding="utf-8")
            import re as _re
            m = _re.search(r"```markdown\n(.*?)```", text, _re.DOTALL)
            if m:
                (workspace / "GEMINI.md").write_text(m.group(1), encoding="utf-8")

    tandem_home = run_dir / "tandem_homes" / attempt_id
    tandem_home.mkdir(parents=True, exist_ok=True)

    default_ledger = Path.home() / ".local/share/tandem-mcp/ledger.jsonl"
    before_default_count = len(read_ledger_entries(default_ledger)) if scenario == "tandem" else 0

    env = os.environ.copy()
    env["TANDEM_HOME"] = str(tandem_home)
    env["TANDEM_MODEL"] = EXECUTOR_MODEL
    if lean_mode:
        env["TANDEM_PROFILE"] = "lean"
        env["TANDEM_WAIT_SECONDS"] = "150"

    prompt = task["direct_prompt"] if effective_scenario == "direct" else task["tandem_prompt"]
    if lean_mode and effective_scenario == "tandem" and task["id"] in {"gen_orbital", "gen_portal"}:
        contract = "animation.json" if task["id"] == "gen_orbital" else "scene3d.json"
        digest = hashlib.sha256((FIXTURES / "generation" / contract).read_bytes()).hexdigest()
        prompt = (
            f"Build {task['name']} in {workspace.resolve()}. Call delegate_contract once with "
            f"workspace={workspace.resolve()}, contract_file={contract}, sha256={digest}. "
            "Poll the same job with job_status while running. Report the final receipt. "
            "The contract contains the full design, acceptance checks and file limits."
        )
    set_tandem_mcp(effective_scenario == "tandem")
    cmd = [
        "agy",
        "-p", prompt,
        "--model", ORCHESTRATOR_MODEL,
        "--output-format", "json",
        "--mode", "auto",
        "--dangerously-skip-permissions",
        "--disable-slash-commands",
    ]

    t0 = time.monotonic()
    timed_out = False
    stdout_str = ""
    stderr_str = ""
    rc = -1

    proc = subprocess.Popen(
        cmd,
        cwd=str(workspace),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout_str, stderr_str = proc.communicate(timeout=task["timeout_s"])
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout_str, stderr_str = proc.communicate()
    elapsed = round(time.monotonic() - t0, 2)

    log_dir = run_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"{attempt_id}.stdout.txt").write_text(stdout_str or "", encoding="utf-8")
    (log_dir / f"{attempt_id}.stderr.txt").write_text(stderr_str or "", encoding="utf-8")

    parsed_json: dict[str, Any] = {}
    for line in (stdout_str or "").splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed_json = json.loads(line)
            except json.JSONDecodeError:
                pass

    status = parsed_json.get("status", "TIMEOUT" if timed_out else "ERROR")
    completed = (not timed_out) and (rc == 0) and (status == "SUCCESS")
    response_text = parsed_json.get("response", "")
    usage = parsed_json.get("usage") or {}

    ev = evaluate_attempt(task["id"], response_text, workspace)

    if effective_scenario in ("direct", "direct_parse"):
        local_stats = {
            "status": "not_applicable",
            "delegation_verified": False,
            "local_calls": 0,
            "local_prompt_tokens": 0,
            "local_completion_tokens": 0,
            "local_total_tokens": 0,
            "estimated_saved_tokens": 0,
            "retries": 0,
            "attempt_id": attempt_id,
        }
    else:
        iso_ledger = tandem_home / "ledger.jsonl"
        entries = read_ledger_entries(iso_ledger)
        local_stats = summarize_local_ledger(entries, attempt_id=attempt_id)

    delegation_verified = bool(local_stats.get("delegation_verified"))
    e2e_success = compute_e2e_success(completed, bool(ev["valid"]), effective_scenario, delegation_verified)
    route_verified = delegation_verified if effective_scenario == "tandem" else True
    if e2e_success:
        attribution_reason = "ok"
    elif completed and ev["valid"] and effective_scenario == "tandem" and not delegation_verified:
        attribution_reason = "missing_verified_delegation"
    else:
        attribution_reason = ev["reason"]

    cloud_total = usage.get("total_tokens")
    cloud_status = "available" if cloud_total is not None else "unavailable"

    return {
        "attempt_id": attempt_id,
        "task_id": task["id"],
        "task_name": task["name"],
        "category": task["category"],
        "scenario": scenario,
        "effective_scenario": effective_scenario,
        "executed_route": route_steps[-1],
        "route_steps": route_steps,
        "fallback_used": fallback_used,
        "routing": routing,
        "repeat": repeat,
        "completed": completed,
        "timed_out": timed_out,
        "artifact_valid": ev["valid"],
        "delegation_verified": delegation_verified,
        "route_verified": route_verified,
        "attribution_reason": attribution_reason,
        "eval_reason": ev["reason"],
        "eval_requirements": (ev.get("details") or {}).get("requirements"),
        "e2e_success": e2e_success,
        "duration_seconds": parsed_json.get("duration_seconds", elapsed),
        "wall_seconds": elapsed,
        "num_turns": parsed_json.get("num_turns"),
        "conversation_id": parsed_json.get("conversation_id"),
        "cloud_usage_status": cloud_status,
        "cloud_usage": {
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "thinking_tokens": usage.get("thinking_tokens"),
            "cache_read_tokens": usage.get("cache_read_tokens"),
            "total_tokens": cloud_total,
        },
        "local_usage": local_stats,
    }


def aggregate_results(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for a in attempts:
        grouped.setdefault((a["task_id"], a["scenario"]), []).append(a)

    direct_means: dict[str, float] = {}
    for (tid, scen), rows in grouped.items():
        if scen == "direct":
            toks = [r["cloud_usage"]["total_tokens"] for r in rows if r["cloud_usage"]["total_tokens"] is not None]
            if toks:
                direct_means[tid] = statistics.mean(toks)

    summary = []
    for task in TASKS:
        tid = task["id"]
        for scen in ("direct", "tandem", "selective"):
            rows = grouped.get((tid, scen), [])
            if not rows:
                continue
            n = len(rows)
            e2e = sum(1 for r in rows if r["e2e_success"])
            failed = n - e2e
            recoveries = sum(
                1 for r in rows
                if r["e2e_success"] and int((r.get("local_usage") or {}).get("retries", 0) or 0) > 0
            )
            toks = [r["cloud_usage"]["total_tokens"] for r in rows if r["cloud_usage"]["total_tokens"] is not None]
            total_cloud = sum(toks) if len(toks) == n else (sum(toks) if toks else None)
            mean_cloud = round(statistics.mean(toks), 1) if toks else None
            stdev_cloud = round(statistics.stdev(toks), 1) if len(toks) >= 2 else None
            times = [r["wall_seconds"] for r in rows]
            med_time = round(statistics.median(times), 2) if times else None
            stdev_time = round(statistics.stdev(times), 2) if len(times) >= 2 else None
            local_toks = [
                r["local_usage"]["local_total_tokens"]
                for r in rows
                if r.get("local_usage", {}).get("local_total_tokens") is not None
            ]
            total_local = sum(local_toks) if local_toks else None
            mean_local = round(statistics.mean(local_toks), 1) if local_toks else None
            timeouts = sum(1 for r in rows if r.get("timed_out"))
            fallbacks = sum(1 for r in rows if r.get("fallback_used"))
            savings_pct = None
            if scen in ("tandem", "selective") and mean_cloud is not None and tid in direct_means and direct_means[tid] > 0:
                savings_pct = round((1.0 - (mean_cloud / direct_means[tid])) * 100.0, 1)
            tok_per_useful = round(sum(toks) / e2e, 1) if (e2e > 0 and len(toks) == n) else None
            summary.append({
                "task_id": tid,
                "task_name": task["name"],
                "category": task["category"],
                "scenario": scen,
                "n": n,
                "e2e_success_count": e2e,
                "failed_count": failed,
                "recoveries": recoveries,
                "timeouts": timeouts,
                "fallbacks": fallbacks,
                "e2e_success_pct": round(100.0 * e2e / n, 1),
                "cloud_coverage": f"{len(toks)}/{n}",
                "local_coverage": f"{len(local_toks)}/{n}",
                "total_cloud_tokens": total_cloud,
                "mean_cloud_tokens": mean_cloud,
                "stdev_cloud_tokens": stdev_cloud,
                "tokens_per_useful_result": tok_per_useful,
                "cloud_savings_vs_direct_pct": savings_pct,
                "median_wall_seconds": med_time,
                "stdev_wall_seconds": stdev_time,
                "total_local_tokens": total_local,
                "mean_local_tokens": mean_local,
            })
    return summary


def render_markdown(run_id: str, pre: dict[str, Any], summary: list[dict[str, Any]], attempts: list[dict[str, Any]]) -> str:
    lines = [
        f"# Tandem MCP v3.6.1 Benchmark: {ORCHESTRATOR_LABEL} + {EXECUTOR_MODEL}",
        "",
        f"- **Run ID**: `{run_id}`",
        f"- **Date (UTC)**: `{pre['timestamp']}`",
        f"- **Orchestrator**: `{ORCHESTRATOR_MODEL}` (`agy` {pre['agy_version']})",
        f"- **Executor**: `{EXECUTOR_MODEL}` on LM Studio (`{LM_STUDIO_URL}`)",
        "- **Accounting**: Cloud tokens measured directly via `agy --output-format json`; local tokens measured via Tandem `ledger.jsonl`.",
        "",
        "## Summary Table",
        "",
        "| Task | Scenario | n | E2E Success | Mean Cloud Tokens | Cloud Savings vs Direct | Median Time (s) | Mean Local Tokens |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary:
        cloud_str = f"{row['mean_cloud_tokens']:,.1f}" if row["mean_cloud_tokens"] is not None else "N/A"
        local_str = f"{row['mean_local_tokens']:,.1f}" if row["mean_local_tokens"] is not None else "N/A"
        if row["scenario"] == "direct":
            sav_str = "baseline"
        elif row["cloud_savings_vs_direct_pct"] is not None:
            sav_str = f"{row['cloud_savings_vs_direct_pct']:+.1f}%"
        else:
            sav_str = "N/A"
        lines.append(
            f"| `{row['task_id']}` | `{row['scenario']}` | {row['n']} | "
            f"{row['e2e_success_pct']:.1f}% ({row['e2e_success_count']}/{row['n']}) | "
            f"{cloud_str} | {sav_str} | {row['median_wall_seconds']:.2f} | {local_str} |"
        )
    lines.extend([
        "",
        "## Per-Attempt Details",
        "",
        "| Attempt | Completed | Valid | E2E | Time (s) | Turns | Cloud Input | Cloud Output | Cloud Total | Local Total | Reason |",
        "| --- | :---: | :---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ])
    for a in attempts:
        cu = a["cloud_usage"]
        lu = a["local_usage"]
        local_tot = lu.get("local_total_tokens")
        local_tot_str = str(local_tot) if local_tot is not None else "unavailable"
        lines.append(
            f"| `{a['attempt_id']}` | {a['completed']} | {a['artifact_valid']} | {a['e2e_success']} | "
            f"{a['wall_seconds']:.2f} | {a['num_turns'] or '-'} | "
            f"{cu['input_tokens'] if cu.get('input_tokens') is not None else '-'} | "
            f"{cu['output_tokens'] if cu.get('output_tokens') is not None else '-'} | "
            f"{cu['total_tokens'] if cu.get('total_tokens') is not None else 'unavailable'} | "
            f"{local_tot_str} | {a['eval_reason']} |"
        )
    lines.append("")
    return "\n".join(lines)


def reevaluate_run(run_dir: Path, out_dir: Path | None = None) -> dict[str, Any]:
    """Re-evaluate saved artifacts of an existing run on temporary workspace copies without modifying original files."""
    archive_hash_before = _sha256_path(run_dir)
    orig_path = run_dir / "results.json"
    orig = json.loads(orig_path.read_text(encoding="utf-8"))
    orig_run_id = orig.get("run_id", run_dir.name)
    evaluator_sha = compute_evaluator_sha256()
    out_dir = out_dir or ROOT

    new_attempts = []
    comparisons = []
    with tempfile.TemporaryDirectory(prefix=f"reeval_{orig_run_id}_") as tmp_root_str:
        tmp_root = Path(tmp_root_str)
        for a in orig.get("attempts", []):
            aid = a["attempt_id"]
            tid = a["task_id"]
            ws = run_dir / "workspaces" / aid
            tmp_ws = tmp_root / aid
            if ws.exists():
                shutil.copytree(ws, tmp_ws)
            else:
                tmp_ws.mkdir(parents=True, exist_ok=True)
            stdout_path = run_dir / "logs" / f"{aid}.stdout.txt"
            response_text = ""
            if stdout_path.exists():
                for line in stdout_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if line.startswith("{") and line.endswith("}"):
                        try:
                            response_text = json.loads(line).get("response", "")
                        except json.JSONDecodeError:
                            pass
            ev = evaluate_attempt(tid, response_text, tmp_ws)
            eff_scen = a.get("effective_scenario") or a.get("scenario", "direct")
            iso_ledger = run_dir / "tandem_homes" / aid / "ledger.jsonl"
            if iso_ledger.exists():
                ledger_summary = summarize_local_ledger(read_ledger_entries(iso_ledger), attempt_id=aid)
                delegation_verified = bool(ledger_summary.get("delegation_verified"))
            else:
                delegation_verified = bool((a.get("local_usage") or {}).get("delegation_verified"))
            new_e2e = compute_e2e_success(bool(a.get("completed")), bool(ev["valid"]), eff_scen, delegation_verified)
            updated = dict(a)
            updated["orig_artifact_valid"] = a.get("artifact_valid")
            updated["orig_e2e_success"] = a.get("e2e_success")
            updated["orig_eval_reason"] = a.get("eval_reason")
            updated["artifact_valid"] = ev["valid"]
            updated["delegation_verified"] = delegation_verified
            updated["route_verified"] = delegation_verified if eff_scen == "tandem" else True
            updated["e2e_success"] = new_e2e
            updated["eval_reason"] = ev["reason"]
            updated["eval_requirements"] = (ev.get("details") or {}).get("requirements")
            new_attempts.append(updated)
            if a.get("e2e_success") != new_e2e:
                comparisons.append({
                    "attempt_id": aid,
                    "before": a.get("e2e_success"),
                    "after": new_e2e,
                    "reason_before": a.get("eval_reason"),
                    "reason_after": ev["reason"],
                })

    archive_hash_after = _sha256_path(run_dir)
    if archive_hash_before != archive_hash_after:
        raise RuntimeError(f"Original archive {run_dir} was modified during re-evaluation")

    summary = aggregate_results(new_attempts)
    report = {
        "original_run_id": orig_run_id,
        "reevaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "evaluator_sha256": evaluator_sha,
        "archive_sha256_before": archive_hash_before,
        "archive_sha256_after": archive_hash_after,
        "archive_unmodified": True,
        "changes": comparisons,
        "summary": summary,
        "attempts": new_attempts,
    }
    json_out = out_dir / f"REEVAL_{orig_run_id}.json"
    md_out = out_dir / f"REEVAL_{orig_run_id}.md"
    json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    md_lines = [
        f"# Re-evaluation of `{orig_run_id}`",
        "",
        f"- **Original Run ID**: `{orig_run_id}`",
        f"- **Re-evaluated (UTC)**: `{report['reevaluated_at_utc']}`",
        f"- **Evaluator SHA-256**: `{evaluator_sha}`",
        f"- **Verdicts changed**: {len(comparisons)}",
        "",
        "## Verdict Changes",
        "",
        "| Attempt | Before | After | Reason After |",
        "| --- | :---: | :---: | --- |",
    ]
    for c in comparisons:
        md_lines.append(f"| `{c['attempt_id']}` | {c['before']} | {c['after']} | {c['reason_after']} |")
    if not comparisons:
        md_lines.append("| (none) | - | - | No verdict changed |")
    md_lines.extend([
        "",
        "## Re-evaluated Summary",
        "",
        "| Task | Scenario | n | E2E Success | Failed | Mean Cloud Tokens | Cloud Coverage | Local Coverage | Median Time (s) |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in summary:
        cloud_str = f"{row['mean_cloud_tokens']:,.1f}" if row["mean_cloud_tokens"] is not None else "unavailable"
        md_lines.append(
            f"| `{row['task_id']}` | `{row['scenario']}` | {row['n']} | "
            f"{row['e2e_success_count']}/{row['n']} ({row['e2e_success_pct']:.1f}%) | "
            f"{row['failed_count']} | {cloud_str} | {row['cloud_coverage']} | {row['local_coverage']} | "
            f"{row['median_wall_seconds']:.2f} |"
        )
    md_lines.append("")
    md_out.write_text("\n".join(md_lines), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Tandem MCP Hydrogen + Qwen3.8 27B benchmark suite.")
    parser.add_argument("--tasks", default="", help="Comma-separated task IDs (default: all)")
    parser.add_argument("--scenarios", default="direct,tandem", help="Comma-separated scenarios (direct,tandem,selective)")
    parser.add_argument("--repeats", type=int, default=3, help="Paired repeats per task (default: 3)")
    parser.add_argument("--order", choices=("counterbalanced", "direct_first", "tandem_first"), default="counterbalanced")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for counterbalanced order")
    parser.add_argument("--merge-from", default="", help="Existing run_id whose attempts to merge into this run's summary")
    parser.add_argument("--lean", action="store_true", help="Enable TANDEM_PROFILE=lean and GEMINI.md orchestrator rules")
    parser.add_argument("--reevaluate", default="", help="Re-evaluate an existing run_id into a new report without modifying raw results")
    args = parser.parse_args()

    if args.reevaluate:
        report = reevaluate_run(RUNS_DIR / args.reevaluate)
        print(f"Re-evaluated {args.reevaluate}: {len(report['changes'])} verdict change(s)")
        return 0

    selected_ids = {t.strip() for t in args.tasks.split(",") if t.strip()}
    selected_tasks = [t for t in TASKS if not selected_ids or t["id"] in selected_ids]
    if not selected_tasks:
        print(f"No matching tasks for {args.tasks!r}", file=sys.stderr)
        return 2

    scenarios = tuple(s.strip() for s in args.scenarios.split(",") if s.strip())
    pre = preflight()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    plan = build_execution_plan(selected_tasks, args.repeats, order=args.order, seed=args.seed, scenarios=scenarios)
    manifest = build_run_manifest(run_id, pre, selected_tasks, args, plan)

    prior_attempts: list[dict[str, Any]] = []
    if args.merge_from:
        prior_path = RUNS_DIR / args.merge_from / "results.json"
        prior_payload = json.loads(prior_path.read_text(encoding="utf-8"))
        prior_attempts = validate_merge(prior_payload, manifest)

    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "preflight.json").write_text(json.dumps(pre, indent=2), encoding="utf-8")
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    attempts: list[dict[str, Any]] = list(prior_attempts)
    seen_warm: set[tuple[str, str]] = set()
    try:
        for step in plan:
            task = step["task"]
            scenario = step["scenario"]
            rep = step["repeat"]
            warm_cold = "warm" if (scenario, task["id"]) in seen_warm else "cold"
            seen_warm.add((scenario, task["id"]))
            print(f"[{run_id}] Running {task['id']} ({scenario}, r{rep}, {warm_cold})...", flush=True)
            res = run_attempt(task, scenario, rep, run_dir, lean_mode=args.lean)
            res["pair_id"] = step["pair_id"]
            res["pair_order"] = step["pair_order"]
            res["seed"] = step["seed"]
            res["warm_cold"] = warm_cold
            attempts.append(res)
            print(
                f"  -> e2e={res['e2e_success']} time={res['wall_seconds']}s "
                f"cloud={res['cloud_usage']['total_tokens']} local={res['local_usage']['local_total_tokens']} "
                f"({res['eval_reason']})",
                flush=True,
            )
            (run_dir / "results.partial.json").write_text(json.dumps({"attempts": attempts}, indent=2), encoding="utf-8")
    finally:
        set_tandem_mcp(bool(pre.get("initial_tandem_mcp_enabled", True)))

    summary = aggregate_results(attempts)
    payload = {
        "run_id": run_id,
        "manifest": manifest,
        "preflight": pre,
        "summary": summary,
        "attempts": attempts,
    }
    (run_dir / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md = render_markdown(run_id, pre, summary, attempts)
    (run_dir / "RESULTS.md").write_text(md, encoding="utf-8")
    (ROOT / "RESULTS.md").write_text(md, encoding="utf-8")
    print(f"Saved results to {run_dir / 'RESULTS.md'} and {ROOT / 'RESULTS.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
