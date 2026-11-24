"""Visual reference handling, local VLM screenshot review, and MCP screenshot attachment.

Separates visual quality verification from cloud code generation:
1. Optional reference_image passed up front in the contract is copied into the job folder.
2. web_check captures a 1280x800 JPEG screenshot of the live rendered page inside the job folder.
3. When a local vision-capable model (VLM) is available (via TANDEM_MODEL_VISION or server metadata),
   Tandem runs a single-shot stateless visual critique locally (0 cloud tokens, no KV cache disruption
   to the main coding conversation) and feeds concrete visual fixes back into the local repair loop.
4. When TANDEM_RECEIPT_SCREENSHOT=1 (default), MCP tool responses attach the captured screenshot as
   ImageContent so the cloud orchestrator can verify the final look and, if needed, send one short
   job_continue(hint) without writing code itself.
"""
from __future__ import annotations

import base64
import os
import re
import shutil
from pathlib import Path
from typing import Any

from . import engine, store

ALLOWED_EXTS = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.gif': 'image/gif',
}
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MiB

REVIEW_SCHEMA = {
    'type': 'object',
    'required': ['passed', 'summary', 'issues', 'fixes'],
    'properties': {
        'passed': {'type': 'boolean'},
        'summary': {'type': 'string'},
        'issues': {'type': 'array', 'items': {'type': 'string'}},
        'fixes': {'type': 'array', 'items': {'type': 'string'}},
    },
    'additionalProperties': False,
}

_VISION_UNSUPPORTED_RE = re.compile(
    r'image_url|vision|multimodal|does not support image|unsupported.*image|unknown.*content.*type',
    re.I,
)


def review_mode() -> str:
    """'auto' (default), 'on', or 'off' from TANDEM_VISUAL_REVIEW."""
    raw = os.environ.get('TANDEM_VISUAL_REVIEW', 'auto').strip().lower()
    if raw in ('0', 'false', 'no', 'off'):
        return 'off'
    if raw in ('1', 'true', 'yes', 'on', 'force'):
        return 'on'
    return 'auto'


def enabled() -> bool:
    return review_mode() != 'off'


def max_repairs() -> int:
    """Maximum local visual-review repair rounds per job (TANDEM_MAX_VISUAL_REPAIRS, default 2)."""
    try:
        return max(0, min(int(os.environ.get('TANDEM_MAX_VISUAL_REPAIRS', '2')), 5))
    except ValueError:
        return 2


def receipt_screenshot_enabled() -> bool:
    """Attach captured web screenshot as MCP ImageContent on receipts (TANDEM_RECEIPT_SCREENSHOT, default 1)."""
    raw = os.environ.get('TANDEM_RECEIPT_SCREENSHOT', '1').strip().lower()
    return raw not in ('0', 'false', 'no', 'off')


def prepare_reference(path_str: str, dest_dir: Path) -> str:
    """Validate an optional reference image path and copy it into the job folder. Returns stored path or ''."""
    raw = str(path_str or '').strip()
    if not raw:
        return ''
    src = Path(raw).expanduser().resolve()
    if not src.is_file():
        raise ValueError(f'reference_image not found: {raw!r}')
    ext = src.suffix.lower()
    if ext not in ALLOWED_EXTS:
        allowed = ', '.join(sorted(ALLOWED_EXTS))
        raise ValueError(f'reference_image must be an image file ({allowed}), got {ext or "no extension"}')
    size = src.stat().st_size
    if size <= 0:
        raise ValueError(f'reference_image is empty: {raw!r}')
    if size > MAX_IMAGE_BYTES:
        raise ValueError(f'reference_image exceeds {MAX_IMAGE_BYTES // (1024 * 1024)} MiB limit ({size} bytes)')
    dest_dir.mkdir(parents=True, exist_ok=True)
    dst = (dest_dir / f'reference{ext}').resolve()
    if src != dst:
        shutil.copy2(src, dst)
    return str(dst)


