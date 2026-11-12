"""What the executor may touch: paths inside a workspace, commands that match an allow list."""
import fnmatch
import os
import re
import subprocess
from pathlib import Path

# Never run for the executor, whatever the allow list says.
DENY = [r'\bsudo\b', r'\bsu\b\s', r'\brm\s+(-\w*\s+)*-\w*r\w*\s+(/|~|\$HOME)(\s|$)', r'\bgit\s+(push|commit|reset|clean|checkout|rebase|merge|tag)\b',
        r'\bmkfs', r'\bdd\s+if=', r'\bshutdown\b', r'\breboot\b', r'\bcurl\b.*\|\s*(ba)?sh', r'\bwget\b.*\|\s*(ba)?sh',
        r'\bchown\b', r'\bchmod\s+-R\b', r'>\s*/dev/sd', r'\bsystemctl\b', r'\bkill(all)?\b', r'\bpkill\b', r'\bssh\b', r'\bscp\b',
        r'\bnpm\s+publish\b', r'\bpip\s+install\b', r'\bapt(-get)?\b']
SKIP_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'build', 'managed_components', '.history', 'dist', '.cache'}


class SandboxError(RuntimeError):
    pass


class Workspace:
    def __init__(self, root, write_globs=None, allow_run=None):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise SandboxError(f'workspace is not a folder: {root}')
        if self.root == Path(self.root.anchor) or self.root == Path.home().resolve():
            raise SandboxError('workspace must be a project folder, not / or the home folder')
        self.write_globs = [g for g in (write_globs or []) if g.strip()]
        self.allow_run = [re.compile(r) for r in (allow_run or []) if r.strip()]

    def path(self, rel):
        p = (self.root / rel).resolve() if not os.path.isabs(rel) else Path(rel).resolve()
        if p != self.root and self.root not in p.parents:
            raise SandboxError(f'path outside the workspace: {rel}')
        return p

    def rel(self, p):
        return str(Path(p).resolve().relative_to(self.root))

    def writable(self, rel):
        p = self.path(rel)
        r = self.rel(p)
        if any(part in ('.git',) for part in Path(r).parts):
            raise SandboxError('the .git folder is not writable')
        if self.write_globs and not any(fnmatch.fnmatch(r, g) for g in self.write_globs):
            raise SandboxError(f'{r} is outside the files this task may write ({", ".join(self.write_globs)})')
        return p

    def check_command(self, command):
        for pattern in DENY:
            if re.search(pattern, command):
                raise SandboxError(f'command refused by the safety list: {command[:80]}')
        if not self.allow_run:
            raise SandboxError('this task may not run commands')
        if not any(r.search(command) for r in self.allow_run):
            raise SandboxError(f'command not in the allow list of this task: {command[:80]}')


def run(command, cwd, timeout=180):
    """Run a shell command, return (exit code, combined output)."""
    try:
        done = subprocess.run(command, shell=True, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
                              errors='replace')
        return done.returncode, (done.stdout or '') + (('\n' + done.stderr) if done.stderr else '')
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or b'')
        partial = partial.decode(errors='replace') if isinstance(partial, bytes) else partial
        return 124, partial + f'\n[timeout after {timeout} s]'


def read_text(path, limit=4_000_000):
    """Text of a file; PDFs through pdftotext when it is installed."""
    path = Path(path)
    if path.suffix.lower() == '.pdf':
        code, out = run(f'pdftotext -layout {str(path)!r} -', path.parent, 120)
        if code != 0:
            raise SandboxError('cannot read the PDF (pdftotext missing or failed)')
        return out[:limit]
    data = path.read_bytes()[:limit]
    if b'\x00' in data[:4096]:
        raise SandboxError(f'{path.name} looks like a binary file')
    return data.decode('utf-8', errors='replace')


def walk(root, glob='**/*', limit=4000):
    """Files under root that match the glob, generated folders skipped."""
    root = Path(root)
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            rel = str((Path(dirpath) / name).relative_to(root))
            if fnmatch.fnmatch(rel, glob) or fnmatch.fnmatch(name, glob):
                out.append(rel)
                if len(out) >= limit:
                    return sorted(out)
    return sorted(out)
