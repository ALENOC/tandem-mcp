"""Reusable Chromium runtime & animation check integrated into Tandem's server verification loop."""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

_PROBE_SCRIPT = Path(__file__).resolve().with_name("_web_probe.mjs")
_HTML_GLOB_RE = re.compile(r"\.html?$", re.I)
_ANIM_RE = re.compile(
    r"\b(animat\w*|requestAnimationFrame|orbit\w*|twinkl\w*|particle\w*|rotat\w*|canvas|3d|portal|fps)\b",
    re.I,
)


def enabled() -> bool:
    val = os.environ.get("TANDEM_WEB_CHECK", "1").strip().lower()
    return val not in ("0", "false", "no", "off")


def find_chromium() -> str | None:
    """Locate Chromium/Chrome executable, honoring TANDEM_CHROME / CHROME overrides."""
    for env_key in ("TANDEM_CHROME", "CHROME"):
        override = os.environ.get(env_key, "").strip()
        if override:
            return override if Path(override).is_file() else None
    patterns = [
        str(Path.home() / ".cache/ms-playwright/chromium-*/chrome-linux64/chrome"),
        str(Path.home() / ".cache/ms-playwright/chromium-*/chrome-linux/chrome"),
    ]
    for pat in patterns:
        hits = sorted(glob.glob(pat), reverse=True)
        for h in hits:
            if Path(h).is_file():
                return h
    for name in ("chromium", "chromium-browser", "google-chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def spec_for(goal: str, write_globs: list[str], constraints: list[str] | None = None) -> dict[str, Any] | None:
    """Return web-check spec if the contract targets an executable web page, else None."""
    if not enabled():
        return None
    globs = list(write_globs or [])
    html_globs = [g for g in globs if _HTML_GLOB_RE.search(g.strip())]
    if not html_globs and not re.search(r"\bindex\.html\b", goal or "", re.I):
        return None
    preferred_entry = "index.html" if ("index.html" in globs or not html_globs) else html_globs[0]
    text = f"{goal or ''}\n" + "\n".join(constraints or [])
    require_anim = bool(_ANIM_RE.search(text))
    return {"preferred_entry": preferred_entry, "html_globs": html_globs, "require_animation": require_anim}


def _resolve_entry(ws_root: Path, spec: dict[str, Any]) -> str | None:
    if (ws_root / "index.html").is_file():
        return "index.html"
    pref = spec.get("preferred_entry", "")
    if pref and "*" not in pref and (ws_root / pref).is_file():
        return pref
    for g in spec.get("html_globs", []):
        if "*" not in g and (ws_root / g).is_file():
            return g
    return None


def run(ws_root: str | Path, spec: dict[str, Any], timeout_s: float = 45.0) -> tuple[int, str]:
    """Run Chromium probe against the workspace entry point. Returns (exit_code, concise_report)."""
    root = Path(ws_root).resolve()
    entry = _resolve_entry(root, spec)
    if not entry:
        wanted = spec.get("preferred_entry") or "index.html"
        return 1, f"FAIL: missing web entry point {wanted!r} in workspace."

    require_anim = bool(spec.get("require_animation"))
    if not require_anim:
        html_txt = (root / entry).read_text(encoding="utf-8", errors="replace")
        if "<canvas" in html_txt.lower() and "requestanimationframe" in html_txt.lower():
            require_anim = True

    node_bin = shutil.which("node")
    chrome_bin = find_chromium()
    if not node_bin:
        return 2, "not_evaluated: node executable not found for browser verification."
    if not chrome_bin:
        return 2, "not_evaluated: Chromium executable not found for browser verification."

    try:
        proc = subprocess.run(
            [node_bin, str(_PROBE_SCRIPT), str(root), entry, chrome_bin, "1" if require_anim else "0"],
            capture_output=True,
            text=True,
            timeout=max(10.0, float(timeout_s)),
        )
    except subprocess.TimeoutExpired:
        return 2, f"not_evaluated: Chromium browser check timed out after {int(timeout_s)}s on {entry}."

    raw_out = (proc.stdout or "").strip().splitlines()
    data: dict[str, Any] = {}
    if raw_out:
        try:
            data = json.loads(raw_out[-1])
        except json.JSONDecodeError:
            data = {}

    status = data.get("status")
    if proc.returncode == 0 and status == "passed":
        return 0, f"OK: browser verified {entry} with 0 JS errors (canvas animated={data.get('animated')})."
    if status == "not_evaluated" or proc.returncode == 2:
        reason = data.get("reason") or (proc.stderr or "").strip() or "browser check unavailable"
        return 2, f"not_evaluated: {reason}"

    lines = [f"FAIL: browser check failed on {entry}:"]
    for err in (data.get("runtimeErrors") or [])[:4]:
        lines.append(f"  - runtime exception: {err.get('message')} at {err.get('location')}")
    for cerr in (data.get("consoleErrors") or [])[:3]:
        lines.append(f"  - console.error: {cerr}")
    if require_anim and not data.get("canvasSized"):
        lines.append("  - canvas missing or zero-sized (expected visible <canvas>).")
    elif require_anim and not data.get("animated"):
        obs = data.get("canvasObserved") or {}
        obs_str = (
            f" (observed canvas={obs.get('cw')}x{obs.get('ch')}, "
            f"nonZeroPixels={obs.get('nonZeroPixels')}, hashes={obs.get('hashes')})"
            if obs else ""
        )
        lines.append(f"  - canvas pixels remained static across 3 sampled frames{obs_str}.")
    if len(lines) == 1:
        tail = (proc.stderr or proc.stdout or "").strip()[-300:]
        lines.append(f"  - probe exited {proc.returncode}: {tail}")
    lines.append("Expected: 0 runtime/console errors during startup and initial frames" + (" with live canvas animation." if require_anim else "."))
    return 1, "\n".join(lines)