def image_b64(path: str | Path) -> tuple[str, str]:
    """Return (base64_string, mime_type) for an image file."""
    p = Path(path)
    mime = ALLOWED_EXTS.get(p.suffix.lower(), 'image/jpeg')
    data = p.read_bytes()
    return base64.b64encode(data).decode('ascii'), mime


def image_data_url(path: str | Path) -> str:
    b64, mime = image_b64(path)
    return f'data:{mime};base64,{b64}'


def select_vision_model(executor_model: str = '') -> str | None:
    """Pick a local vision-capable model for screenshot critique, or None if unavailable.

    Order:
    1. TANDEM_MODEL_VISION (explicit user override; works even when the coding executor is text-only).
    2. Active executor model if server metadata marks it as vision-capable (`type == 'vlm'` or `vision`).
    3. Another already-loaded vision-capable model on the same local server.
    4. When TANDEM_VISUAL_REVIEW=on, fall back to executor_model unless cached caps already proved vision=False.
    """
    mode = review_mode()
    if mode == 'off':
        return None
    forced = os.environ.get('TANDEM_MODEL_VISION', '').strip()
    if forced:
        return forced
    rows = []
    try:
        rows = engine.models()
    except Exception:
        rows = []
    active = executor_model or ''
    if active:
        for m in rows:
            if m.get('id') == active and (m.get('vision') or m.get('type') == 'vlm'):
                return active
    for m in rows:
        if m.get('loaded') and (m.get('vision') or m.get('type') == 'vlm'):
            return m['id']
    if mode == 'on':
        candidate = active
        if not candidate:
            try:
                candidate = engine.default_model('delegate')
            except Exception:
                return None
        try:
            known = store.model_caps(engine._caps_key(candidate)) or {}
            if known.get('vision') is False:
                return None
        except Exception:
            pass
        return candidate
    return None


def _vision_rejected(exc: Exception) -> bool:
    cause = getattr(exc, '__cause__', None) or exc
    if getattr(cause, 'status_code', None) in (400, 415, 422):
        if _VISION_UNSUPPORTED_RE.search(str(exc)):
            return True
    return bool(_VISION_UNSUPPORTED_RE.search(str(exc)))


def review(
    screenshot_path: str | Path,
    goal: str,
    constraints: list[str] | None = None,
    reference_path: str | Path | None = None,
    model: str = '',
    timeout: float | None = None,
) -> dict[str, Any]:
    """Run a stateless local VLM visual check on the rendered screenshot (0 cloud tokens).

    Returns {'status': 'passed'|'failed'|'skipped', 'model': str, 'summary': str,
             'issues': list[str], 'fixes': list[str], 'tokens': int, ...}.
    """
    shot = Path(screenshot_path)
    if not shot.is_file():
        return {'status': 'skipped', 'reason': 'screenshot missing', 'model': model, 'summary': '', 'issues': [], 'fixes': [], 'tokens': 0}

    use_model = model or select_vision_model()
    if not use_model:
        return {'status': 'skipped', 'reason': 'no local vision model available', 'model': '', 'summary': '', 'issues': [], 'fixes': [], 'tokens': 0}

    ref = Path(reference_path) if reference_path else None
    has_ref = bool(ref and ref.is_file())

    c_lines = '\n'.join(f'- {c}' for c in (constraints or [])[:20])
    c_block = f'\nContract constraints:\n{c_lines}\n' if c_lines else ''
    if has_ref:
        prompt = (
            'You are a strict visual QA reviewer for a web application.\n'
            'Image 1 is the target visual reference. Image 2 is the live 1280x800 screenshot produced by the code.\n'
            f'Goal: {goal}\n{c_block}\n'
            'Compare Image 2 against Image 1 and the contract. Report ONLY concrete, fixable visual defects '
            '(missing wireframe/neon edges, missing grid axes, broken/inverted/self-intersecting polygons, '
            'missing or unreadable HUD controls/values, blank canvas, severe palette or composition mismatch). '
            'Do not fail for minor stylistic variations when the main structure, colors, and HUD are clean.\n'
            'Set passed=true when Image 2 is clean and faithful to the target; set passed=false with specific, '
            'actionable issues and fixes when real visual defects remain.'
        )
    else:
        prompt = (
            'You are a strict visual QA reviewer for a web application.\n'
            'This image is a live 1280x800 screenshot of the rendered web page.\n'
            f'Goal: {goal}\n{c_block}\n'
            'Inspect the rendered screenshot against the goal and constraints. Report ONLY concrete, fixable '
            'visual defects (blank or cut-off canvas, broken/inverted/self-intersecting 3D geometry, missing '
            'requested wireframe edges or grid axes, unreadable/overlapping HUD or missing slider values/labels, '
            'severe mismatch with requested palette or visual polish). '
            'Do not fail for minor taste differences when the render is clean and complete.\n'
            'Set passed=true when the page looks clean and matches the contract; set passed=false with specific, '
            'actionable issues and fixes when real visual defects remain.'
        )

    parts: list[dict[str, Any]] = [{'type': 'text', 'text': prompt}]
    if has_ref:
        parts.append({'type': 'image_url', 'image_url': {'url': image_data_url(ref)}})
    parts.append({'type': 'image_url', 'image_url': {'url': image_data_url(shot)}})

    messages = [
        {'role': 'system', 'content': 'Visual QA reviewer. Reply with concise, concrete JSON only.'},
        {'role': 'user', 'content': parts},
    ]

    try:
        data, used = engine.chat_json(
            messages,
            REVIEW_SCHEMA,
            tool='visual_review',
            model=use_model,
            max_tokens=1024,
            temperature=0.1,
            timeout=timeout,
        )
    except engine.ExecutorError as exc:
        if _vision_rejected(exc):
            try:
                engine.remember(use_model, vision=False)
            except Exception:
                pass
            return {
                'status': 'skipped',
                'reason': f'model {use_model} does not support image inputs',
                'model': use_model,
                'summary': '',
                'issues': [],
                'fixes': [],
                'tokens': 0,
            }
        return {
            'status': 'skipped',
            'reason': f'visual review error: {str(exc)[:180]}',
            'model': use_model,
            'summary': '',
            'issues': [],
            'fixes': [],
            'tokens': 0,
        }

    tokens = int(used.get('prompt', 0) + used.get('completion', 0))
    passed = bool(data.get('passed'))
    summary = str(data.get('summary') or '').strip()[:300]
    issues = [str(i).strip()[:200] for i in (data.get('issues') or []) if str(i).strip()][:6]
    fixes = [str(f).strip()[:200] for f in (data.get('fixes') or []) if str(f).strip()][:6]
    # If the model set passed=false without naming any issue, do not loop blindly
    if not passed and not issues and not fixes:
        passed = True
    return {
        'status': 'passed' if passed else 'failed',
        'model': use_model,
        'summary': summary,
        'issues': issues,
        'fixes': fixes,
        'tokens': tokens,
    }


def format_repair(result: dict[str, Any], has_reference: bool = False) -> str:
    """Format a concise repair prompt for the local coding executor from a failed visual review."""
    head = (
        'All functional checks pass, but a visual review of the live 1280x800 screenshot against the '
        + ('reference image and contract ' if has_reference else 'contract ')
        + 'found visual defects:'
    )
    lines = [head]
    if result.get('summary'):
        lines.append(f'Summary: {result["summary"]}')
    for item in result.get('issues') or []:
        lines.append(f'- Issue: {item}')
    for fix in result.get('fixes') or []:
        lines.append(f'- Fix: {fix}')
    lines.append(
        'Fix these visual defects with targeted edits while keeping all functional checks and the 40 FPS '
        'frame rate passing, then call finish again.'
    )
    return '\n'.join(lines)
